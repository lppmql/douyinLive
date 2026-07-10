"""知识库问答服务 — 搜索 + DeepSeek 回答"""
import json
import logging
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.knowledge_base import KnowledgeBase
from app.models.analysis_reports import AnalysisReport
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.deepseek_client import chat, chat_json
from app.services.ai.prompt_service import get_prompt

logger = logging.getLogger(__name__)


def search_knowledge(
    db: Session,
    keyword: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[KnowledgeBase]:
    """搜索知识库"""
    q = db.query(KnowledgeBase)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(or_(
            KnowledgeBase.title.ilike(like),
            KnowledgeBase.content.ilike(like),
        ))
    if category:
        q = q.filter(KnowledgeBase.category == category)
    return q.order_by(KnowledgeBase.created_at.desc()).limit(limit).all()


def qa_search(
    db: Session,
    question: str,
    category: str | None = None,
) -> dict[str, Any]:
    """知识库问答 — 搜索 → 拼接上下文 → DeepSeek → 回答 + 引用来源

    流程：
    1. 搜索知识库（关键词 + 可选分类）
    2. 格式化 Top 5 结果为上下文
    3. 调用 DeepSeek QA 提示词
    4. 返回回答 + 引用来源
    """
    # 1. 搜索
    items = search_knowledge(db, keyword=question, category=category, limit=5)

    if not items:
        # 没有匹配的知识库内容，直接让 DeepSeek 回答
        return {
            "answer": "知识库中没有找到相关信息。请尝试其他关键词或稍后再试。",
            "sources": [],
            "has_result": False,
        }

    # 2. 拼接上下文
    context_parts = []
    sources = []
    for i, item in enumerate(items, 1):
        context_parts.append(f"[{i}] {item.title or '无标题'}\n{item.content or ''}")
        sources.append({
            "id": item.id,
            "title": item.title,
            "category": item.category,
            "source_type": item.source_type,
        })

    knowledge_context = "\n\n---\n\n".join(context_parts)

    # 3. 用 QA 提示词调用 DeepSeek
    prompt = get_prompt(db, "qa")
    if not prompt:
        logger.error("未找到 qa 提示词模板")
        return {"answer": "系统配置错误", "sources": sources, "has_result": False}

    user_message = prompt.replace("{knowledge_context}", knowledge_context).replace(
        "{question}", question
    )

    try:
        answer = chat(
            system_prompt="你是一个直播数据分析助手，请基于提供的知识库内容回答问题。",
            user_message=user_message,
            temperature=0.5,
            max_tokens=2048,
        )
    except Exception as e:
        logger.error("DeepSeek QA 回答失败: %s", e)
        return {"answer": "AI 回答失败，请稍后重试", "sources": sources, "has_result": False}

    return {
        "answer": answer,
        "sources": sources,
        "has_result": True,
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
    logger.info("场次 %d 话术已保存到知识库", session_id)
    return 1


def save_analysis_to_kb(db: Session, session_id: int) -> int:
    """将 AI 分析报告保存到知识库"""
    reports = db.query(AnalysisReport).filter(
        AnalysisReport.session_id == session_id,
    ).all()

    saved = 0
    for r in reports:
        existing = db.query(KnowledgeBase).filter(
            KnowledgeBase.session_id == session_id,
            KnowledgeBase.source_type == "ai_analysis",
            KnowledgeBase.title == r.report_title,
        ).first()
        if existing:
            continue

        content = json.dumps(r.report_content, ensure_ascii=False, indent=2) if r.report_content else r.summary
        if not content:
            continue

        kb = KnowledgeBase(
            session_id=session_id,
            category="分析结论",
            title=r.report_title or f"分析 - 场次{session_id}",
            content=str(content)[:5000],
            source_type="ai_analysis",
        )
        db.add(kb)
        saved += 1

    if saved:
        db.commit()
        logger.info("场次 %d 的 %d 条分析结果已保存到知识库", session_id, saved)
    return saved
