"""AI 分析 API（DeepSeek）"""
import json
import logging
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request as FastapiRequest
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.prompts import get_system_prompt
from app.services.ai.deepseek_client import chat
from app.services.ai.prompt_service import get_prompt_template
from app.services.ai.scoring import score_session_transcript, batch_score_recent
from app.services.ai.analysis import analyze_trend, detect_anomalies
from app.services.ai.high_intent_service import identify_high_intent, list_high_intent_users
from app.services.ai.kb_service import qa_search, qa_search_stream, sync_session_to_kb
from app.services.ai.post_collection import process_session_post_collection
from app.models.analysis_reports import AnalysisReport
from app.models.live_sessions import LiveSession
from app.models.comments import Comment
from app.models.conversations import Conversation, ConversationMessage
from app.models.transcript_segments import TranscriptSegment
from app.schemas.ai import (
    AiTestResponse,
    AiScoreResponse,
    AiPipelineResponse,
    AiBatchScoreResponse,
    AiTrendResponse,
    AiAnomalyResponse,
    AiOptimizeResponse,
    AiHighIntentResponse,
    HighIntentUserOut,
    AiQaResponse,
    AiKbSaveResponse,
    AiKbSyncRecentResponse,
)
from app.schemas.conversations import (
    ConversationListItem,
    ConversationDetail,
    ConversationCreateRequest,
    ConversationDeleteResponse,
    FeedbackRequest,
)

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
    prompt_template = None
    if req.prompt_type:
        prompt_template = get_prompt_template(db, req.prompt_type)
        system_prompt = prompt_template.content if prompt_template else ""
    reply = chat(
        system_prompt=system_prompt,
        user_message=req.message,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        operation="general_chat",
        prompt_name=prompt_template.type if prompt_template else None,
        prompt_version=prompt_template.version if prompt_template else None,
    )
    return ChatResponse(reply=reply)


@router.post("/test", response_model=AiTestResponse)
def test_connection():
    """测试 DeepSeek API 连通性"""
    try:
        reply = chat(
            system_prompt=get_system_prompt("connection_test"),
            user_message="请回复连接成功",
            max_tokens=20,
            operation="connection_test",
        )
        return {"status": "ok", "reply": reply}
    except Exception as e:
        logger.exception("DeepSeek 连接测试失败")
        return {"status": "error", "message": str(e)}


# ── 话术评分 ──

@router.post("/score/{session_id}", response_model=AiScoreResponse)
def score_session(session_id: int, db: Session = Depends(get_db)):
    """对指定场次进行话术评分"""
    result = score_session_transcript(session_id, db)
    if result is None:
        raise HTTPException(400, "话术评分失败，请检查该场次是否有已完成的话术")
    return {"status": "ok", "result": result}


@router.post("/pipeline/{session_id}", response_model=AiPipelineResponse)
def run_transcript_ai_pipeline(session_id: int, db: Session = Depends(get_db)):
    """手动重跑与自动链路相同的评分、复盘、知识库和 DataEase 后处理。"""
    try:
        result = process_session_post_collection(db, session_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not result["success"]:
        raise HTTPException(500, f"AI复盘或知识库同步失败: {result['errors']}")
    return {
        "status": "ok",
        "result": result,
        **result["knowledge"],
    }


@router.post("/score/batch", response_model=AiBatchScoreResponse)
def batch_score(limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    """批量评分最近有话术但未评分的场次"""
    scored = batch_score_recent(db, limit=limit)
    return {"status": "ok", "scored_count": len(scored), "session_ids": scored}


# ── 趋势分析 ──

@router.post("/trend", response_model=AiTrendResponse)
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

@router.post("/anomaly/{session_id}", response_model=AiAnomalyResponse)
def anomaly_detection(session_id: int, db: Session = Depends(get_db)):
    """检测单场直播的异常"""
    result = detect_anomalies(session_id, db)
    if result is None:
        raise HTTPException(400, "异常检测失败，请检查场次是否存在")
    return {"status": "ok", "result": result}


# ── 优化建议 ──

@router.post("/optimize/{session_id}", response_model=AiOptimizeResponse)
def optimize_session(session_id: int, db: Session = Depends(get_db)):
    """生成单场直播的优化建议"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")
    # 获取该场次的话术评分和场次数据
    score_report = db.query(AnalysisReport).filter(
        AnalysisReport.session_id == session_id,
        AnalysisReport.report_type == "speech_score",
    ).order_by(AnalysisReport.created_at.desc()).first()

    prompt_template = get_prompt_template(db, "optimization")
    if not prompt_template:
        raise HTTPException(500, "未找到 optimization 提示词模板")

    comments = db.query(Comment).filter(Comment.session_id == session_id).order_by(
        Comment.comment_time.asc(), Comment.id.asc()
    ).limit(200).all()
    segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.session_id == session_id,
        TranscriptSegment.asr_status == "completed",
    ).order_by(TranscriptSegment.segment_start.asc()).limit(400).all()
    session_data = {
        "场次ID": session.id,
        "主播": session.anchor_name,
        "标题": session.session_title,
        "直播时长秒": session.live_duration_seconds,
        "累计观看": session.total_viewers,
        "峰值在线": session.peak_online_count,
        "平均停留秒": float(session.avg_watch_seconds or 0),
        "评论数": session.comments_count,
        "私信人数": session.private_message_count,
        "场景线索人数": session.scene_leads_count,
        "新增关注": session.new_followers,
    }
    real_comments = [
        {"用户": item.user_nickname or "匿名", "评论": item.comment_content or "", "时间": str(item.comment_time or "")}
        for item in comments
    ]
    real_transcript = [
        {
            "开始秒": float(item.segment_start or 0),
            "结束秒": float(item.segment_end or 0),
            "话术": item.text_content or "",
        }
        for item in segments
    ]
    evidence_payload = {
        "session": session_data,
        "comments": real_comments,
        "transcript_segments": real_transcript,
    }
    user_message = prompt_template.content.replace(
        "{session_data}",
        json.dumps(evidence_payload, ensure_ascii=False),
    )
    user_message = user_message.replace(
        "{speech_data}",
        str(score_report.report_content if score_report else "暂无话术评分数据"),
    )

    from app.services.ai.deepseek_client import chat_json
    result = chat_json(
        system_prompt=get_system_prompt("optimization"),
        user_message=user_message,
        temperature=0.3,
        operation="session_optimization",
        session_id=session_id,
        prompt_name=prompt_template.type,
        prompt_version=prompt_template.version,
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

@router.post("/high-intent/{session_id}", response_model=AiHighIntentResponse)
def detect_high_intent(session_id: int, db: Session = Depends(get_db)):
    """AI 识别高意向用户"""
    users = identify_high_intent(session_id, db)
    return {"status": "ok", "count": len(users), "users": users}


@router.get("/high-intent", response_model=list[HighIntentUserOut])
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

class QaHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class QaRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    category: str | None = None
    history: list[QaHistoryMessage] = Field(default_factory=list, max_length=8)


@router.post("/qa", response_model=AiQaResponse)
def knowledge_qa(req: QaRequest, db: Session = Depends(get_db)):
    """知识库问答"""
    history = [item.model_dump() for item in req.history[-8:]]
    result = qa_search(db, question=req.question, category=req.category, history=history)
    return result


@router.post("/qa/stream")
def knowledge_qa_stream(req: QaRequest, db: Session = Depends(get_db)):
    """知识库问答（流式输出）

    返回 SSE（Server-Sent Events）流，每个事件格式：
        data: {"type": "token", "content": "文字片段"}

    最后一条事件包含引用来源：
        data: {"type": "done", "sources": [...], "has_result": true}

    前端用 fetch + ReadableStream 逐字读取并实时显示，像 ChatGPT 一样的打字效果。
    """
    history = [item.model_dump() for item in req.history[-8:]]

    return StreamingResponse(
        qa_search_stream(
            db,
            question=req.question,
            category=req.category,
            history=history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲，确保逐字推送
        },
    )


@router.post("/kb/save/{session_id}", response_model=AiKbSaveResponse)
def save_to_knowledge_base(session_id: int, db: Session = Depends(get_db)):
    """将直播数据、评论、话术和分析结果统一保存到知识库。"""
    if not db.get(LiveSession, session_id):
        raise HTTPException(404, "直播场次不存在")
    return {"status": "ok", **sync_session_to_kb(db, session_id)}


@router.post("/kb/sync/recent", response_model=AiKbSyncRecentResponse)
def sync_recent_to_knowledge_base(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """增量同步最近真实场次；不依赖 ASR，已有数据和评论即可入库。"""
    sessions = db.query(LiveSession).filter(
        LiveSession.detail_collection_status == "complete",
    ).order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc()).limit(limit).all()
    totals = {
        "live_data_saved": 0,
        "comments_saved": 0,
        "transcript_saved": 0,
        "analysis_saved": 0,
        "time_slices_created": 0,
        "time_slices_updated": 0,
        "time_slices_unchanged": 0,
        "time_slices_total": 0,
        "unmapped_comments": 0,
    }
    for session in sessions:
        result = sync_session_to_kb(db, session.id)
        for key, value in result.items():
            totals[key] += value
    return {"status": "ok", "session_count": len(sessions), **totals}


# ── 对话历史管理 ──


@router.get("/conversations", response_model=list[ConversationListItem])
def list_conversations(db: Session = Depends(get_db)):
    """获取所有对话列表（按更新时间倒序，最新在前）"""
    conversations = (
        db.query(Conversation)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    return conversations


@router.post("/conversations", response_model=ConversationDetail)
def create_conversation(req: ConversationCreateRequest, db: Session = Depends(get_db)):
    """新建对话（可带首条消息）

    如果 first_message 不为空，会自动创建对话并添加首条用户消息。
    """
    title = req.title or (req.first_message[:50] if req.first_message else "新对话")
    conv = Conversation(title=title, message_count=1 if req.first_message else 0)
    db.add(conv)
    db.flush()  # 获取 conv.id

    if req.first_message:
        msg = ConversationMessage(
            conversation_id=conv.id,
            role="user",
            content=req.first_message,
        )
        db.add(msg)

    db.commit()
    db.refresh(conv)

    # 返回详情格式
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[
            {
                "id": conv.messages[0].id,
                "role": conv.messages[0].role,
                "content": conv.messages[0].content,
                "sources": None,
                "feedback": None,
                "error": False,
                "created_at": conv.messages[0].created_at,
            }
        ] if conv.messages else [],
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: int, db: Session = Depends(get_db)):
    """获取对话详情（含所有消息）"""
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "对话不存在")
    return conv


@router.delete("/conversations/{conv_id}", response_model=ConversationDeleteResponse)
def delete_conversation(conv_id: int, db: Session = Depends(get_db)):
    """删除对话（级联删除所有消息）"""
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "对话不存在")
    db.delete(conv)
    db.commit()
    return ConversationDeleteResponse(deleted_id=conv_id)


@router.post("/conversations/{conv_id}/messages/{msg_id}/feedback")
def set_message_feedback(
    conv_id: int,
    msg_id: int,
    req: FeedbackRequest,
    db: Session = Depends(get_db),
):
    """给某条助手消息点赞或踩"""
    msg = db.get(ConversationMessage, msg_id)
    if not msg or msg.conversation_id != conv_id:
        raise HTTPException(404, "消息不存在")
    if msg.role != "assistant":
        raise HTTPException(400, "只能给 AI 回答反馈")
    msg.feedback = req.feedback
    db.commit()
    return {"ok": True, "feedback": req.feedback}


class AppendMessagesRequest(BaseModel):
    """追加消息请求体（2026-07-28 方案 C）"""
    question: str = Field(min_length=1, max_length=2000)
    ai_answer: str = Field(min_length=1, max_length=8000)
    sources: list[dict] | None = None


@router.post("/conversations/{conv_id}/messages")
async def append_messages(conv_id: int, req: AppendMessagesRequest, db: Session = Depends(get_db)):
    """向对话追加用户消息和 AI 回答"""
    conv = db.get(Conversation, conv_id)
    if not conv:
        raise HTTPException(404, "对话不存在")

    question = req.question.strip()
    ai_answer = req.ai_answer.strip()

    # 保存用户消息
    user_msg = ConversationMessage(
        conversation_id=conv_id,
        role="user",
        content=question,
    )
    db.add(user_msg)

    # 保存 AI 回答
    ai_msg = ConversationMessage(
        conversation_id=conv_id,
        role="assistant",
        content=ai_answer,
        sources=req.sources,
    )
    db.add(ai_msg)

    # 更新对话：标题取第一条用户消息，消息数+2
    if not conv.title or conv.title == "新对话":
        conv.title = question[:50]
    conv.message_count = (conv.message_count or 0) + 2

    db.commit()
    return {"ok": True, "conv_id": conv_id, "user_msg_id": user_msg.id, "ai_msg_id": ai_msg.id}
