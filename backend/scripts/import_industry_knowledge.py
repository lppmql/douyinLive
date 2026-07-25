"""行业知识导入脚本 —— 把 Markdown 行业知识文档导入 MySQL 知识库 + Qdrant 向量库

用法:
    cd backend && source .venv/bin/activate
    python -m scripts.import_industry_knowledge

幂等性:
    - 相同 title 的条目会更新内容而非重复插入
    - 可安全重复运行，不会产生重复数据
"""

import logging
import re
from pathlib import Path

from app.core.database import SessionLocal
from app.models.knowledge_base import KnowledgeBase
from app.services.ai.kb_service import _sync_kb_item_to_qdrant

logger = logging.getLogger(__name__)

# 行业知识文档目录（相对于项目根目录）
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "docs" / "行业知识"


def _parse_red_black_list(text: str) -> list[dict[str, str]]:
    """解析「零食店红黑榜.md」→ 结构化条目列表。

    拆分为以下条目：
    1. 头部品牌开店通用要求
    2. 每个头部品牌的详情（好想来、赵一鸣、零食很忙、零食有鸣）
    3. 快招公司黑榜
    4. 二线品牌推荐
    """
    entries: list[dict[str, str]] = []

    # ── 条目 1: 头部品牌开店通用要求 ──
    common_req_match = re.search(
        r"## 一、四个头部一线品牌总览\s*\n\n(.+?)(?=\n### 1\.)",
        text, re.DOTALL
    )
    if common_req_match:
        entries.append({
            "title": "零食店头部品牌开店通用要求",
            "content": common_req_match.group(1).strip(),
        })

    # ── 条目 2-5: 各头部品牌详情 ──
    brand_sections = re.finditer(r"### (\d+)\. (.+?)\n(\|.+?\n\|.+?\n(?:\|.+?\n)*)", text)
    for match in brand_sections:
        brand_name = match.group(2).strip()
        table = match.group(3).strip()
        entries.append({
            "title": f"{brand_name}品牌详情",
            "content": f"# {brand_name}\n\n{table}",
        })

    # ── 条目 6: 快招公司黑榜 ──
    blacklist_match = re.search(
        r"## 二、快招公司 & 割韭菜品牌.+?\n\n(.+?)(?=\n## 三、)",
        text, re.DOTALL
    )
    if blacklist_match:
        entries.append({
            "title": "快招公司 & 割韭菜品牌避坑黑榜",
            "content": blacklist_match.group(1).strip(),
        })

    # ── 条目 7: 二线品牌推荐 ──
    second_tier_match = re.search(
        r"## 三、二线靠谱品牌推荐\s*\n\n(.+)",
        text, re.DOTALL
    )
    if second_tier_match:
        entries.append({
            "title": "二线靠谱零食店品牌推荐（预算30-40万）",
            "content": second_tier_match.group(1).strip(),
        })

    return entries


def _parse_regional_distribution(text: str) -> list[dict[str, str]]:
    """解析「零食店品牌区域分布.md」→ 按省份拆分为独立条目。

    每个省份一个条目，包含该省的一线/二线/疑似快招品牌。
    """
    entries: list[dict[str, str]] = []

    # 按省份标题拆分
    # 匹配 "### XX省" 或 "### XX市" 或 "### XX自治区"
    sections = re.split(r"\n(?=### )", text)

    for section in sections:
        # 提取省份名
        province_match = re.match(r"### (.+)", section)
        if not province_match:
            continue
        province = province_match.group(1).strip()
        content = section.strip()

        # 跳过重复条目（如内蒙古出现了两次）
        if any(e["title"] == f"{province}零食店品牌分布" for e in entries):
            continue

        entries.append({
            "title": f"{province}零食店品牌分布",
            "content": content,
        })

    return entries


def _parse_all_knowledge() -> list[dict[str, str]]:
    """解析所有行业知识 Markdown 文件，返回结构化条目列表。"""
    all_entries: list[dict[str, str]] = []

    if not KNOWLEDGE_DIR.is_dir():
        logger.warning("行业知识目录不存在: %s", KNOWLEDGE_DIR)
        return all_entries

    for md_file in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("读取 %s 失败: %s", md_file.name, exc)
            continue

        if "红黑榜" in md_file.name:
            entries = _parse_red_black_list(text)
            logger.info("从 %s 解析出 %d 条知识", md_file.name, len(entries))
            all_entries.extend(entries)
        elif "区域分布" in md_file.name:
            entries = _parse_regional_distribution(text)
            logger.info("从 %s 解析出 %d 条知识", md_file.name, len(entries))
            all_entries.extend(entries)
        else:
            # 未知文件，整篇作为一条知识
            title = md_file.stem
            all_entries.append({
                "title": title,
                "content": text,
            })
            logger.info("从 %s 整篇导入为 1 条知识", md_file.name)

    return all_entries


def import_industry_knowledge() -> dict[str, int]:
    """导入行业知识到 MySQL + Qdrant（幂等）。

    Returns:
        {"created": 新建数量, "updated": 更新数量, "total": 总处理数量}
    """
    entries = _parse_all_knowledge()
    if not entries:
        logger.warning("未找到任何行业知识条目，跳过导入")
        return {"created": 0, "updated": 0, "total": 0}

    db = SessionLocal()
    created = 0
    updated = 0

    try:
        for entry in entries:
            title = entry["title"][:200]  # 数据库字段限制 200 字符
            content = entry["content"]

            # 幂等：检查是否已存在同名条目
            existing = db.query(KnowledgeBase).filter(
                KnowledgeBase.title == title,
                KnowledgeBase.source_type == "manual",
            ).first()

            if existing:
                # 更新已有条目
                if existing.content != content or existing.category != "行业知识":
                    existing.content = content
                    existing.category = "行业知识"
                    db.commit()
                    # 内容变更后同步向量
                    _sync_kb_item_to_qdrant(existing.id, title, content, "manual")
                    updated += 1
                else:
                    updated += 1  # 内容没变，也算处理过
            else:
                # 新建条目
                kb = KnowledgeBase(
                    session_id=None,  # 行业知识与直播场次无关
                    category="行业知识",
                    title=title,
                    content=content,
                    source_type="manual",
                )
                db.add(kb)
                db.commit()
                db.refresh(kb)
                # 同步向量到 Qdrant
                _sync_kb_item_to_qdrant(kb.id, title, content, "manual")
                created += 1

        logger.info("行业知识导入完成：新建 %d 条，更新 %d 条，共 %d 条",
                     created, updated, len(entries))
    except Exception as exc:
        db.rollback()
        logger.exception("行业知识导入失败: %s", exc)
        raise
    finally:
        db.close()

    return {"created": created, "updated": updated, "total": len(entries)}


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = import_industry_knowledge()
    print(f"\n✅ 行业知识导入完成！")
    print(f"   新建: {result['created']} 条")
    print(f"   更新: {result['updated']} 条")
    print(f"   合计: {result['total']} 条")
