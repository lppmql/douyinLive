"""直播复盘工作台 API。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession
from app.models.review import ComplianceRule, ReviewActionItem, ReviewFinding, ScriptAsset
from app.models.transcript_segments import TranscriptSegment
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
)
from app.services.ai.review_service import build_workbench, compare_sessions, generate_findings


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
        return {
            "status": "ok",
            "finding_count": len(findings),
            "workbench": build_workbench(db, session_id),
        }
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


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
