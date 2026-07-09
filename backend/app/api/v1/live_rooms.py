"""直播间 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_rooms import LiveRoom
from app.schemas import (
    LiveRoomCreate,
    LiveRoomUpdate,
    LiveRoomResponse,
)

router = APIRouter(prefix="/live-rooms", tags=["直播间"])


@router.get("/", response_model=list[LiveRoomResponse])
def list_rooms(db: Session = Depends(get_db)):
    """获取所有直播间"""
    return db.query(LiveRoom).all()


@router.get("/{room_id}", response_model=LiveRoomResponse)
def get_room(room_id: int, db: Session = Depends(get_db)):
    """获取单个直播间"""
    room = db.query(LiveRoom).get(room_id)
    if not room:
        raise HTTPException(404, "直播间不存在")
    return room


@router.post("/", response_model=LiveRoomResponse)
def create_room(data: LiveRoomCreate, db: Session = Depends(get_db)):
    """创建直播间"""
    room = LiveRoom(**data.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.put("/{room_id}", response_model=LiveRoomResponse)
def update_room(room_id: int, data: LiveRoomUpdate, db: Session = Depends(get_db)):
    """更新直播间"""
    room = db.query(LiveRoom).get(room_id)
    if not room:
        raise HTTPException(404, "直播间不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(room, key, val)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    """删除直播间"""
    room = db.query(LiveRoom).get(room_id)
    if not room:
        raise HTTPException(404, "直播间不存在")
    db.delete(room)
    db.commit()
    return {"message": "删除成功"}
