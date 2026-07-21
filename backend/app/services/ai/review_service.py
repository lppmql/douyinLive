"""基于真实采集数据构建直播复盘工作台。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.analysis_reports import AnalysisReport
from app.models.comments import Comment
from app.models.high_intent_users import HighIntentUser
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.live_metrics import LiveMetric
from app.models.live_sessions import LiveSession
from app.models.review import ComplianceRule, ReviewActionItem, ReviewFinding, ScriptAsset
from app.models.stream_sources import StreamSource
from app.models.transcript_segments import TranscriptSegment


INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "选址": ("选址", "位置", "商圈", "小区", "学校", "超市", "人流", "商业街"),
    "预算": ("预算", "租金", "房租", "转让费", "多少钱", "多少万", "面积", "平米", "平方"),
    "品牌": ("加盟", "品牌", "赵一鸣", "零食很忙", "好想来", "老婆大人"),
    "供应链": ("货源", "供应链", "进货", "厂家", "配送", "选品"),
    "经营测算": ("毛利", "回本", "营业额", "销量", "损耗", "临期", "利润"),
    "证照": ("营业执照", "食品经营许可证", "证照", "办证"),
    "资料领取": ("资料", "清单", "表格", "怎么领", "发我", "想要", "私信"),
}

CONTENT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "开场留人": ("听5分钟", "别急着走", "不做韭菜", "开店前", "今天讲"),
    "选址避坑": ("选址", "位置", "商圈", "人流", "小区", "学校", "商业街"),
    "预算测算": ("预算", "房租", "租金", "转让费", "装修", "货架", "面积"),
    "品牌判断": ("品牌", "加盟", "赵一鸣", "零食很忙", "好想来", "牌子"),
    "供应链": ("供应链", "进货", "货源", "选品", "配送", "厂家"),
    "毛利损耗": ("毛利", "利润", "损耗", "临期", "回本", "营业额"),
    "资料钩子": ("资料", "清单", "表格", "领取", "红色按钮"),
    "私信承接": ("私信", "站内", "发消息", "咨询"),
}


def _as_float(value: Any) -> float:
    return float(value or 0)


def _seconds_from_start(session: LiveSession, value: datetime | None) -> float | None:
    if not session.live_start_time or not value:
        return None
    return max(0.0, (value - session.live_start_time).total_seconds())


def _duration_seconds(session: LiveSession) -> int:
    if session.live_duration_seconds:
        return int(session.live_duration_seconds)
    if session.live_start_time:
        end = session.live_end_time or datetime.now()
        return max(0, int((end - session.live_start_time).total_seconds()))
    return 0


def _latest_stream(db: Session, session: LiveSession) -> str | None:
    source = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session.id)
        .order_by((StreamSource.status == "active").desc(), StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    return (source.m3u8_url if source else None) or session.stream_url


def calculate_completeness(db: Session, session: LiveSession) -> dict[str, Any]:
    """按真实覆盖率计算可分析程度，区分真实零值和缺失数据。"""
    duration = _duration_seconds(session)
    metric_count = db.query(LiveMetric).filter(LiveMetric.session_id == session.id).count()
    comment_count = db.query(Comment).filter(Comment.session_id == session.id).count()
    profile_count = db.query(LiveAudienceProfile).filter(LiveAudienceProfile.session_id == session.id).count()
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.session_id == session.id, TranscriptSegment.asr_status == "completed")
        .all()
    )
    report_count = db.query(AnalysisReport).filter(AnalysisReport.session_id == session.id).count()

    basic_fields = [session.anchor_name, session.live_start_time, session.session_title, session.detail_collection_status]
    basic_ratio = sum(bool(value) for value in basic_fields) / len(basic_fields)
    expected_metrics = max(1, duration // 60) if duration else max(1, metric_count)
    metric_ratio = min(1.0, metric_count / expected_metrics)
    platform_comment_count = max(int(session.comments_count or 0), int(session.comment_users or 0))
    comment_ratio = min(1.0, comment_count / platform_comment_count) if platform_comment_count else 1.0
    max_segment_end = max((_as_float(item.segment_end) for item in segments), default=0)
    transcript_ratio = min(1.0, max_segment_end / duration) if duration else (1.0 if segments else 0.0)
    stream_ratio = 1.0 if _latest_stream(db, session) else 0.0
    profile_ratio = 1.0 if profile_count else 0.0
    report_ratio = 1.0 if report_count else 0.0

    components = [
        ("基础信息", 10, basic_ratio, sum(bool(value) for value in basic_fields), len(basic_fields)),
        ("分钟指标", 25, metric_ratio, metric_count, expected_metrics),
        ("评论映射", 15, comment_ratio, comment_count, platform_comment_count),
        ("话术转写", 25, transcript_ratio, int(max_segment_end), duration),
        ("直播回放", 10, stream_ratio, int(bool(stream_ratio)), 1),
        ("观众画像", 10, profile_ratio, profile_count, 1),
        ("AI报告", 5, report_ratio, report_count, 1),
    ]
    score = round(sum(weight * ratio for _, weight, ratio, _, _ in components), 1)
    return {
        "score": score,
        "level": "complete" if score >= 85 else "usable" if score >= 60 else "insufficient",
        "analysis_ready": score >= 60 and metric_count > 0 and (comment_count > 0 or len(segments) > 0),
        "duration_seconds": duration,
        "components": [
            {
                "name": name,
                "weight": weight,
                "score": round(ratio * 100, 1),
                "captured": captured,
                "expected": expected,
                "status": "complete" if ratio >= 0.95 else "partial" if ratio > 0 else "missing",
            }
            for name, weight, ratio, captured, expected in components
        ],
    }


def _upsert_finding(db: Session, session_id: int, payload: dict[str, Any]) -> ReviewFinding:
    finding = db.query(ReviewFinding).filter(
        ReviewFinding.session_id == session_id,
        ReviewFinding.evidence_key == payload["evidence_key"],
    ).first()
    if finding:
        preserved_status = finding.status
        for key, value in payload.items():
            setattr(finding, key, value)
        finding.status = preserved_status
        return finding
    finding = ReviewFinding(session_id=session_id, **payload)
    db.add(finding)
    return finding


def _keyword_categories(text: str, mapping: dict[str, tuple[str, ...]]) -> list[str]:
    return [category for category, words in mapping.items() if any(word.lower() in text.lower() for word in words)]


def generate_findings(db: Session, session_id: int) -> list[ReviewFinding]:
    """只用数据库中的真实证据生成结构化发现，不补写不存在的场景。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("直播场次不存在")

    metrics = (
        db.query(LiveMetric)
        .filter(LiveMetric.session_id == session_id)
        .order_by(LiveMetric.metric_time.asc(), LiveMetric.id.asc())
        .all()
    )
    comments = (
        db.query(Comment)
        .filter(Comment.session_id == session_id)
        .order_by(Comment.comment_time.asc(), Comment.id.asc())
        .limit(1000)
        .all()
    )
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.session_id == session_id, TranscriptSegment.asr_status == "completed")
        .order_by(TranscriptSegment.segment_start.asc(), TranscriptSegment.id.asc())
        .limit(2000)
        .all()
    )

    completeness = calculate_completeness(db, session)
    if completeness["score"] < 60:
        _upsert_finding(
            db,
            session_id,
            {
                "evidence_key": "data-completeness",
                "finding_type": "risk",
                "category": "数据质量",
                "title": "数据完整度不足，暂不适合生成强结论",
                "description": "请先补齐缺失的指标、评论或话术；当前仅展示有原始证据的观察。",
                "severity": "warning",
                "evidence_type": "session",
                "evidence_text": f"真实数据完整度 {completeness['score']}%",
                "confidence": 1,
                "source": "rule",
            },
        )

    drops: list[tuple[float, LiveMetric, LiveMetric]] = []
    for previous, current in zip(metrics, metrics[1:]):
        before = int(previous.online_count or 0)
        after = int(current.online_count or 0)
        if before >= 3 and after <= before * 0.6:
            drops.append(((before - after) / before, previous, current))
    for ratio, previous, current in sorted(drops, key=lambda item: item[0], reverse=True)[:5]:
        seconds = _seconds_from_start(session, current.metric_time)
        _upsert_finding(
            db,
            session_id,
            {
                "evidence_key": f"online-drop:{current.id}",
                "finding_type": "observation",
                "category": "留人",
                "title": f"在线人数下降 {ratio * 100:.0f}%",
                "description": "建议回看该时间点前后话术，确认是否发生话题切换、互动中断或承接不足。",
                "severity": "critical" if ratio >= 0.7 else "warning",
                "start_seconds": seconds,
                "end_seconds": (seconds + 60) if seconds is not None else None,
                "evidence_type": "metric",
                "evidence_text": f"在线人数从 {int(previous.online_count or 0)} 降至 {int(current.online_count or 0)}",
                "metric_name": "online_count",
                "metric_before": previous.online_count,
                "metric_after": current.online_count,
                "confidence": min(1, 0.7 + ratio / 3),
                "source": "rule",
            },
        )

    intent_found = 0
    existing_intent_comment_ids = {
        item.comment_id
        for item in db.query(HighIntentUser).filter(HighIntentUser.session_id == session_id).all()
        if item.comment_id
    }
    for comment in comments:
        text = (comment.comment_content or "").strip()
        categories = _keyword_categories(text, INTENT_KEYWORDS)
        if not categories:
            continue
        seconds = _seconds_from_start(session, comment.comment_time)
        primary = categories[0]
        _upsert_finding(
            db,
            session_id,
            {
                "evidence_key": f"intent-comment:{comment.id}",
                "finding_type": "opportunity",
                "category": "私信留资" if "资料领取" in categories else "互动",
                "title": f"观众提出{primary}相关问题",
                "description": "这是零食店筹备意图的真实信号，建议先在直播间回答核心问题，再引导用户主动站内私信领取对应资料。",
                "severity": "warning" if "资料领取" in categories else "info",
                "start_seconds": seconds,
                "end_seconds": (seconds + 30) if seconds is not None else None,
                "evidence_type": "comment",
                "evidence_text": f"{comment.user_nickname or '匿名用户'}：{text}",
                "confidence": min(0.98, 0.72 + 0.06 * len(categories)),
                "source": "rule",
            },
        )
        comment.is_high_intent = 1
        comment.keywords = ",".join(categories)
        if comment.id not in existing_intent_comment_ids:
            db.add(
                HighIntentUser(
                    session_id=session_id,
                    comment_id=comment.id,
                    user_name=comment.user_nickname,
                    product_interest="、".join(categories),
                    intent_level="high" if "资料领取" in categories else "medium",
                    intent_reason=f"真实评论包含零食店筹备主题：{'、'.join(categories)}",
                )
            )
            existing_intent_comment_ids.add(comment.id)
        intent_found += 1
        if intent_found >= 30:
            break

    hook_segments = []
    for segment in segments:
        text = (segment.text_content or "").strip()
        categories = _keyword_categories(text, CONTENT_CATEGORIES)
        if categories and segment.segment_type in (None, "", "asr_offline", "asr_realtime"):
            segment.segment_type = categories[0]
        if any(category in categories for category in ("资料钩子", "私信承接")):
            hook_segments.append((segment, categories))
    for segment, categories in hook_segments[:8]:
        _upsert_finding(
            db,
            session_id,
            {
                "evidence_key": f"lead-hook:{segment.id}",
                "finding_type": "observation",
                "category": "资料钩子" if "资料钩子" in categories else "私信留资",
                "title": "检测到资料钩子或站内私信承接话术",
                "description": "请结合该时间点后5分钟的评论和私信变化，判断钩子是否清晰、资料是否与观众问题匹配。",
                "severity": "info",
                "start_seconds": segment.segment_start,
                "end_seconds": segment.segment_end,
                "evidence_type": "transcript",
                "evidence_text": (segment.text_content or "")[:1000],
                "confidence": Decimal("0.95"),
                "source": "rule",
            },
        )

    rules = db.query(ComplianceRule).filter(ComplianceRule.enabled == 1).all()
    for rule in rules:
        words = [word.strip() for word in (rule.pattern or "").split("|") if word.strip()]
        hits = 0
        for segment in segments:
            text = segment.text_content or ""
            matched = next((word for word in words if word.lower() in text.lower()), None)
            if not matched:
                continue
            _upsert_finding(
                db,
                session_id,
                {
                    "evidence_key": f"compliance:{rule.rule_code}:{segment.id}",
                    "finding_type": "risk",
                    "category": "合规",
                    "title": rule.name,
                    "description": f"命中“{matched}”。{rule.guidance} 本结果仅用于风险筛查，需人工结合上下文确认。",
                    "severity": rule.severity,
                    "start_seconds": segment.segment_start,
                    "end_seconds": segment.segment_end,
                    "evidence_type": "transcript",
                    "evidence_text": text[:1000],
                    "confidence": Decimal("0.85"),
                    "source": "rule",
                },
            )
            hits += 1
            if hits >= 10:
                break

    if int(session.total_viewers or 0) >= 100 and int(session.private_message_count or 0) == 0:
        _upsert_finding(
            db,
            session_id,
            {
                "evidence_key": "no-private-message-conversion",
                "finding_type": "risk",
                "category": "私信留资",
                "title": "有观看流量但未形成站内私信",
                "description": "优先检查资料价值是否具体、领取动作是否清晰，以及主播是否先回答问题再引导私信。",
                "severity": "warning",
                "evidence_type": "session",
                "evidence_text": f"累计观看 {int(session.total_viewers or 0)}，私信人数 0",
                "metric_name": "private_message_count",
                "metric_before": session.total_viewers,
                "metric_after": 0,
                "confidence": Decimal("0.92"),
                "source": "rule",
            },
        )

    db.commit()
    return (
        db.query(ReviewFinding)
        .filter(ReviewFinding.session_id == session_id)
        .order_by(ReviewFinding.start_seconds.asc(), ReviewFinding.severity.desc(), ReviewFinding.id.asc())
        .all()
    )


def build_domain_coverage(segments: list[TranscriptSegment]) -> list[dict[str, Any]]:
    category_segments: dict[str, list[TranscriptSegment]] = defaultdict(list)
    for segment in segments:
        text = segment.text_content or ""
        for category in _keyword_categories(text, CONTENT_CATEGORIES):
            category_segments[category].append(segment)
    return [
        {
            "category": category,
            "covered": bool(category_segments.get(category)),
            "segment_count": len(category_segments.get(category, [])),
            "first_seconds": _as_float(category_segments[category][0].segment_start) if category_segments.get(category) else None,
        }
        for category in CONTENT_CATEGORIES
    ]


def build_live_alerts(db: Session, session: LiveSession) -> list[dict[str, Any]]:
    metrics = (
        db.query(LiveMetric)
        .filter(LiveMetric.session_id == session.id)
        .order_by(LiveMetric.metric_time.desc(), LiveMetric.id.desc())
        .limit(6)
        .all()
    )
    alerts: list[dict[str, Any]] = []
    if not metrics:
        return [{"key": "no-metrics", "severity": "critical", "title": "尚未收到实时指标", "description": "请检查实时监控与采集账号状态。", "start_seconds": None}]
    latest = metrics[0]
    freshness = (datetime.now() - latest.metric_time).total_seconds()
    if session.live_status == "live" and freshness > 180:
        alerts.append(
            {
                "key": "metric-stale",
                "severity": "critical",
                "title": "实时指标超过3分钟未更新",
                "description": f"最后指标时间为 {latest.metric_time:%H:%M:%S}，请检查监控服务。",
                "start_seconds": _seconds_from_start(session, latest.metric_time),
            }
        )
    chronological = list(reversed(metrics))
    if len(chronological) >= 2:
        previous, current = chronological[-2], chronological[-1]
        before, after = int(previous.online_count or 0), int(current.online_count or 0)
        if before >= 3 and after <= before * 0.6:
            alerts.append(
                {
                    "key": f"live-online-drop:{current.id}",
                    "severity": "warning",
                    "title": "在线人数快速下降",
                    "description": f"在线人数从 {before} 降至 {after}，建议立即切回具体避坑案例或回答公屏问题。",
                    "start_seconds": _seconds_from_start(session, current.metric_time),
                }
            )
    recent_comments = db.query(Comment).filter(
        Comment.session_id == session.id,
        Comment.comment_time >= latest.metric_time.replace(second=0, microsecond=0),
    ).count()
    if session.live_status == "live" and int(latest.online_count or 0) > 0 and recent_comments == 0:
        alerts.append(
            {
                "key": "no-recent-comment",
                "severity": "info",
                "title": "当前有在线用户但暂时没有新问题",
                "description": "可用“准备开店的预算和城市打在公屏”这类具体问题启动互动，不使用虚假福利刺激。",
                "start_seconds": _seconds_from_start(session, latest.metric_time),
            }
        )
    return alerts


def _serialize_finding(item: ReviewFinding) -> dict[str, Any]:
    return {
        "id": item.id,
        "session_id": item.session_id,
        "report_id": item.report_id,
        "finding_type": item.finding_type,
        "category": item.category,
        "title": item.title,
        "description": item.description,
        "severity": item.severity,
        "start_seconds": _as_float(item.start_seconds) if item.start_seconds is not None else None,
        "end_seconds": _as_float(item.end_seconds) if item.end_seconds is not None else None,
        "evidence_type": item.evidence_type,
        "evidence_text": item.evidence_text,
        "metric_name": item.metric_name,
        "metric_before": _as_float(item.metric_before) if item.metric_before is not None else None,
        "metric_after": _as_float(item.metric_after) if item.metric_after is not None else None,
        "confidence": _as_float(item.confidence),
        "source": item.source,
        "status": item.status,
        "created_at": item.created_at,
    }


def _serialize_action(item: ReviewActionItem) -> dict[str, Any]:
    return {column.name: getattr(item, column.name) for column in item.__table__.columns}


def _serialize_asset(item: ScriptAsset) -> dict[str, Any]:
    data = {column.name: getattr(item, column.name) for column in item.__table__.columns}
    for key in ("start_seconds", "end_seconds"):
        data[key] = _as_float(data[key]) if data[key] is not None else None
    return data


def build_workbench(db: Session, session_id: int, refresh_findings: bool = False) -> dict[str, Any]:
    session = db.get(LiveSession, session_id)
    if not session:
        raise ValueError("直播场次不存在")
    if refresh_findings:
        findings = generate_findings(db, session_id)
    else:
        findings = db.query(ReviewFinding).filter(ReviewFinding.session_id == session_id).order_by(
            ReviewFinding.start_seconds.asc(), ReviewFinding.id.asc()
        ).all()
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.session_id == session_id, TranscriptSegment.asr_status == "completed")
        .order_by(TranscriptSegment.segment_start.asc(), TranscriptSegment.id.asc())
        .limit(2000)
        .all()
    )
    reports = (
        db.query(AnalysisReport)
        .filter(AnalysisReport.session_id == session_id)
        .order_by(AnalysisReport.created_at.desc(), AnalysisReport.id.desc())
        .limit(20)
        .all()
    )
    latest_reports: dict[str, dict[str, Any]] = {}
    for report in reports:
        latest_reports.setdefault(
            report.report_type,
            {
                "id": report.id,
                "report_type": report.report_type,
                "report_title": report.report_title,
                "summary": report.summary,
                "report_content": report.report_content,
                "created_at": report.created_at,
            },
        )
    actions = db.query(ReviewActionItem).filter(ReviewActionItem.session_id == session_id).order_by(
        ReviewActionItem.status.asc(), ReviewActionItem.id.desc()
    ).all()
    assets = db.query(ScriptAsset).filter(ScriptAsset.session_id == session_id).order_by(ScriptAsset.id.desc()).all()
    return {
        "session_id": session_id,
        "business_context": "零食店避坑知识科普，通过真实问题解答和资料钩子引导用户主动站内私信留资",
        "completeness": calculate_completeness(db, session),
        "transcript_segments": [
            {
                "id": item.id,
                "segment_start": _as_float(item.segment_start),
                "segment_end": _as_float(item.segment_end),
                "text_content": item.text_content,
                "segment_type": item.segment_type,
                "ai_score": _as_float(item.ai_score) if item.ai_score is not None else None,
            }
            for item in segments
        ],
        "domain_coverage": build_domain_coverage(segments),
        "findings": [_serialize_finding(item) for item in findings],
        "actions": [_serialize_action(item) for item in actions],
        "script_assets": [_serialize_asset(item) for item in assets],
        "live_alerts": build_live_alerts(db, session),
        "latest_reports": list(latest_reports.values()),
    }


COMPARISON_FIELDS = (
    ("total_viewers", "累计观看"),
    ("peak_online_count", "峰值在线"),
    ("avg_watch_seconds", "平均停留秒数"),
    ("comments_count", "评论数"),
    ("private_message_count", "私信人数"),
    ("new_followers", "新增关注"),
    ("comment_rate", "评论率"),
    ("scene_lead_conversion_rate", "线索转化率"),
)


def _comparison_session(db: Session, current: LiveSession, other_session_id: int | None) -> LiveSession | None:
    if other_session_id:
        return db.get(LiveSession, other_session_id)
    query = db.query(LiveSession).filter(LiveSession.id != current.id)
    if current.douyin_uid:
        query = query.filter(LiveSession.douyin_uid == current.douyin_uid)
    elif current.anchor_name:
        query = query.filter(LiveSession.anchor_name == current.anchor_name)
    if current.live_start_time:
        query = query.filter(LiveSession.live_start_time < current.live_start_time)
    return query.order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc()).first()


def _minute_series(db: Session, session: LiveSession) -> list[dict[str, Any]]:
    rows = db.query(LiveMetric).filter(LiveMetric.session_id == session.id).order_by(LiveMetric.metric_time.asc()).all()
    by_minute: dict[int, dict[str, Any]] = {}
    for row in rows:
        seconds = _seconds_from_start(session, row.metric_time)
        if seconds is None:
            continue
        minute = int(seconds // 60)
        by_minute[minute] = {
            "minute": minute,
            "online_count": int(row.online_count or 0),
            "comment_count": int(row.comment_count or 0),
            "clue_count": int(row.clue_count or 0),
            "follow_count": int(row.follow_count or 0),
        }
    return list(by_minute.values())[:360]


def compare_sessions(db: Session, session_id: int, other_session_id: int | None = None) -> dict[str, Any]:
    current = db.get(LiveSession, session_id)
    if not current:
        raise ValueError("直播场次不存在")
    other = _comparison_session(db, current, other_session_id)
    if not other:
        raise ValueError("没有找到可对比的历史场次")

    dimensions = []
    for key, label in COMPARISON_FIELDS:
        current_value = _as_float(getattr(current, key, 0))
        other_value = _as_float(getattr(other, key, 0))
        delta = current_value - other_value
        dimensions.append(
            {
                "key": key,
                "label": label,
                "current": current_value,
                "baseline": other_value,
                "delta": delta,
                "delta_rate": round(delta / other_value, 4) if other_value else None,
            }
        )
    return {
        "current": {
            "id": current.id,
            "anchor_name": current.anchor_name,
            "session_title": current.session_title,
            "live_start_time": current.live_start_time,
            "duration_seconds": _duration_seconds(current),
            "completeness": calculate_completeness(db, current)["score"],
        },
        "baseline": {
            "id": other.id,
            "anchor_name": other.anchor_name,
            "session_title": other.session_title,
            "live_start_time": other.live_start_time,
            "duration_seconds": _duration_seconds(other),
            "completeness": calculate_completeness(db, other)["score"],
        },
        "dimensions": dimensions,
        "current_series": _minute_series(db, current),
        "baseline_series": _minute_series(db, other),
        "comparison_note": "曲线按开播后的相对分钟对齐；场次时长和数据完整度差异较大时，仅用于观察，不直接判断主播优劣。",
    }
