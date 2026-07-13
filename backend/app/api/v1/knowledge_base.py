"""知识库 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.schemas import KnowledgeBaseCreate, KnowledgeBaseResponse

router = APIRouter(prefix="/knowledge-base", tags=["知识库"])


@router.get("/", response_model=list[KnowledgeBaseResponse])
def list_knowledge(
    category: str | None = Query(None),
    source_type: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取知识库列表"""
    q = db.query(KnowledgeBase)
    if category:
        q = q.filter(KnowledgeBase.category == category)
    if source_type:
        q = q.filter(KnowledgeBase.source_type == source_type)
    return q.order_by(KnowledgeBase.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge(kb_id: int, db: Session = Depends(get_db)):
    k = db.get(KnowledgeBase, kb_id)
    if not k:
        raise HTTPException(404, "知识条目不存在")
    return k


@router.post("/", response_model=KnowledgeBaseResponse)
def create_knowledge(data: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    k = KnowledgeBase(**data.model_dump())
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


@router.delete("/{kb_id}")
def delete_knowledge(kb_id: int, db: Session = Depends(get_db)):
    k = db.get(KnowledgeBase, kb_id)
    if not k:
        raise HTTPException(404, "知识条目不存在")
    db.delete(k)
    db.commit()
    return {"message": "删除成功"}
