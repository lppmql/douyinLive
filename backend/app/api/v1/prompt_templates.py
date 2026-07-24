"""AI 提示词管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.core.database import get_db
from app.models.prompt_templates import PromptTemplate
from app.schemas import MessageResponse
from app.services.ai.prompt_service import get_prompt, create_prompt, list_prompts, delete_prompt

router = APIRouter(prefix="/ai/prompts", tags=["AI-提示词管理"])


class PromptCreate(BaseModel):
    type: str
    content: str
    name: str | None = None
    description: str | None = None


class PromptTestRequest(BaseModel):
    type: str
    content: str


class PromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    name: str | None
    content: str
    version: int
    description: str | None
    created_at: datetime | None = None

@router.post("/test")
def test_prompt(
    data: PromptTestRequest,
    db: Session = Depends(get_db),
):
    """用最近真实场次数据测试提示词效果"""
    from app.models.live_sessions import LiveSession
    from app.models.transcript_segments import TranscriptSegment
    from app.models.comments import Comment
    from app.prompts import get_system_prompt
    from app.services.ai.deepseek_client import chat_json

    # 找最近一场有完整数据的已结束场次
    recent = (
        db.query(LiveSession)
        .filter(
            LiveSession.live_status == "ended",
            LiveSession.detail_collection_status == "completed",
        )
        .order_by(LiveSession.live_end_time.desc())
        .first()
    )
    if not recent:
        raise HTTPException(400, "没有已结束的场次数据供测试")

    filled = data.content
    session_info = (
        f"场次ID: {recent.id}\n"
        f"主播: {recent.anchor_name or '未知'}\n"
        f"开播: {recent.live_start_time}\n"
        f"下播: {recent.live_end_time}\n"
        f"最高在线: {recent.peak_online_count or 0}\n"
        f"评论数: {recent.comments_count or 0}\n"
        f"新增关注: {recent.new_followers or 0}"
    )

    # 替换已知变量
    filled = filled.replace("{session_data}", session_info)

    if "{sessions_data}" in filled:
        sessions = (
            db.query(LiveSession)
            .filter(LiveSession.live_status == "ended")
            .order_by(LiveSession.live_start_time.desc())
            .limit(5)
            .all()
        )
        import json
        sessions_list = []
        for s in sessions:
            sessions_list.append({
                "id": s.id, "anchor": s.anchor_name or "",
                "peak_online": s.peak_online_count or 0,
                "comments": s.comments_count or 0,
                "followers": s.new_followers or 0,
            })
        filled = filled.replace(
            "{sessions_data}", json.dumps(sessions_list, ensure_ascii=False, indent=2)
        )

    if "{history_data}" in filled:
        import json
        history = (
            db.query(LiveSession)
            .filter(LiveSession.live_status == "ended", LiveSession.id != recent.id)
            .order_by(LiveSession.live_start_time.desc())
            .limit(10)
            .all()
        )
        hlist = [
            {"id": s.id, "peak_online": s.peak_online_count or 0, "comments": s.comments_count or 0}
            for s in history
        ]
        filled = filled.replace("{history_data}", json.dumps(hlist, ensure_ascii=False, indent=2))

    if "{transcript}" in filled:
        segs = (
            db.query(TranscriptSegment)
            .filter(
                TranscriptSegment.session_id == recent.id,
                TranscriptSegment.asr_status == "completed",
            )
            .order_by(TranscriptSegment.segment_start.asc())
            .limit(30)
            .all()
        )
        txt = "\n".join(
            f"[{s.segment_start:.1f}s] {s.text_content or ''}" for s in segs if s.text_content
        )
        filled = filled.replace("{transcript}", txt or "[暂无话术数据]")

    if "{comments}" in filled:
        comments = (
            db.query(Comment)
            .filter(Comment.session_id == recent.id)
            .order_by(Comment.comment_time.asc())
            .limit(30)
            .all()
        )
        clist = "\n".join(
            f"{c.user_nickname}: {c.comment_content or ''}" for c in comments
        )
        filled = filled.replace("{comments}", clist or "[暂无评论数据]")

    if "{knowledge_context}" in filled:
        from app.models.knowledge_base import KnowledgeBase
        kb = (
            db.query(KnowledgeBase)
            .filter(KnowledgeBase.session_id == recent.id)
            .order_by(KnowledgeBase.id.desc())
            .limit(5)
            .all()
        )
        ktxt = "\n".join(f"[{k.category}] {k.content or ''}" for k in kb)
        filled = filled.replace("{knowledge_context}", ktxt or "[暂无知识库数据]")

    filled = filled.replace("{question}", "测试：最近一场直播的数据表现如何？")
    filled = filled.replace("{speech_data}", "[测试模式：话术评分数据已省略]")
    filled = filled.replace("{session_id}", str(recent.id))

    try:
        system = get_system_prompt(data.type)
        result = chat_json(
            system_prompt=system,
            user_message=filled,
            temperature=0.3,
            operation="prompt_test",
        )
    except Exception as e:
        return {"filled_prompt": filled[:2000], "error": str(e)}

    return {"filled_prompt": filled[:2000], "result": result}


@router.get("/", response_model=list[PromptResponse])
def list_prompt_templates(
    type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """列出提示词模板"""
    return list_prompts(db, type=type, skip=skip, limit=limit)


@router.get("/{type}/latest", response_model=PromptResponse)
def get_latest_prompt(type: str, db: Session = Depends(get_db)):
    """获取最新版本提示词"""
    content = get_prompt(db, type)
    if not content:
        raise HTTPException(404, f"未找到类型 {type} 的提示词模板")
    t = db.query(PromptTemplate).filter(PromptTemplate.type == type).order_by(PromptTemplate.version.desc()).first()
    return t


@router.get("/active", response_model=list[PromptResponse])
def get_active_prompts(db: Session = Depends(get_db)):
    """返回项目注册的所有类型的最新版提示词"""
    from app.prompts import DEFAULT_PROMPTS
    results: list[PromptTemplate] = []
    for definition in DEFAULT_PROMPTS:
        t = db.query(PromptTemplate).filter(
            PromptTemplate.type == definition.type
        ).order_by(PromptTemplate.version.desc()).first()
        if t:
            results.append(t)
    return results


@router.get("/{prompt_id}", response_model=PromptResponse)
def get_prompt_by_id(prompt_id: int, db: Session = Depends(get_db)):
    """按 ID 获取单条提示词"""
    t = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    if not t:
        raise HTTPException(404, "提示词不存在")
    return t


@router.put("/{prompt_id}", response_model=PromptResponse)
def update_prompt_template(prompt_id: int, data: PromptCreate, db: Session = Depends(get_db)):
    """编辑提示词 — 自动创建新版本，保留旧版本历史"""
    existing = db.query(PromptTemplate).filter(PromptTemplate.id == prompt_id).first()
    if not existing:
        raise HTTPException(404, "原始提示词不存在")
    return create_prompt(db, type=data.type, content=data.content,
                          name=data.name or existing.name,
                          description=data.description or existing.description)


@router.post("/", response_model=PromptResponse)
def create_prompt_template(data: PromptCreate, db: Session = Depends(get_db)):
    """创建新版本提示词"""
    return create_prompt(db, type=data.type, content=data.content,
                          name=data.name, description=data.description)


@router.delete("/{prompt_id}", response_model=MessageResponse)
def delete_prompt_template(prompt_id: int, db: Session = Depends(get_db)):
    """删除提示词模板"""
    if not delete_prompt(db, prompt_id):
        raise HTTPException(404, "提示词模板不存在")
    return {"message": "删除成功"}
