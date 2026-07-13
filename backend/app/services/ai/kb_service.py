"""知识库问答服务 — 搜索 + DeepSeek 回答"""
import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from app.models.analysis_reports import AnalysisReport
from app.models.transcript_segments import TranscriptSegment
from app.models.live_sessions import LiveSession
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.live_audience_profiles import LiveAudienceProfile
from app.services.ai.deepseek_client import chat
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
    if category:
        q = q.filter(KnowledgeBase.category == category)
    candidates = q.order_by(KnowledgeBase.updated_at.desc()).limit(300).all()
    if not keyword:
        return candidates[:limit]

    terms = _query_terms(keyword)
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
            "session_id": item.session_id,
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
        existing.content = content[:60000]
        db.commit()
        return 0
    db.add(KnowledgeBase(
        session_id=session_id,
        category=category,
        title=title[:200],
        content=content[:60000],
        source_type=source_type,
    ))
    db.commit()
    return 1


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
        lines.append(f"{timestamp} {row.user_nickname or '匿名用户'}{intent}：{row.comment_content or ''}")
    anchor = session.anchor_name or session.anchor_nickname or "未知主播"
    header = f"场次ID：{session_id}\n主播：{anchor}\n标题：{session.session_title or '未命名直播'}\n评论总数：{len(comments)}\n"
    return _upsert_kb_item(db, session_id, "comments", "互动评论", f"直播评论 - {anchor} - 场次{session_id}", header + "\n".join(lines))


def sync_session_to_kb(db: Session, session_id: int) -> dict[str, int]:
    """幂等同步一场直播的全部已有知识资产，ASR 未开启也可同步数据和评论。"""
    return {
        "live_data_saved": save_session_data_to_kb(db, session_id),
        "comments_saved": save_comments_to_kb(db, session_id),
        "transcript_saved": save_transcript_to_kb(db, session_id),
        "analysis_saved": save_analysis_to_kb(db, session_id),
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
