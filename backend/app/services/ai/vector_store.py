"""Qdrant 向量存储服务 —— 知识库的向量索引层

职责：
1. 管理 Qdrant 集合（启动时自动创建）
2. 写入向量（知识条目/时间片同步时调用）
3. 向量搜索（问答时调用）
4. 混合检索：向量搜 + 关键词搜 → RRF 融合排序

所有方法都带降级逻辑：Qdrant 不可用时返回空结果，不影响关键词搜索兜底。"""

import logging
from typing import Any

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
    ScoredPoint,
)

from app.core.config import settings
from app.core.qdrant import get_client

logger = logging.getLogger(__name__)

# bge-small-zh-v1.5 的固定输出维度。集合初始化不应导入 embedding_service，
# 否则仅检查 Qdrant 也会强制要求安装和加载 torch/transformers。
VECTOR_DIM = 512

# ── 集合（Collection）管理 ──


def _collection_name(source: str) -> str:
    """根据来源类型返回集合名。"""
    if source == "time_slice":
        return settings.QDRANT_COLLECTION_SLICES
    return settings.QDRANT_COLLECTION_KB


def ensure_collections() -> dict[str, bool]:
    """确保两个向量集合存在，不存在则自动创建。

    在 FastAPI 启动事件中调用。
    返回每个集合是否创建成功。
    """
    client = get_client()
    if client is None:
        return {settings.QDRANT_COLLECTION_KB: False, settings.QDRANT_COLLECTION_SLICES: False}

    result = {}
    for collection_name, description in [
        (settings.QDRANT_COLLECTION_KB, "知识条目"),
        (settings.QDRANT_COLLECTION_SLICES, "时间片"),
    ]:
        try:
            existing = {c.name for c in client.get_collections().collections}
            if collection_name not in existing:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=VECTOR_DIM,
                        distance=Distance.COSINE,  # 余弦相似度，适合语义匹配
                    ),
                )
                logger.info("Qdrant 集合 '%s' (%s) 创建成功", collection_name, description)
            else:
                logger.debug("Qdrant 集合 '%s' (%s) 已存在", collection_name, description)
            result[collection_name] = True
        except Exception as exc:
            logger.error("Qdrant 集合 '%s' (%s) 创建失败: %s", collection_name, description, exc)
            result[collection_name] = False

    return result


# ── 写入向量 ──


def upsert_knowledge_item(
    kb_id: int,
    session_id: int,
    title: str,
    content: str,
    source_type: str,
    vector: list[float] | None,
) -> bool:
    """写入/更新一条知识条目的向量。

    Args:
        kb_id: 知识条目 ID（MySQL 主键，用作 Qdrant point_id）
        title: 标题（存在 payload 里，方便调试）
        content: 内容片段（存在 payload 里）
        source_type: 来源类型
        vector: 768 维向量

    Returns:
        是否写入成功
    """
    if vector is None:
        logger.debug("知识条目 %d 跳过向量写入（embedding 失败）", kb_id)
        return False

    client = get_client()
    if client is None:
        return False

    collection = settings.QDRANT_COLLECTION_KB
    try:
        client.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=kb_id,  # 用 MySQL 主键当 point_id，方便精确删除
                    vector=vector,
                    payload={
                        "kb_id": kb_id,
                        "session_id": session_id,
                        "title": title,
                        "content": content[:2000],  # payload 存摘要，完整内容在 MySQL
                        "source_type": source_type,
                    },
                )
            ],
            wait=True,
        )
        logger.debug("知识条目 %d 向量写入 Qdrant 成功", kb_id)
        return True
    except Exception as exc:
        logger.warning("知识条目 %d 向量写入 Qdrant 失败: %s", kb_id, exc)
        return False


def upsert_time_slice(
    slice_id: int,
    session_id: int,
    anchor_name: str,
    search_text: str,
    vector: list[float] | None,
) -> bool:
    """写入/更新一个时间片的向量。

    Args:
        slice_id: 时间片 ID（MySQL knowledge_time_slices 主键）
        session_id: 所属场次 ID
        anchor_name: 主播名
        search_text: 搜索文本（向量化来源）
        vector: 768 维向量

    Returns:
        是否写入成功
    """
    if vector is None:
        logger.debug("时间片 %d 跳过向量写入（embedding 失败）", slice_id)
        return False

    client = get_client()
    if client is None:
        return False

    collection = settings.QDRANT_COLLECTION_SLICES
    try:
        client.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=slice_id,
                    vector=vector,
                    payload={
                        "slice_id": slice_id,
                        "session_id": session_id,
                        "anchor_name": anchor_name,
                        "search_text": search_text[:2000],
                    },
                )
            ],
            wait=True,
        )
        logger.debug("时间片 %d 向量写入 Qdrant 成功", slice_id)
        return True
    except Exception as exc:
        logger.warning("时间片 %d 向量写入 Qdrant 失败: %s", slice_id, exc)
        return False


def delete_knowledge_item(kb_id: int) -> bool:
    """删除一条知识条目的向量。"""
    client = get_client()
    if client is None:
        return False
    try:
        client.delete(
            collection_name=settings.QDRANT_COLLECTION_KB,
            points_selector=[kb_id],
            wait=True,
        )
        return True
    except Exception as exc:
        logger.warning("知识条目 %d 向量删除失败: %s", kb_id, exc)
        return False


def delete_time_slice(slice_id: int) -> bool:
    """删除一个时间片的向量。"""
    client = get_client()
    if client is None:
        return False
    try:
        client.delete(
            collection_name=settings.QDRANT_COLLECTION_SLICES,
            points_selector=[slice_id],
            wait=True,
        )
        return True
    except Exception as exc:
        logger.warning("时间片 %d 向量删除失败: %s", slice_id, exc)
        return False


# ── 向量搜索 ──


def search_knowledge_vectors(
    query_vector: list[float],
    limit: int = 10,
    session_id: int | None = None,
) -> list[dict[str, Any]]:
    """在知识条目集合中做向量相似度搜索。

    Args:
        query_vector: 问题向量
        limit: 返回条数

    Returns:
        [{kb_id, title, content, source_type, score}, ...]
    """
    client = get_client()
    if client is None:
        return []

    try:
        results: list[ScoredPoint] = client.search(
            collection_name=settings.QDRANT_COLLECTION_KB,
            query_vector=query_vector,
            limit=limit,
            query_filter=_session_filter(session_id),
        )
        return [
            {
                "kb_id": int(point.id),
                "session_id": point.payload.get("session_id"),
                "title": point.payload.get("title", ""),
                "content": point.payload.get("content", ""),
                "source_type": point.payload.get("source_type", ""),
                "score": round(float(point.score), 4),
            }
            for point in results
            if point.payload
        ]
    except Exception as exc:
        logger.warning("知识条目向量搜索失败: %s", exc)
        return []


def search_time_slice_vectors(
    query_vector: list[float],
    limit: int = 10,
    session_id: int | None = None,
) -> list[dict[str, Any]]:
    """在时间片集合中做向量相似度搜索。

    Args:
        query_vector: 问题向量
        limit: 返回条数

    Returns:
        [{slice_id, session_id, anchor_name, search_text, score}, ...]
    """
    client = get_client()
    if client is None:
        return []

    try:
        results: list[ScoredPoint] = client.search(
            collection_name=settings.QDRANT_COLLECTION_SLICES,
            query_vector=query_vector,
            limit=limit,
            query_filter=_session_filter(session_id),
        )
        return [
            {
                "slice_id": int(point.id),
                "session_id": point.payload.get("session_id", 0),
                "anchor_name": point.payload.get("anchor_name", ""),
                "search_text": point.payload.get("search_text", ""),
                "score": round(float(point.score), 4),
            }
            for point in results
            if point.payload
        ]
    except Exception as exc:
        logger.warning("时间片向量搜索失败: %s", exc)
        return []


def _session_filter(session_id: int | None) -> Filter | None:
    """为场次级问答构造 Qdrant 过滤器；全知识库模式不限制。"""
    if session_id is None:
        return None
    return Filter(must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))])


# ── 混合检索（RRF 倒数排名融合） ──


def rrf_fusion(
    vector_results: list[dict[str, Any]],
    keyword_results: list[dict[str, Any]],
    vector_id_key: str = "id",
    keyword_id_key: str = "id",
    k: int = 60,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    """RRF（倒数排名融合）算法：把向量搜和关键词搜两路结果智能合并。

    原理白话：
    - 向量搜排第 1 的结果 → 得分 1/(60+1) = 0.0164
    - 关键词搜排第 1 的结果 → 得分 1/(60+1) = 0.0164
    - 如果同一个结果在两路都排前面，得分会叠加，排名更高
    - k=60 是经验值，保证排名靠前的结果分数差距不会太大

    Args:
        vector_results: 向量搜索结果列表
        keyword_results: 关键词搜索结果列表
        vector_id_key: 向量结果里 ID 的字段名
        keyword_id_key: 关键词结果里 ID 的字段名
        k: RRF 平滑因子
        top_n: 返回前 N 条

    Returns:
        融合排序后的结果列表，每项含 rrf_score 和来源标记
    """
    rrf_scores: dict[tuple[str, int], float] = {}
    merged_items: dict[tuple[str, int], dict[str, Any]] = {}

    # 向量搜索结果给 RRF 分
    for rank, item in enumerate(vector_results):
        item_id = item.get(vector_id_key)
        if item_id is None:
            continue
        key = ("vector", item_id)
        rrf_scores[key] = 1.0 / (k + rank + 1)
        merged_items[key] = {**item, "source": "vector"}

    # 关键词搜索结果给 RRF 分
    for rank, item in enumerate(keyword_results):
        item_id = item.get(keyword_id_key)
        if item_id is None:
            continue
        key = ("keyword", item_id)
        rrf_scores[key] = 1.0 / (k + rank + 1)
        merged_items[key] = {**item, "source": "keyword"}

    # 处理同时出现在两路的结果 —— 分数叠加
    vector_ids = {(v.get(vector_id_key)) for v in vector_results}
    keyword_ids = {(k.get(keyword_id_key)) for k in keyword_results}
    common_ids = vector_ids & keyword_ids

    for item_id in common_ids:
        if item_id is None:
            continue
        v_key = ("vector", item_id)
        k_key = ("keyword", item_id)
        if v_key in rrf_scores and k_key in rrf_scores:
            rrf_scores[v_key] += rrf_scores[k_key]
            merged_items[v_key]["source"] = "both"

    # 按 RRF 分数排序
    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    top_items = sorted_items[:top_n]

    result = []
    for key, rrf_score in top_items:
        item = merged_items.get(key)
        if item:
            item["rrf_score"] = round(rrf_score, 6)
            result.append(item)

    return result
