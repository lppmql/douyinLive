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
from app.models.review import ReviewFinding
from app.services.ai.deepseek_client import chat
from app.services.ai.prompt_service import get_prompt_template
from app.services.ai.time_slice_service import search_time_slices, sync_session_time_slices

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


def qa_search(
    db: Session,
    question: str,
    category: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """知识库问答 — 搜索 → 拼接上下文 → DeepSeek → 回答 + 引用来源

    流程：
    1. 搜索知识库（关键词 + 可选分类）
    2. 格式化 Top 5 结果为上下文
    3. 调用 DeepSeek QA 提示词
    4. 返回回答 + 引用来源
    """
    # 1. 优先召回可追溯的时间片，再用原有整场知识补足上下文。
    retrieval_question = _contextual_question(question, history)
    time_slices = search_time_slices(db, question=retrieval_question, limit=5)
    items = search_knowledge(
        db,
        keyword=retrieval_question,
        category=category,
        limit=max(0, 5 - len(time_slices)),
    )

    if not time_slices and not items:
        # 没有匹配的知识库内容，直接让 DeepSeek 回答
        return {
            "answer": "知识库中没有找到相关信息。请尝试其他关键词或稍后再试。",
            "sources": [],
            "has_result": False,
        }

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

    knowledge_context = "\n\n---\n\n".join(context_parts)

    # 3. 用 QA 提示词调用 DeepSeek
    prompt_template = get_prompt_template(db, "qa")
    if not prompt_template:
        logger.error("未找到 qa 提示词模板")
        return {"answer": "系统配置错误", "sources": sources, "has_result": False}

    conversation = _format_conversation(history)
    contextual_prompt = f"{conversation}\n\n当前问题：{question}" if conversation else question
    user_message = prompt_template.content.replace("{knowledge_context}", knowledge_context).replace(
        "{question}", contextual_prompt
    )

    try:
        answer = chat(
            system_prompt=(
                "你是零食店避坑直播运营复盘助手。只能依据本次提供的真实知识库证据回答，"
                "需要理解历史对话中的连续追问；证据不足时必须明确说明，不得编造主播、评论、话术或指标。"
            ),
            user_message=user_message,
            temperature=0.5,
            max_tokens=2048,
            operation="knowledge_qa",
            prompt_name=prompt_template.type,
            prompt_version=prompt_template.version,
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
        content = json.dumps(r.report_content, ensure_ascii=False, indent=2) if r.report_content else r.summary
        if not content:
            continue
        title = r.report_title or f"分析 - 场次{session_id}"
        normalized_content = str(content)[:5000]
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
            saved += int(changed)
            continue

        kb = KnowledgeBase(
            session_id=session_id,
            category="分析结论",
            title=title,
            content=normalized_content,
            source_type="ai_analysis",
        )
        db.add(kb)
        saved += 1

    if saved:
        db.commit()
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
        return int(changed)

    db.add(
        KnowledgeBase(
            session_id=session_id,
            category="分析结论",
            title=title,
            content=content,
            source_type="ai_analysis",
        )
    )
    db.commit()
    logger.info("场次 %d 的 %d 条复盘发现已保存到知识库", session_id, len(findings))
    return 1
