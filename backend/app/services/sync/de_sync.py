"""
DataEase 同步主入口

用法:
    from app.services.sync import sync_all, sync_session

    sync_all(db)          # 全量同步
    sync_session(db, 1)   # 单场同步（下播时触发）
"""
from app.core.logger import logger
from app.models.live_sessions import LiveSession
from app.services.sync.session_sync import sync_session_summary, sync_realtime_metrics, sync_conversion_funnel
from app.services.sync.profile_sync import sync_audience_profiles
from app.services.sync.comment_sync import sync_comment_summary
from app.services.sync.transcript_sync import sync_transcript_summary


def sync_session(db, session_id: int):
    """同步单场直播的所有 de_ 数据（下播时调用）"""
    logger.info(f"开始同步 session {session_id} 到 de_ 表")
    sync_session_summary(db, session_id)
    sync_realtime_metrics(db, session_id)
    sync_conversion_funnel(db, session_id)
    sync_audience_profiles(db, session_id)
    sync_comment_summary(db, session_id)
    sync_transcript_summary(db, session_id)
    db.commit()
    logger.info(f"session {session_id} 同步完成")


def sync_all(db):
    """全量同步所有直播场次数据到 de_ 表"""
    session_ids = [row[0] for row in db.query(LiveSession.id).all()]
    logger.info(f"开始全量同步，共 {len(session_ids)} 个场次")

    for sid in session_ids:
        try:
            sync_session(db, sid)
        except Exception as e:
            logger.error(f"同步 session {sid} 失败: {e}")
            db.rollback()

    logger.info("全量同步完成")
