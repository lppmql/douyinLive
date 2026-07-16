"""直播场次 CRUD API"""
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.live_metrics import LiveMetric
from app.models.comments import Comment
from app.models.stream_sources import StreamSource
from app.models.live_audience_profiles import LiveAudienceProfile
from app.services.collector.video_download import (
    build_video_download_command,
    build_browser_playback_command,
    stream_browser_playback,
    stream_video_as_mp4,
    video_download_semaphore,
)
from app.schemas import (
    LiveMetricDetailResponse,
    LiveSessionCreate,
    LiveSessionDetailResponse,
    LiveSessionListItemResponse,
    LiveSessionPageResponse,
    LiveSessionResponse,
    LiveSessionUpdate,
)

router = APIRouter(prefix="/live-sessions", tags=["直播场次"])
MAX_AVATAR_BYTES = 2 * 1024 * 1024
LIVE_SESSION_LIST_COLUMNS = (
    LiveSession.id,
    LiveSession.anchor_name,
    LiveSession.anchor_nickname,
    LiveSession.anchor_avatar_url,
    LiveSession.douyin_id,
    LiveSession.session_title,
    LiveSession.detail_collection_status,
    LiveSession.detail_collection_error,
    LiveSession.live_start_time,
    LiveSession.live_end_time,
    LiveSession.live_duration_seconds,
    LiveSession.live_status,
    LiveSession.peak_online_count,
    LiveSession.new_followers,
    LiveSession.comments_count,
    LiveSession.leads_count,
)


def _attach_room_profile(session: LiveSession) -> dict:
    """将 LiveRoom 上的主播资料注入到场次返回数据中。"""
    data = {c.name: getattr(session, c.name) for c in session.__table__.columns}
    # 企业主账号下一个入口对应多个主播，不能把未映射场次伪装成入口账号主播。
    data["anchor_name"] = session.anchor_name
    data["anchor_nickname"] = session.anchor_nickname
    data["anchor_avatar_url"] = session.anchor_avatar_url
    data["douyin_id"] = session.douyin_id
    data["douyin_uid"] = session.douyin_uid
    return data


def _is_allowed_avatar_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and hostname.endswith(".douyinpic.com")


@router.get("/page", response_model=LiveSessionPageResponse)
def page_sessions(
    current: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    anchor_name: str | None = Query(None),
    live_status: str | None = Query(None),
    detail_status: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """按 SoybeanAdmin 分页结构返回全部直播场次。"""
    query = db.query(*LIVE_SESSION_LIST_COLUMNS)
    if anchor_name:
        query = query.filter(LiveSession.anchor_name.like(f"%{anchor_name.strip()}%"))
    if live_status:
        query = query.filter(LiveSession.live_status == live_status)
    if detail_status:
        query = query.filter(LiveSession.detail_collection_status == detail_status)

    total = query.with_entities(LiveSession.id).order_by(None).count()
    sessions = (
        query.order_by(LiveSession.live_start_time.desc(), LiveSession.id.desc())
        .offset((current - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "records": [LiveSessionListItemResponse(**session._mapping) for session in sessions],
        "total": total,
        "current": current,
        "size": size,
    }


@router.get("/", response_model=list[LiveSessionResponse])
def list_sessions(
    room_id: int | None = Query(None, description="按直播间筛选"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取直播场次列表"""
    q = db.query(LiveSession)
    if room_id:
        q = q.filter(LiveSession.room_id == room_id)
    sessions = q.order_by(LiveSession.live_start_time.desc()).offset(skip).limit(limit).all()
    return [LiveSessionResponse(**_attach_room_profile(s)) for s in sessions]


@router.get("/{session_id}/details", response_model=LiveSessionDetailResponse)
def get_session_details(
    session_id: int,
    comment_limit: int = Query(300, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取单场直播的大屏趋势、已采集评论和可用流地址。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")

    metrics = (
        db.query(LiveMetric)
        .filter(LiveMetric.session_id == session_id)
        .order_by(LiveMetric.metric_time.asc())
        .all()
    )
    comments = (
        db.query(Comment)
        .filter(Comment.session_id == session_id)
        .order_by(Comment.comment_time.desc(), Comment.id.desc())
        .limit(comment_limit)
        .all()
    )
    stream_sources = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id)
        .order_by(StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .all()
    )
    latest_stream = next((item.m3u8_url for item in stream_sources if item.status == "active"), None)
    profiles = (
        db.query(LiveAudienceProfile)
        .filter(LiveAudienceProfile.session_id == session_id)
        .order_by(LiveAudienceProfile.dimension_type, LiveAudienceProfile.ratio.desc())
        .all()
    )

    return LiveSessionDetailResponse(
        session=LiveSessionResponse(**_attach_room_profile(session)),
        metrics=[LiveMetricDetailResponse.model_validate(item, from_attributes=True) for item in metrics],
        comments=comments,
        profiles=profiles,
        stream_url=latest_stream or session.stream_url,
        stream_source_count=len(stream_sources),
    )


@router.get("/{session_id}/avatar")
def get_session_avatar(session_id: int, db: Session = Depends(get_db)):
    """同源返回已采集的抖音主播头像，避免 CDN 限制浏览器跨站嵌入。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")

    avatar_url = session.anchor_avatar_url
    if not avatar_url:
        raise HTTPException(404, "该场次暂无主播头像")
    if not _is_allowed_avatar_url(avatar_url):
        raise HTTPException(400, "主播头像地址不受信任")

    try:
        upstream = httpx.get(
            avatar_url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://live.douyin.com/"},
            follow_redirects=False,
            timeout=10,
        )
        upstream.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "主播头像读取失败") from exc

    content_type = upstream.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(502, "主播头像响应格式无效")
    if len(upstream.content) > MAX_AVATAR_BYTES:
        raise HTTPException(502, "主播头像文件过大")

    return Response(
        content=upstream.content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{session_id}/video")
def download_session_video(session_id: int, db: Session = Depends(get_db)):
    """把已结束场次的 m3u8 原码流封装为 MP4 流，不执行高开销转码。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")
    if session.live_status == "live":
        raise HTTPException(409, "直播仍在进行，请等待下播后再下载完整视频")
    if video_download_semaphore.locked():
        raise HTTPException(429, "当前已有视频正在下载，请完成后再试")

    source = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id)
        .order_by((StreamSource.status == "active").desc(), StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    stream_url = (source.m3u8_url if source else None) or session.stream_url
    if not stream_url:
        raise HTTPException(404, "该场次暂无 m3u8 地址，请先刷新采集")
    headers = dict(source.headers_json or {}) if source else {}
    try:
        build_video_download_command(stream_url, headers)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    iterator = stream_video_as_mp4(stream_url, headers)

    filename = f"live-session-{session_id}.mp4"
    return StreamingResponse(
        iterator,
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/playback")
def playback_session_video(
    session_id: int,
    start_seconds: float = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """将真实 H.265 回放按需转换为浏览器兼容的 H.264 流。"""
    session = db.get(LiveSession, session_id)
    if not session:
        raise HTTPException(404, "直播场次不存在")
    source = (
        db.query(StreamSource)
        .filter(StreamSource.session_id == session_id)
        .order_by((StreamSource.status == "active").desc(), StreamSource.fetched_at.desc(), StreamSource.id.desc())
        .first()
    )
    stream_url = (source.m3u8_url if source else None) or session.stream_url
    if not stream_url:
        raise HTTPException(404, "该场次暂无可回放地址，请先刷新采集")
    headers = dict(source.headers_json or {}) if source else {}
    try:
        build_browser_playback_command(stream_url, headers, start_seconds, encoder="h264_videotoolbox")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return StreamingResponse(
        stream_browser_playback(stream_url, headers, start_seconds, session_id),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'inline; filename="live-session-{session_id}.mp4"',
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}", response_model=LiveSessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """获取单个直播场次"""
    s = db.get(LiveSession, session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    return LiveSessionResponse(**_attach_room_profile(s))


@router.post("/", response_model=LiveSessionResponse)
def create_session(data: LiveSessionCreate, db: Session = Depends(get_db)):
    """创建直播场次"""
    s = LiveSession(**data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.put("/{session_id}", response_model=LiveSessionResponse)
def update_session(session_id: int, data: LiveSessionUpdate, db: Session = Depends(get_db)):
    """更新直播场次"""
    s = db.get(LiveSession, session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(s, key, val)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """删除直播场次"""
    s = db.get(LiveSession, session_id)
    if not s:
        raise HTTPException(404, "直播场次不存在")
    db.delete(s)
    db.commit()
    return {"message": "删除成功"}
