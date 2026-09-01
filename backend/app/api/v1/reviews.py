"""直播复盘工作台 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession
from app.models.review import ComplianceRule, ReviewActionItem, ReviewFinding, ScriptAsset
from app.models.unified_ai_review import AudienceInteractionAnalysis
from app.models.transcript_segments import TranscriptSegment
from app.models.comments import Comment
from app.models.live_metrics import LiveMetric
from app.models.clip_clips import ClipClip
from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.unified_ai_review import UnifiedAiReviewRun
from app.schemas.review import (
    FindingStatusUpdate,
    ReviewActionCreate,
    ReviewActionUpdate,
    ScriptAssetCreate,
    ScriptAssetUpdate,
    ReviewWorkbenchResponse,
    ReviewGenerateResponse,
    ReviewComparisonResponse,
    ReviewFindingOut,
    ReviewActionOut,
    ReviewScriptAssetOut,
    ComplianceRuleOut,
    AudienceAnalysisOverrideRequest,
)
from app.services.ai.review_service import build_workbench, compare_sessions, generate_findings
from app.services.ai.unified_review import AnalysisGenerationBusyError, LocalAiUnavailableError, generate_unified_review
from app.services.ai.unified_review import get_unified_review, refresh_unified_summary_counts


router = APIRouter(prefix="/reviews", tags=["直播复盘工作台"])


def _row_dict(row) -> dict:
    data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    for key in ("start_seconds", "end_seconds", "confidence", "metric_before", "metric_after"):
        if key in data and data[key] is not None:
            data[key] = float(data[key])
    # datetime → ISO 字符串（Pydantic Schema 用 str 类型）
    from datetime import datetime as dt
    for key in ("created_at", "updated_at"):
        if key in data and isinstance(data[key], dt):
            data[key] = data[key].isoformat()
    return data


@router.get("/readiness-funnel", response_model=dict)
def get_review_readiness_funnel(db: Session = Depends(get_db)):
    """返回从场次采集到复盘、剪辑和客资归属的真实数据漏斗。"""

    def distinct_sessions(model, *filters) -> int:
        return int(
            db.query(func.count(func.distinct(model.session_id)))
            .filter(model.session_id.isnot(None), *filters)
            .scalar()
            or 0
        )

    total_sessions = int(db.query(func.count(LiveSession.id)).scalar() or 0)
    detail_complete = int(
        db.query(func.count(LiveSession.id))
        .filter(LiveSession.detail_collection_status == "complete")
        .scalar()
        or 0
    )
    lead_total = int(db.query(func.count(LeadConversionPair.id)).scalar() or 0)
    attributed_leads = int(
        db.query(func.count(LeadConversionPair.id))
        .filter(LeadConversionPair.session_id.isnot(None))
        .scalar()
        or 0
    )
    steps = [
        {"key": "sessions", "label": "直播场次", "count": total_sessions},
        {"key": "details", "label": "详情完整", "count": detail_complete},
        {"key": "metrics", "label": "有分钟指标", "count": distinct_sessions(LiveMetric)},
        {"key": "comments", "label": "有评论", "count": distinct_sessions(Comment)},
        {
            "key": "transcripts",
            "label": "有真实转写",
            "count": distinct_sessions(TranscriptSegment, TranscriptSegment.asr_status == "completed"),
        },
        {
            "key": "reviews",
            "label": "AI复盘完成",
            "count": distinct_sessions(UnifiedAiReviewRun, UnifiedAiReviewRun.status == "completed"),
        },
        {
            "key": "clips",
            "label": "已有成片",
            "count": distinct_sessions(ClipClip, ClipClip.video_path.isnot(None)),
        },
    ]
    return {
        "steps": steps,
        "lead_attribution": {
            "total": lead_total,
            "attributed": attributed_leads,
            "pending": max(0, lead_total - attributed_leads),
            "rate": round(attributed_leads / lead_total * 100, 1) if lead_total else 0,
        },
    }


@router.get("/{session_id}/workbench", response_model=ReviewWorkbenchResponse)
def get_workbench(
    session_id: int,
    refresh_findings: bool = Query(False),
    db: Session = Depends(get_db),
):
    try:
        return build_workbench(db, session_id, refresh_findings=refresh_findings)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{session_id}/generate", response_model=ReviewGenerateResponse)
def generate_session_review(session_id: int, db: Session = Depends(get_db)):
    try:
        findings = generate_findings(db, session_id)
        unified_review = generate_unified_review(db, session_id, force=True)
        return {
            "status": "ok",
            "finding_count": len(findings),
            "workbench": build_workbench(db, session_id),
            "unified_ai_review": unified_review,
        }
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except AnalysisGenerationBusyError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LocalAiUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.patch("/{session_id}/audience/{analysis_id}", response_model=dict)
def override_audience_analysis(
    session_id: int,
    analysis_id: int,
    data: AudienceAnalysisOverrideRequest,
    db: Session = Depends(get_db),
):
    """人工确认或清除用户画像结论，人工结果展示时优先于AI。"""
    row = db.query(AudienceInteractionAnalysis).filter(
        AudienceInteractionAnalysis.id == analysis_id,
        AudienceInteractionAnalysis.session_id == session_id,
    ).first()
    if not row:
        raise HTTPException(404, "用户AI分析不存在")
    if data.clear:
        row.manual_override = None
    else:
        values = data.model_dump(exclude={"clear"}, exclude_none=True)
        if not values:
            raise HTTPException(400, "请至少提交一项人工结论")
        # 分类采用一致的状态机，避免“精准新客 + 已开店/恶意/非目标”等矛盾组合。
        if values.get("business_stage") == "opened_store":
            values.update(precision_status="existing_store", is_precision_lead=False)
        elif values.get("demand_scope") in {"non_snack_store", "industry_peer"}:
            values.update(
                precision_status="non_target" if values["demand_scope"] == "non_snack_store" else "industry_peer",
                is_precision_lead=False,
            )
        elif values.get("interaction_type") == "malicious":
            values.update(precision_status="malicious", is_precision_lead=False)
        elif values.get("precision_status") == "precision_new_lead" or values.get("is_precision_lead") is True:
            values.update(precision_status="precision_new_lead", is_precision_lead=True)
        elif "precision_status" in values:
            values["is_precision_lead"] = False
        row.manual_override = values
    db.commit()
    refresh_unified_summary_counts(db, session_id)
    return get_unified_review(db, session_id) or {}


@router.get("/{session_id}/comparison", response_model=ReviewComparisonResponse)
def get_comparison(
    session_id: int,
    other_session_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        return compare_sessions(db, session_id, other_session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.patch("/{session_id}/findings/{finding_id}", response_model=ReviewFindingOut)
def update_finding_status(
    session_id: int,
    finding_id: int,
    data: FindingStatusUpdate,
    db: Session = Depends(get_db),
):
    finding = db.query(ReviewFinding).filter(
        ReviewFinding.id == finding_id,
        ReviewFinding.session_id == session_id,
    ).first()
    if not finding:
        raise HTTPException(404, "复盘发现不存在")
    finding.status = data.status
    db.commit()
    db.refresh(finding)
    return _row_dict(finding)


@router.post("/{session_id}/actions", response_model=ReviewActionOut)
def create_action(
    session_id: int,
    data: ReviewActionCreate,
    db: Session = Depends(get_db),
):
    if not db.get(LiveSession, session_id):
        raise HTTPException(404, "直播场次不存在")
    if data.finding_id:
        finding = db.query(ReviewFinding).filter(
            ReviewFinding.id == data.finding_id,
            ReviewFinding.session_id == session_id,
        ).first()
        if not finding:
            raise HTTPException(400, "复盘发现不属于当前场次")
    action = ReviewActionItem(session_id=session_id, **data.model_dump())
    db.add(action)
    db.commit()
    db.refresh(action)
    return _row_dict(action)


@router.patch("/{session_id}/actions/{action_id}", response_model=ReviewActionOut)
def update_action(
    session_id: int,
    action_id: int,
    data: ReviewActionUpdate,
    db: Session = Depends(get_db),
):
    action = db.query(ReviewActionItem).filter(
        ReviewActionItem.id == action_id,
        ReviewActionItem.session_id == session_id,
    ).first()
    if not action:
        raise HTTPException(404, "整改任务不存在")
    changes = data.model_dump(exclude_unset=True)
    verification_session_id = changes.get("verification_session_id")
    if verification_session_id and not db.get(LiveSession, verification_session_id):
        raise HTTPException(400, "验证场次不存在")
    for key, value in changes.items():
        setattr(action, key, value)
    db.commit()
    db.refresh(action)
    return _row_dict(action)


@router.post("/{session_id}/script-assets", response_model=ReviewScriptAssetOut)
def create_script_asset(
    session_id: int,
    data: ScriptAssetCreate,
    db: Session = Depends(get_db),
):
    if not db.get(LiveSession, session_id):
        raise HTTPException(404, "直播场次不存在")
    if not data.transcript_segment_id:
        raise HTTPException(400, "话术资产必须关联真实 ASR 片段")
    segment = db.query(TranscriptSegment).filter(
        TranscriptSegment.id == data.transcript_segment_id,
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.asr_status == "completed",
    ).first()
    if not segment or not (segment.text_content or "").strip():
        raise HTTPException(400, "话术片段不属于当前场次或尚未完成真实转写")
    asset = ScriptAsset(
        session_id=session_id,
        transcript_segment_id=segment.id,
        category=data.category,
        title=data.title,
        content=segment.text_content.strip(),
        start_seconds=segment.segment_start,
        end_seconds=segment.segment_end,
        performance_note=data.performance_note,
        status=data.status,
    )
    db.add(asset)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "该话术片段已经加入资产库") from exc
    db.refresh(asset)
    return _row_dict(asset)


@router.patch("/{session_id}/script-assets/{asset_id}", response_model=ReviewScriptAssetOut)
def update_script_asset(
    session_id: int,
    asset_id: int,
    data: ScriptAssetUpdate,
    db: Session = Depends(get_db),
):
    asset = db.query(ScriptAsset).filter(
        ScriptAsset.id == asset_id,
        ScriptAsset.session_id == session_id,
    ).first()
    if not asset:
        raise HTTPException(404, "话术资产不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return _row_dict(asset)


@router.get("/compliance/rules", response_model=list[ComplianceRuleOut])
def list_compliance_rules(db: Session = Depends(get_db)):
    rows = db.query(ComplianceRule).filter(ComplianceRule.enabled == 1).order_by(
        ComplianceRule.category.asc(), ComplianceRule.id.asc()
    ).all()
    return [_row_dict(row) for row in rows]
