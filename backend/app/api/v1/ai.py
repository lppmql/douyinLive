"""AI 分析 API（DeepSeek）"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.database import get_db
from app.services.ai.deepseek_client import chat
from app.services.ai.prompt_service import get_prompt
from app.services.ai.scoring import score_session_transcript, batch_score_recent
from app.services.ai.analysis import analyze_trend, detect_anomalies
from app.services.ai.high_intent_service import identify_high_intent, list_high_intent_users
from app.services.ai.kb_service import qa_search, sync_session_to_kb
from app.models.analysis_reports import AnalysisReport
from app.models.high_intent_users import HighIntentUser
from app.models.live_sessions import LiveSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI-分析"])


class ChatRequest(BaseModel):
    message: str
    prompt_type: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096


class ChatResponse(BaseModel):
    reply: str


# ── 通用对话 ──

@router.post("/chat", response_model=ChatResponse)
def ai_chat(req: ChatRequest, db: Session = Depends(get_db)):
    """AI 对话（可选使用提示词模板）"""
    system_prompt = ""
    if req.prompt_type:
        system_prompt = get_prompt(db, req.prompt_type) or ""
    reply = chat(
        system_prompt=system_prompt,
        user_message=req.message,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )
    return ChatResponse(reply=reply)


@router.post("/test")
def test_connection():
    """测试 DeepSeek API 连通性"""
    try:
        reply = chat(
            system_prompt="你是一个AI助手。只回复'连接成功'这四个字即可。",
            user_message="请回复连接成功",
            max_tokens=20,
        )
        return {"status": "ok", "reply": reply}
    except Exception as e:
        logger.exception("DeepSeek 连接测试失败")
        return {"status": "error", "message": str(e)}


# ── 话术评分 ──

@router.post("/score/{session_id}")
def score_session(session_id: int, db: Session = Depends(get_db)):
    """对指定场次进行话术评分"""
    result = score_session_transcript(session_id, db)
    if result is None:
        raise HTTPException(400, "话术评分失败，请检查该场次是否有已完成的话术")
    return {"status": "ok", "result": result}


@router.post("/pipeline/{session_id}")
def run_transcript_ai_pipeline(session_id: int, db: Session = Depends(get_db)):
    """转写完成后执行评分，并把话术和分析结果同步到知识库。"""
    result = score_session_transcript(session_id, db)
    if result is None:
        raise HTTPException(400, "没有足够的已完成话术，无法执行 AI 分析")
    saved = sync_session_to_kb(db, session_id)
    return {
        "status": "ok",
        "result": result,
        **saved,
    }


@router.post("/score/batch")
def batch_score(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """批量评分最近有话术但未评分的场次"""
    scored = batch_score_recent(db, limit=limit)
    return {"status": "ok", "scored_count": len(scored), "session_ids": scored}


# ── 趋势分析 ──

@router.post("/trend")
def trend_analysis(
    session_ids: list[int] = Query(..., min_length=2),
    db: Session = Depends(get_db),
):
    """多场直播趋势对比分析"""
    result = analyze_trend(session_ids, db)
    if result is None:
        raise HTTPException(400, "趋势分析失败，需要至少2场已结束的直播")
    return {"status": "ok", "result": result}


# ── 异常检测 ──

@router.post("/anomaly/{session_id}")
def anomaly_detection(session_id: int, db: Session = Depends(get_db)):
    """检测单场直播的异常"""
    result = detect_anomalies(session_id, db)
    if result is None:
        raise HTTPException(400, "异常检测失败，请检查场次是否存在")
    return {"status": "ok", "result": result}


# ── 优化建议 ──

@router.post("/optimize/{session_id}")
def optimize_session(session_id: int, db: Session = Depends(get_db)):
    """生成单场直播的优化建议"""
    # 获取该场次的话术评分和场次数据
    score_report = db.query(AnalysisReport).filter(
        AnalysisReport.session_id == session_id,
        AnalysisReport.report_type == "speech_score",
    ).order_by(AnalysisReport.created_at.desc()).first()

    prompt = get_prompt(db, "optimization")
    if not prompt:
        raise HTTPException(500, "未找到 optimization 提示词模板")

    user_message = prompt.replace("{session_data}", f"场次ID: {session_id}")
    user_message = user_message.replace(
        "{speech_data}",
        str(score_report.report_content if score_report else "暂无话术评分数据"),
    )

    from app.services.ai.deepseek_client import chat_json
    result = chat_json(
        system_prompt="你是一个直播运营专家，请按JSON格式输出优化建议。",
        user_message=user_message,
        temperature=0.3,
    )

    report = AnalysisReport(
        session_id=session_id,
        report_type="optimization",
        report_title=f"优化建议 - 场次{session_id}",
        report_content=result,
        summary=result.get("summary", ""),
    )
    db.add(report)
    db.commit()

    return {"status": "ok", "result": result}


# ── 高意向用户 ──

@router.post("/high-intent/{session_id}")
def detect_high_intent(session_id: int, db: Session = Depends(get_db)):
    """AI 识别高意向用户"""
    users = identify_high_intent(session_id, db)
    return {"status": "ok", "count": len(users), "users": users}


@router.get("/high-intent", response_model=list[dict])
def list_high_intent(
    session_id: int | None = Query(None),
    intent_level: str | None = Query(None),
    is_contacted: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """查询高意向用户列表"""
    users = list_high_intent_users(db, session_id, intent_level, is_contacted, skip, limit)
    return [
        {
            "id": u.id,
            "session_id": u.session_id,
            "user_name": u.user_name,
            "phone": u.phone,
            "product_interest": u.product_interest,
            "intent_level": u.intent_level,
            "intent_reason": u.intent_reason,
            "is_contacted": u.is_contacted,
            "created_at": str(u.created_at) if u.created_at else None,
        }
        for u in users
    ]


# ── 知识库问答 ──

class QaRequest(BaseModel):
    question: str
    category: str | None = None


@router.post("/qa")
def knowledge_qa(req: QaRequest, db: Session = Depends(get_db)):
    """知识库问答"""
    result = qa_search(db, question=req.question, category=req.category)
    return result


@router.post("/kb/save/{session_id}")
def save_to_knowledge_base(session_id: int, db: Session = Depends(get_db)):
    """将直播数据、评论、话术和分析结果统一保存到知识库。"""
    if not db.get(LiveSession, session_id):
        raise HTTPException(404, "直播场次不存在")
    return {"status": "ok", **sync_session_to_kb(db, session_id)}


@router.post("/kb/sync/recent")
def sync_recent_to_knowledge_base(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """增量同步最近真实场次；不依赖 ASR，已有数据和评论即可入库。"""
    sessions = db.query(LiveSession).filter(
        LiveSession.detail_collection_status == "complete",
    ).order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc()).limit(limit).all()
    totals = {"live_data_saved": 0, "comments_saved": 0, "transcript_saved": 0, "analysis_saved": 0}
    for session in sessions:
        result = sync_session_to_kb(db, session.id)
        for key, value in result.items():
            totals[key] += value
    return {"status": "ok", "session_count": len(sessions), **totals}
