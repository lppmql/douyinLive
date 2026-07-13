"""用户画像同步 — live_audience_profiles → de_anchor_audience_profile"""
from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.live_audience_profiles import LiveAudienceProfile
from app.models.de_tables import DeAnchorAudienceProfile


def sync_audience_profiles(db, session_id: int):
    """同步用户画像数据"""
    # 先删除旧数据
    db.query(DeAnchorAudienceProfile).filter(
        DeAnchorAudienceProfile.session_id == session_id
    ).delete()

    session = db.query(LiveSession).get(session_id)
    room = db.query(LiveRoom).get(session.room_id) if session and session.room_id else None
    anchor_name = (session.anchor_name or (room.anchor_name if room else None)) if session else None
    session_title = session.session_title if session else None

    profiles = db.query(LiveAudienceProfile).filter(
        LiveAudienceProfile.session_id == session_id
    ).all()

    for p in profiles:
        dp = DeAnchorAudienceProfile(
            session_id=session_id,
            anchor_name=anchor_name,
            session_title=session_title,
            dimension_type=p.dimension_type,
            dimension_name=p.dimension_name,
            ratio=float(p.ratio or 0),
            count=p.count or 0,
        )
        db.add(dp)

    logger.info(f"  audience_profiles: {len(profiles)} 条")
