"""知识库问答服务 — 搜索 + 本地 Ollama 回答。"""
from contextlib import aclosing
from starlette.concurrency import run_in_threadpool
import json
import logging
import re
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from app.models.analysis_reports import AnalysisReport
from app.models.transcript_segments import TranscriptSegment
from app.models.live_sessions import LiveSession
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.review import ReviewFinding
from app.prompts import get_system_prompt
from app.services.ai.llm_client import chat, chat_stream
from app.services.ai.prompt_service import get_prompt_template
from app.services.ai.time_slice_service import search_time_slices, sync_session_time_slices, format_offset

logger = logging.getLogger(__name__)


def search_knowledge(
    db: Session,
    keyword: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[KnowledgeBase]:
    """搜索知识库"""
    q = db.query(KnowledgeBase)
    if category:
        q = q.filter(KnowledgeBase.category == category)
    if not keyword:
        return q.order_by(KnowledgeBase.updated_at.desc()).limit(limit).all()

    terms = _query_terms(keyword)
    # LONGTEXT 里保存的是完整话术和评论。先让 MySQL 用较长关键词筛出候选，
    # 再在 Python 中精排，避免每次问答把数百场完整正文全部读进电脑内存。
    lookup_terms = terms[:12]
    conditions = []
    for term in lookup_terms:
        pattern = f"%{term}%"
        conditions.extend((KnowledgeBase.title.like(pattern), KnowledgeBase.content.like(pattern)))
    if conditions:
        q = q.filter(or_(*conditions))
    candidates = q.order_by(KnowledgeBase.updated_at.desc()).limit(120).all()
    ranked = []
    for item in candidates:
        title = (item.title or "").lower()
        content = (item.content or "").lower()
        score = sum((4 if term in title else 0) + min(content.count(term), 3) for term in terms)
        if score:
            ranked.append((score, item.updated_at or item.created_at, item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in ranked[:limit]]


def _query_terms(question: str) -> list[str]:
    """提取中英文检索词；中文长句补充二至四字片段，避免要求整句完全命中。"""
    normalized = question.strip().lower()
    terms = {token for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]+", normalized) if len(token) >= 2}
    for sequence in re.findall(r"[\u4e00-\u9fff]{3,}", normalized):
        for size in (2, 3, 4):
            terms.update(sequence[index:index + size] for index in range(len(sequence) - size + 1))
    return sorted(terms, key=len, reverse=True)[:40]


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """只保留最近的有效问答，避免无界上下文挤占模型输入。"""
    normalized = []
    for item in (history or [])[-8:]:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            normalized.append({"role": role, "content": content[:4000]})
    return normalized


def _contextual_question(question: str, history: list[dict[str, str]] | None = None) -> str:
    """用最近用户问题补全“这个、还有呢”等省略式追问的检索语义。"""
    normalized = _normalize_history(history)
    user_questions = [item["content"] for item in normalized if item["role"] == "user"][-2:]
    session_ids = []
    for item in normalized:
        if item["role"] != "assistant":
            continue
        for session_id in re.findall(r"场次\s*#?\s*(\d+)", item["content"], re.IGNORECASE):
            if session_id not in session_ids:
                session_ids.append(session_id)
    source_context = " ".join(f"场次{session_id}" for session_id in session_ids[-5:])
    return "\n".join([*user_questions, source_context, question.strip()])[-1200:]


def _format_conversation(history: list[dict[str, str]] | None = None) -> str:
    normalized = _normalize_history(history)
    if not normalized:
        return ""
    labels = {"user": "用户", "assistant": "助手"}
    lines = [f"{labels[item['role']]}：{item['content']}" for item in normalized]
    return "历史对话（仅用于理解连续追问）：\n" + "\n".join(lines)


def _enrich_source_anchor_profiles(db: Session, sources: list[dict[str, Any]]) -> None:
    """一次查询补齐引用来源的主播身份，避免前端再逐条请求或猜测。"""
    session_ids = sorted({source.get("session_id") for source in sources if source.get("session_id")})
    if not session_ids:
        return
    rows = (
        db.query(
            LiveSession.id,
            LiveSession.anchor_name,
            LiveSession.anchor_nickname,
            LiveSession.anchor_avatar_url,
            LiveSession.douyin_id,
        )
        .filter(LiveSession.id.in_(session_ids))
        .all()
    )
    profiles = {row.id: row for row in rows}
    for source in sources:
        profile = profiles.get(source.get("session_id"))
        if not profile:
            continue
        source["anchor_name"] = source.get("anchor_name") or profile.anchor_name
        source["anchor_nickname"] = profile.anchor_nickname
        source["anchor_avatar_url"] = profile.anchor_avatar_url
        source["douyin_id"] = profile.douyin_id


def _prepare_qa_context(
    db: Session,
    question: str,
    category: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """准备问答上下文：混合搜索 → 拼接上下文 → 构建提示词。

    把搜索、RRF 融合、上下文拼接、提示词构建这些公共逻辑抽取出来，
    让 qa_search()（一次性）和 qa_search_stream()（流式）共用。

    Returns:
        None: 没有找到相关知识或系统配置错误
        dict: {
            "sources": 引用来源列表,
            "user_message": 拼接好的用户消息（已替换占位符）,
            "system_prompt": 系统提示词,
            "prompt_template": 提示词模板对象（用于记录观测）,
        }
    """
    # 1. Phase 36: 混合搜索（向量 + 关键词并行）
    retrieval_question = _contextual_question(question, history)

    # 关键词搜索（保留作为兜底）
    time_slices_keyword = search_time_slices(db, question=retrieval_question, limit=10)
    items_keyword = search_knowledge(db, keyword=retrieval_question, category=category, limit=10)

    # 向量搜索（Qdrant 语义相似度）
    time_slices_vector, items_vector = _vector_search(retrieval_question)

    # RRF 融合两路结果
    time_slices, items = _hybrid_merge(
        db, time_slices_vector, time_slices_keyword, items_vector, items_keyword
    )

    if not time_slices and not items:
        return None

    # 2. 拼接上下文
    context_parts = []
    sources = []
    for i, item in enumerate(time_slices, 1):
        context_parts.append(
            f"[{i}] 主播：{item['anchor_name'] or '未知'}｜场次：{item['session_id']}｜"
            f"时间：{item['time_range']}｜来源：{' + '.join(item['source_types'])}\n"
            f"{(item['content'] or '')[:8000]}"
        )
        sources.append({
            "id": item["id"],
            "title": f"{item['anchor_name'] or '未知主播'}｜场次{item['session_id']}｜{item['time_range']}",
            "category": "直播时间片",
            "source_type": "time_slice",
            "session_id": item["session_id"],
            "anchor_name": item["anchor_name"],
            "time_range": item["time_range"],
            "slice_start_seconds": item["slice_start_seconds"],
            "slice_end_seconds": item["slice_end_seconds"],
            "source_types": item["source_types"],
            "excerpt": item["excerpt"],
            "score": item["score"],
        })
    offset = len(time_slices)
    for i, item in enumerate(items, offset + 1):
        context_parts.append(f"[{i}] {item.title or '无标题'}\n{item.content or ''}")
        sources.append({
            "id": item.id,
            "title": item.title,
            "category": item.category,
            "source_type": item.source_type,
            "session_id": item.session_id,
        })

    _enrich_source_anchor_profiles(db, sources)

    knowledge_context = "\n\n---\n\n".join(context_parts)

    # 3. 用 QA 提示词构建用户消息
    prompt_template = get_prompt_template(db, "qa")
    if not prompt_template:
        logger.error("未找到 qa 提示词模板")
        return None

    conversation = _format_conversation(history)
    contextual_prompt = f"{conversation}\n\n当前问题：{question}" if conversation else question
    user_message = prompt_template.content.replace("{knowledge_context}", knowledge_context).replace(
        "{question}", contextual_prompt
    )

    return {
        "sources": sources,
        "user_message": user_message,
        "system_prompt": get_system_prompt("knowledge_qa"),
        "prompt_template": prompt_template,
    }


def qa_search(
    db: Session,
    question: str,
    category: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """知识库问答（一次性返回） — 混合搜索 → 拼接上下文 → 本地模型 → 回答 + 引用来源

    Phase 36 升级：
    1. 向量搜索（Qdrant 语义相似度）+ 关键词搜索（MySQL LIKE）并行
    2. RRF 融合两路结果
    3. 格式化 Top 5 结果为上下文
    4. 调用本地模型 QA 提示词
    5. 返回回答 + 引用来源
    """
    ctx = _prepare_qa_context(db, question, category, history)
    if ctx is None:
        return {
            "answer": "知识库中没有找到相关信息。请尝试其他关键词或稍后再试。",
            "sources": [],
            "has_result": False,
        }

    try:
        answer = chat(
            system_prompt=ctx["system_prompt"],
            user_message=ctx["user_message"],
            temperature=0.5,
            max_tokens=2048,
            operation="knowledge_qa",
            prompt_name=ctx["prompt_template"].type,
            prompt_version=ctx["prompt_template"].version,
        )
    except Exception as e:
        logger.error("本地模型 QA 回答失败: %s", e)
        return {"answer": "AI 回答失败，请稍后重试", "sources": ctx["sources"], "has_result": False}

    return {
        "answer": answer,
        "sources": ctx["sources"],
        "has_result": True,
    }


async def qa_search_stream(
    db: Session,
    question: str,
    category: str | None = None,
    history: list[dict[str, str]] | None = None,
):
    """知识库问答（流式输出） — 和 qa_search 逻辑完全一样，但通过 SSE 逐字推送回答。

    生成器产出的是 SSE 格式的字符串，每条格式为：
        data: {"type": "token", "content": "文字片段"}\\n\\n

    最后一条事件包含来源引用：
        data: {"type": "done", "sources": [...], "has_result": true}\\n\\n

    出错时：
        data: {"type": "error", "message": "错误信息"}\\n\\n

    用法（FastAPI StreamingResponse）：
        return StreamingResponse(
            qa_search_stream(db, question, category, history),
            media_type="text/event-stream",
        )
    """
    # 现有数据库和向量检索为同步实现，放入线程池避免阻塞事件循环。
    ctx = await run_in_threadpool(_prepare_qa_context, db, question, category, history)
    if ctx is None:
        # 没有找到相关知识
        yield f"data: {json.dumps({'type': 'done', 'sources': [], 'has_result': False}, ensure_ascii=False)}\n\n"
        return

    try:
        # 流式调用本地模型，每收到一个 token 就推给前端
        async with aclosing(chat_stream(
            system_prompt=ctx["system_prompt"],
            user_message=ctx["user_message"],
            temperature=0.5,
            operation="knowledge_qa",
            prompt_name=ctx["prompt_template"].type,
            prompt_version=ctx["prompt_template"].version,
        )) as stream:
            async for token in stream:
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

        # 流结束后发送引用来源
        yield f"data: {json.dumps({'type': 'done', 'sources': ctx['sources'], 'has_result': True}, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error("本地模型 QA 流式回答失败: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'message': 'AI 回答失败，请稍后重试'}, ensure_ascii=False)}\n\n"


def _upsert_kb_item(
    db: Session,
    session_id: int,
    source_type: str,
    category: str,
    title: str,
    content: str,
) -> int:
    existing = db.query(KnowledgeBase).filter(
        KnowledgeBase.session_id == session_id,
        KnowledgeBase.source_type == source_type,
    ).first()
    if existing:
        existing.category = category
        existing.title = title[:200]
        existing.content = content
        db.commit()
        # Phase 36: 内容变更后同步向量到 Qdrant
        _sync_kb_item_to_qdrant(existing.id, title[:200], content, source_type)
        return 0
    kb = KnowledgeBase(
        session_id=session_id,
        category=category,
        title=title[:200],
        content=content,
        source_type=source_type,
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    # Phase 36: 新建后同步向量到 Qdrant
    _sync_kb_item_to_qdrant(kb.id, title[:200], content, source_type)
    return 1


def _sync_kb_item_to_qdrant(kb_id: int, title: str, content: str, source_type: str) -> None:
    """把一条知识条目的向量写入 Qdrant（独立事务，失败不影响 MySQL）。"""
    try:
        from app.services.ai.embedding_service import embed_text
        from app.services.ai.vector_store import upsert_knowledge_item

        # 用标题+内容拼接做 embedding，标题权重更高（靠前）
        text_for_embedding = f"{title}\n{title}\n{content}"[:3000]
        vector = embed_text(text_for_embedding)
        if vector:
            upsert_knowledge_item(
                kb_id=kb_id,
                title=title,
                content=content,
                source_type=source_type,
                vector=vector,
            )
    except Exception as exc:
        logger.debug("知识条目 %d 向量同步跳过（非关键路径）: %s", kb_id, exc)


def save_session_data_to_kb(db: Session, session_id: int) -> int:
    """把直播汇总、分钟趋势和观众画像保存为可检索知识。"""
    session = db.get(LiveSession, session_id)
    if not session:
        return 0
    metrics = db.query(LiveMetric).filter(LiveMetric.session_id == session_id).order_by(LiveMetric.metric_time).all()
    profiles = db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == session_id).all()
    profile_text = "；".join(
        f"{row.dimension_type}-{row.dimension_name}:{float(row.ratio or 0):g}%" for row in profiles
    ) or "暂无"
    peak_metric_online = max((row.online_count or 0 for row in metrics), default=0)
    metric_comments = sum(row.comment_count or 0 for row in metrics)
    # 不把 m3u8、后台地址、头像和 UID 等敏感/易过期字段放进问答知识，
    # 其余真实场次字段完整保留，方便后续问到冷门经营指标时也能回答。
    excluded_session_fields = {"dashboard_url", "stream_url", "anchor_avatar_url", "douyin_uid"}
    complete_session_fields = {
        column.name: getattr(session, column.name)
        for column in session.__table__.columns
        if column.name not in excluded_session_fields
    }
    metric_lines = [
        json.dumps(
            {
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
                if column.name not in {"created_at", "updated_at"}
            },
            ensure_ascii=False,
            default=str,
            sort_keys=True,
        )
        for row in metrics
    ]
    content = "\n".join((
        f"场次ID：{session.id}",
        f"主播：{session.anchor_name or session.anchor_nickname or '未知'}；抖音号：{session.douyin_id or '未获取'}",
        f"标题：{session.session_title or '未命名直播'}",
        f"直播时间：{session.live_start_time or '未知'} 至 {session.live_end_time or '未知'}；时长：{session.live_duration_seconds or 0}秒",
        f"观看数据：累计观看{session.total_viewers or 0}人，看过{session.viewed_count or 0}人，平均在线{session.avg_online_count or 0}人，峰值在线{session.peak_online_count or peak_metric_online}人，人均停留{float(session.avg_watch_seconds or 0):g}秒",
        f"互动数据：评论{session.comments_count or metric_comments}条，评论用户{session.comment_users or 0}人，点赞{session.like_count or 0}次，分享{session.share_count or 0}次，新增关注{session.new_followers or 0}人，互动{session.interaction_count or 0}次",
        f"转化数据：线索{session.leads_count or 0}人，私信{session.private_message_count or 0}人，小风车点击{session.mini_windmill_click_count or 0}次，卡片点击{session.card_click_count or 0}次，表单提交{session.form_submit_count or 0}次，广告消耗{float(session.ad_cost or 0):g}元",
        f"比率数据：进入率{float(session.exposure_enter_rate or 0):.2%}，关注率{float(session.follow_rate or 0):.2%}，评论率{float(session.comment_rate or 0):.2%}，互动率{float(session.interaction_rate or 0):.2%}，线索转化率{float(session.scene_lead_conversion_rate or 0):.2%}",
        f"分钟趋势：共{len(metrics)}个采样点；分钟在线峰值{peak_metric_online}人；分钟评论合计{metric_comments}条",
        f"观众画像：{profile_text}",
        "完整场次字段：" + json.dumps(complete_session_fields, ensure_ascii=False, default=str, sort_keys=True),
        "逐分钟指标：\n" + ("\n".join(metric_lines) if metric_lines else "暂无"),
    ))
    anchor = session.anchor_name or session.anchor_nickname or "未知主播"
    return _upsert_kb_item(db, session_id, "live_data", "直播数据", f"直播数据 - {anchor} - 场次{session_id}", content)


def save_comments_to_kb(db: Session, session_id: int) -> int:
    """把对应场次的真实用户评论按时间保存为互动知识。"""
    session = db.get(LiveSession, session_id)
    if not session:
        return 0
    comments = db.query(Comment).filter(Comment.session_id == session_id).order_by(Comment.comment_time, Comment.id).all()
    if not comments:
        return 0
    lines = []
    for row in comments:
        timestamp = row.comment_time.strftime("%Y-%m-%d %H:%M:%S") if row.comment_time else "时间未知"
        intent = " [高意向]" if row.is_high_intent else ""
        public_id = f"（抖音号：{row.user_douyin_id}）" if row.user_douyin_id else ""
        lines.append(
            f"{timestamp} {row.user_nickname or '匿名用户'}{public_id}{intent}：{row.comment_content or ''}"
        )
    anchor = session.anchor_name or session.anchor_nickname or "未知主播"
    header = f"场次ID：{session_id}\n主播：{anchor}\n标题：{session.session_title or '未命名直播'}\n评论总数：{len(comments)}\n"
    return _upsert_kb_item(db, session_id, "comments", "互动评论", f"直播评论 - {anchor} - 场次{session_id}", header + "\n".join(lines))


def sync_session_to_kb(db: Session, session_id: int) -> dict[str, int]:
    """幂等同步一场直播的全部已有知识资产，ASR 未开启也可同步数据和评论。"""
    slice_result = sync_session_time_slices(db, session_id)
    return {
        "live_data_saved": save_session_data_to_kb(db, session_id),
        "comments_saved": save_comments_to_kb(db, session_id),
        "transcript_saved": save_transcript_to_kb(db, session_id),
        "analysis_saved": save_analysis_to_kb(db, session_id),
        "review_saved": save_review_findings_to_kb(db, session_id),
        "time_slices_created": slice_result["created_count"],
        "time_slices_updated": slice_result["updated_count"],
        "time_slices_unchanged": slice_result["unchanged_count"],
        "time_slices_total": slice_result["slice_count"],
        "unmapped_comments": slice_result["unmapped_comment_count"],
    }


def save_transcript_to_kb(db: Session, session_id: int) -> int:
    """将优质话术保存到知识库"""
    segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.asr_status == "completed",
    ).order_by(TranscriptSegment.segment_start.asc()).all()

    if not segments:
        return 0

    full_text = "\n".join([s.text_content or "" for s in segments])
    if len(full_text) < 100:
        return 0

    # 检查是否已保存
    existing = db.query(KnowledgeBase).filter(
        KnowledgeBase.session_id == session_id,
        KnowledgeBase.source_type == "transcript",
    ).first()
    if existing:
        existing.content = full_text
        existing.title = f"话术 - 场次{session_id}"
        existing.category = "优质话术"
        db.commit()
        _sync_kb_item_to_qdrant(existing.id, f"话术 - 场次{session_id}", full_text, "transcript")
        return 0

    kb = KnowledgeBase(
        session_id=session_id,
        category="优质话术",
        title=f"话术 - 场次{session_id}",
        content=full_text,
        source_type="transcript",
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    _sync_kb_item_to_qdrant(kb.id, f"话术 - 场次{session_id}", full_text, "transcript")
    logger.info("场次 %d 话术已保存到知识库", session_id)
    return 1


def save_analysis_to_kb(db: Session, session_id: int) -> int:
    """将 AI 分析报告保存到知识库"""
    reports = db.query(AnalysisReport).filter(
        AnalysisReport.session_id == session_id,
    ).all()

    saved = 0
    # Phase 36: 收集需要同步向量的条目
    to_sync: list[tuple[int, str, str]] = []
    for r in reports:
        content = json.dumps(r.report_content, ensure_ascii=False, indent=2) if r.report_content else r.summary
        if not content:
            continue
        title = r.report_title or f"分析 - 场次{session_id}"
        normalized_content = str(content)
        existing = db.query(KnowledgeBase).filter(
            KnowledgeBase.session_id == session_id,
            KnowledgeBase.source_type == "ai_analysis",
            KnowledgeBase.title == title,
        ).first()
        if existing:
            changed = (
                existing.content != normalized_content
                or existing.category != "分析结论"
                or existing.title != title
            )
            existing.title = title
            existing.content = normalized_content
            existing.category = "分析结论"
            if changed:
                saved += 1
                kb_id = getattr(existing, "id", None)
                if kb_id is not None:
                    to_sync.append((kb_id, title, normalized_content))
            continue

        kb = KnowledgeBase(
            session_id=session_id,
            category="分析结论",
            title=title,
            content=normalized_content,
            source_type="ai_analysis",
        )
        db.add(kb)
        db.flush()  # 获取自增 ID，不提交事务
        kb_id = getattr(kb, "id", None)
        if kb_id is not None:
            to_sync.append((kb_id, title, normalized_content))
        saved += 1

    if saved:
        db.commit()
        # Phase 36: 新写入和变更的条目同步向量到 Qdrant
        for kb_id, t, c in to_sync:
            _sync_kb_item_to_qdrant(kb_id, t, c, "ai_analysis")
        logger.info("场次 %d 的 %d 条分析结果已保存到知识库", session_id, saved)
    return saved


def save_review_findings_to_kb(db: Session, session_id: int) -> int:
    """把结构化复盘发现整理成可检索、可回到原场次核验的知识。"""
    session = db.get(LiveSession, session_id)
    if not session:
        return 0
    findings = (
        db.query(ReviewFinding)
        .filter(ReviewFinding.session_id == session_id)
        .order_by(ReviewFinding.start_seconds.asc(), ReviewFinding.severity.desc(), ReviewFinding.id.asc())
        .all()
    )
    if not findings:
        return 0

    anchor = session.anchor_name or session.anchor_nickname or "未知主播"
    title = f"直播复盘 - {anchor} - 场次{session_id}"
    lines = [
        f"场次ID：{session_id}",
        f"主播：{anchor}",
        f"标题：{session.session_title or '未命名直播'}",
        f"复盘发现：{len(findings)}条",
        "以下结论只来自该场次已采集的指标、评论和真实话术：",
    ]
    for index, finding in enumerate(findings, start=1):
        seconds = float(finding.start_seconds) if finding.start_seconds is not None else None
        time_label = f"{int(seconds // 60):02d}:{int(seconds % 60):02d}" if seconds is not None else "整场"
        lines.extend(
            [
                f"{index}. [{finding.category or '未分类'}][{finding.severity or 'info'}][{time_label}] {finding.title}",
                f"结论：{finding.description or '无补充说明'}",
                f"真实证据：{finding.evidence_text or '仅有场次级指标证据'}",
                f"证据类型：{finding.evidence_type or 'session'}；来源：{finding.source or 'rule'}",
            ]
        )
    content = "\n".join(lines)

    existing = db.query(KnowledgeBase).filter(
        KnowledgeBase.session_id == session_id,
        KnowledgeBase.source_type == "ai_analysis",
        KnowledgeBase.title.like("直播复盘 - %"),
    ).first()
    if existing:
        changed = existing.title != title or existing.content != content or existing.category != "分析结论"
        existing.title = title
        existing.content = content
        existing.category = "分析结论"
        db.commit()
        if changed:
            _sync_kb_item_to_qdrant(existing.id, title, content, "ai_analysis")
        return int(changed)

    kb = KnowledgeBase(
        session_id=session_id,
        category="分析结论",
        title=title,
        content=content,
        source_type="ai_analysis",
    )
    db.add(kb)
    db.commit()
    db.refresh(kb)
    _sync_kb_item_to_qdrant(kb.id, title, content, "ai_analysis")
    logger.info("场次 %d 的 %d 条复盘发现已保存到知识库", session_id, len(findings))
    return 1


# ── Phase 36: 混合搜索辅助函数 ──


def _vector_search(question: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """向量搜索：对问题做 embedding，分别搜索时间片和知识条目两个向量集合。

    Qdrant 不可用或 embedding 失败时返回空列表，
    调用方检测后降级为纯关键词搜索。

    Returns:
        (时间片向量结果, 知识条目向量结果)
    """
    try:
        from app.services.ai.embedding_service import embed_text
        from app.services.ai.vector_store import search_time_slice_vectors, search_knowledge_vectors

        vector = embed_text(question)
        if vector is None:
            return [], []

        time_slices = search_time_slice_vectors(vector, limit=10)
        items = search_knowledge_vectors(vector, limit=10)
        return time_slices, items
    except Exception as exc:
        logger.debug("向量搜索跳过（Qdrant 不可用或 API 失败）: %s", exc)
        return [], []


def _hybrid_merge(
    db: Session,
    time_slices_vector: list[dict[str, Any]],
    time_slices_keyword: list[dict[str, Any]],
    items_vector: list[dict[str, Any]],
    items_keyword: list[KnowledgeBase],
) -> tuple[list[dict[str, Any]], list[KnowledgeBase]]:
    """混合搜索合并：向量搜 + 关键词搜 → RRF 融合 → 从 MySQL 补齐完整数据。

    Returns:
        (合并后的时间片列表, 合并后的知识条目列表)
    """
    from app.services.ai.vector_store import rrf_fusion

    # ── 时间片合并 ──
    if time_slices_vector and time_slices_keyword:
        fused_slices = rrf_fusion(
            time_slices_vector,
            time_slices_keyword,
            vector_id_key="slice_id",
            keyword_id_key="id",
            top_n=8,
        )
        merged_slices = _resolve_slices_from_fusion(db, fused_slices, time_slices_keyword)
        logger.info("RRF 融合时间片: 向量%d + 关键词%d → %d",
                      len(time_slices_vector), len(time_slices_keyword), len(merged_slices))
    elif time_slices_vector:
        merged_slices = _resolve_slices_from_vector(db, time_slices_vector)
        logger.info("纯向量搜索时间片: %d 条", len(merged_slices))
    else:
        merged_slices = time_slices_keyword
        logger.info("关键词搜索时间片: %d 条", len(merged_slices))

    # ── 知识条目合并 ──
    if items_vector and items_keyword:
        keyword_dicts = [
            {"id": item.id, "title": item.title, "content": item.content, "source_type": item.source_type}
            for item in items_keyword
        ]
        fused_items = rrf_fusion(items_vector, keyword_dicts, vector_id_key="kb_id", keyword_id_key="id", top_n=8)
        # 同时提取向量来源（kb_id）和关键词来源（id）
        kb_ids = set()
        for f in fused_items:
            kid = f.get("kb_id") or f.get("id")  # 兼容两路来源
            if kid is not None:
                kb_ids.add(kid)
        if kb_ids:
            rows = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(list(kb_ids))).all()
            row_by_id = {row.id: row for row in rows}
            merged_items = [row_by_id[kid] for kid in kb_ids if kid in row_by_id]
        else:
            merged_items = items_keyword
        logger.info("RRF 融合知识条目: 向量%d + 关键词%d → %d",
                      len(items_vector), len(items_keyword), len(merged_items))
    elif items_vector:
        kb_ids = [v["kb_id"] for v in items_vector if v.get("kb_id")]
        if kb_ids:
            rows = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(kb_ids)).all()
            row_by_id = {row.id: row for row in rows}
            merged_items = [row_by_id[kb_id] for kb_id in kb_ids if kb_id in row_by_id]
        else:
            merged_items = []
        logger.info("纯向量搜索知识条目: %d 条", len(merged_items))
    else:
        merged_items = items_keyword
        logger.info("关键词搜索知识条目: %d 条", len(merged_items))

    return merged_slices, merged_items


def _resolve_slices_from_fusion(
    db: Session,
    fused: list[dict[str, Any]],
    keyword_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """用 RRF 融合结果解析时间片完整数据。

    融合结果可能来自两路：
    - 向量侧：key 是 slice_id（Qdrant point_id）
    - 关键词侧：key 是 id（MySQL KnowledgeTimeSlice.id）

    先从关键词结果中取（最快），取不到的从 MySQL 补。
    """
    from app.models.knowledge_time_slices import KnowledgeTimeSlice

    keyword_by_id = {item["id"]: item for item in keyword_results}
    resolved = []
    db_ids_needed: set[int] = set()

    for f_item in fused:
        # 尝试从关键词结果中找（优先，数据最完整）
        kw_id = f_item.get("id")      # 关键词来源
        vec_id = f_item.get("slice_id")  # 向量来源

        found_id = None
        if kw_id is not None and kw_id in keyword_by_id:
            found_id = kw_id
        elif vec_id is not None and vec_id in keyword_by_id:
            found_id = vec_id
        elif kw_id is not None:
            db_ids_needed.add(kw_id)
        elif vec_id is not None:
            db_ids_needed.add(vec_id)

        if found_id is not None:
            resolved.append({**keyword_by_id[found_id], "match_type": f_item.get("source", "unknown")})

    # 向量搜索结果中不在关键词结果里的，从 MySQL 补齐
    if db_ids_needed:
        rows = db.query(KnowledgeTimeSlice).filter(KnowledgeTimeSlice.id.in_(list(db_ids_needed))).all()
        for row in rows:
            source_types = []
            if row.transcript_text:
                source_types.append("直播话术")
            if row.comments_text:
                source_types.append("用户评论")
            if row.metric_point_count:
                source_types.append("分钟指标")
            excerpt = (row.transcript_text or row.comments_text or row.search_text or "")[:500]
            resolved.append({
                "id": row.id,
                "session_id": row.session_id,
                "anchor_name": row.anchor_name,
                "session_title": row.session_title,
                "slice_start_seconds": row.slice_start_seconds,
                "slice_end_seconds": row.slice_end_seconds,
                "time_range": f"{format_offset(row.slice_start_seconds)}-{format_offset(row.slice_end_seconds)}",
                "source_types": source_types,
                "excerpt": excerpt,
                "score": 0,
                "content": row.search_text,
                "comment_count": row.comment_count,
                "metric_point_count": row.metric_point_count,
                "match_type": "vector",
            })

    return resolved


def _resolve_slices_from_vector(
    db: Session,
    vector_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """纯向量搜索结果：从 MySQL 捞出时间片的完整数据。"""
    if not vector_results:
        return []
    from app.models.knowledge_time_slices import KnowledgeTimeSlice

    slice_ids = [v["slice_id"] for v in vector_results if v.get("slice_id")]
    if not slice_ids:
        return []

    rows = db.query(KnowledgeTimeSlice).filter(KnowledgeTimeSlice.id.in_(slice_ids)).all()
    row_by_id = {row.id: row for row in rows}

    results = []
    for v_item in vector_results:
        row = row_by_id.get(v_item["slice_id"])
        if row is None:
            continue
        source_types = []
        if row.transcript_text:
            source_types.append("直播话术")
        if row.comments_text:
            source_types.append("用户评论")
        if row.metric_point_count:
            source_types.append("分钟指标")
        excerpt = (row.transcript_text or row.comments_text or row.search_text or "")[:500]
        results.append({
            "id": row.id,
            "session_id": row.session_id,
            "anchor_name": row.anchor_name,
            "session_title": row.session_title,
            "slice_start_seconds": row.slice_start_seconds,
            "slice_end_seconds": row.slice_end_seconds,
            "time_range": f"{format_offset(row.slice_start_seconds)}-{format_offset(row.slice_end_seconds)}",
            "source_types": source_types,
            "excerpt": excerpt,
            "score": v_item.get("score", 0),
            "content": row.search_text,
            "comment_count": row.comment_count,
            "metric_point_count": row.metric_point_count,
            "match_type": "vector",
        })
    return results
