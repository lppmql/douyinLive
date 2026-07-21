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


class PromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    name: str | None
    content: str
    version: int
    description: str | None
    created_at: datetime | None = None

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
