"""评论 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.comments import Comment
from app.schemas import CommentCreate, CommentResponse

router = APIRouter(prefix="/comments", tags=["评论"])


@router.get("/", response_model=list[CommentResponse])
def list_comments(
    session_id: int | None = Query(None),
    is_high_intent: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取评论列表"""
    q = db.query(Comment)
    if session_id:
        q = q.filter(Comment.session_id == session_id)
    if is_high_intent is not None:
        q = q.filter(Comment.is_high_intent == is_high_intent)
    return q.order_by(Comment.comment_time.desc()).offset(skip).limit(limit).all()


@router.get("/{comment_id}", response_model=CommentResponse)
def get_comment(comment_id: int, db: Session = Depends(get_db)):
    c = db.query(Comment).get(comment_id)
    if not c:
        raise HTTPException(404, "评论不存在")
    return c


@router.post("/", response_model=CommentResponse)
def create_comment(data: CommentCreate, db: Session = Depends(get_db)):
    c = Comment(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{comment_id}")
def delete_comment(comment_id: int, db: Session = Depends(get_db)):
    c = db.query(Comment).get(comment_id)
    if not c:
        raise HTTPException(404, "评论不存在")
    db.delete(c)
    db.commit()
    return {"message": "删除成功"}
