"""
直播采集调度管理器 — 基于 apscheduler AsyncIOScheduler

管理所有定时任务的注册、启动、停止。
"""
from typing import Optional
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logger import logger
from app.models.scraper_tasks import ScraperTask
from app.services.collector.browser import browser_manager


class SchedulerManager:
    """全局采集调度管理器单例"""

    _instance: Optional["SchedulerManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._scheduler = None
            cls._instance._running = False
            cls._instance._session_jobs: dict[int, dict[str, str]] = {}
            cls._instance._collector_factory = None
            cls._instance._last_error = None
        return cls._instance

    def set_collector_factory(self, factory):
        """设置采集器工厂（用于 Mock 注入）"""
        self._collector_factory = factory

    async def start(self):
        """启动调度器"""
        if self._running:
            return

        self._scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

        # 全局监控 job
        self._scheduler.add_job(
            self._monitor_check,
            IntervalTrigger(seconds=max(settings.MONITOR_CHECK_INTERVAL, 30)),
            id="monitor_check",
            replace_existing=True,
            misfire_grace_time=30,
        )

        # 清理过期 job
        self._scheduler.add_job(
            self._cleanup_expired,
            CronTrigger(hour=3, minute=0),
            id="cleanup_expired",
            replace_existing=True,
        )

        self._scheduler.start()
        self._running = True
        self._last_error = None
        logger.info("SchedulerManager 已启动")

    async def stop(self):
        """停止调度器"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._running = False
        self._session_jobs.clear()
        logger.info("SchedulerManager 已停止")

    @property
    def running(self) -> bool:
        return self._running

    def add_session_jobs(self, session_id: int, dashboard_url: str):
        """开播后注册该 session 的所有采集任务"""
        if session_id in self._session_jobs:
            return

        jobs = {}
        for job_type, interval in [
            ("metrics", max(settings.METRICS_COLLECT_INTERVAL, 10)),
            ("comments", max(settings.COMMENT_COLLECT_INTERVAL, 20)),
            ("profiles", max(settings.PROFILE_COLLECT_INTERVAL, 30)),
        ]:
            job_id = f"{job_type}_{session_id}"
            self._scheduler.add_job(
                self._collect_wrapper,
                IntervalTrigger(seconds=interval),
                id=job_id,
                args=[session_id, dashboard_url, job_type],
                replace_existing=True,
                misfire_grace_time=15,
            )
            jobs[job_type] = job_id

        # 流刷新 job
        refresh_id = f"stream_refresh_{session_id}"
        self._scheduler.add_job(
            self._collect_wrapper,
            IntervalTrigger(seconds=300),
            id=refresh_id,
            args=[session_id, dashboard_url, "stream_refresh"],
            replace_existing=True,
            misfire_grace_time=30,
        )
        jobs["stream_refresh"] = refresh_id

        self._session_jobs[session_id] = jobs
        logger.info(f"已注册 session {session_id} 的采集任务: {list(jobs.keys())}")

    def remove_session_jobs(self, session_id: int):
        """下播后移除该 session 的所有采集任务"""
        jobs = self._session_jobs.pop(session_id, {})
        for job_id in jobs.values():
            try:
                self._scheduler.remove_job(job_id)
            except Exception:
                pass
        logger.info(f"已移除 session {session_id} 的采集任务")

    def get_active_sessions(self) -> list[int]:
        """获取所有活跃的 session_id 列表"""
        return list(self._session_jobs.keys())

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    async def _monitor_check(self):
        """开播检测任务"""
        from app.core.database import SessionLocal
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession
        from app.services.collector.monitor import MockLiveDetector, CluerichLiveDetector

        db = SessionLocal()
        try:
            if settings.MONITOR_MOCK_MODE:
                detector = MockLiveDetector()
            else:
                detector = CluerichLiveDetector()

            rooms = db.query(LiveRoom).filter(LiveRoom.status == True).all()
            self._last_error = None
            for room in rooms:
                room_id_for_url = room.room_id_str or str(room.id)
                dashboard_url = f"https://leads.cluerich.com/pc/analysis/live-screen?room_id={room_id_for_url}" if not settings.MONITOR_MOCK_MODE else ""
                result = await detector.detect(dashboard_url)

                detection_error = (result.raw_data or {}).get("error")
                if detection_error:
                    self._last_error = str(detection_error)[:500]
                    logger.error("直播监控检测失败 room=%s: %s", room.id, self._last_error)
                    continue
                active_session = db.query(LiveSession).filter(
                    LiveSession.room_id == room.id,
                    LiveSession.live_status == "live",
                ).order_by(LiveSession.id.desc()).first()

                if result.is_live and not active_session:
                    await self._on_live_start(db, room, result)
                elif result.is_live and active_session and active_session.id not in self._session_jobs:
                    self.add_session_jobs(active_session.id, active_session.dashboard_url or dashboard_url)
                elif not result.is_live and active_session:
                    await self._on_live_end(db, room)
        except Exception as e:
            self._last_error = str(e)[:500]
            logger.error(f"monitor_check 异常: {e}")
        finally:
            db.close()

    async def _on_live_start(self, db: Session, room, result):
        """开播事件处理"""
        from app.models.live_sessions import LiveSession
        from app.services.collector.end_live import process_live_end

        session = LiveSession(
            room_id=room.id,
            session_title=result.session_title or f"{room.anchor_name} 直播",
            live_start_time=result.start_time or datetime.utcnow(),
            live_status="live",
            dashboard_url=f"https://leads.cluerich.com/pc/analysis/live-screen?room_id={room.room_id_str or room.id}",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        self.add_session_jobs(session.id, session.dashboard_url or "")
        logger.info(f"开播! room={room.id} session={session.id}")

    async def _on_live_end(self, db: Session, room):
        """下播事件处理"""
        from app.models.live_sessions import LiveSession

        active_session = db.query(LiveSession).filter(
            LiveSession.room_id == room.id,
            LiveSession.live_status == "live",
        ).first()
        if active_session:
            await process_live_end(db, active_session.id)
            self.remove_session_jobs(active_session.id)

    async def _collect_wrapper(self, session_id: int, dashboard_url: str, job_type: str):
        """统一采集包装器 — 异常处理 + 任务记录"""
        db = SessionLocal()
        task = None
        try:
            task = ScraperTask(
                session_id=session_id,
                task_type=job_type,
                status="running",
                started_at=datetime.utcnow(),
            )
            db.add(task)
            db.commit()
            db.refresh(task)

            context, is_valid, message = await browser_manager.get_logged_in_context()
            if not is_valid or not context:
                raise RuntimeError(message or "采集账号登录状态不可用")
            from app.services.collector.live_collector import (
                MetricsCollector, CommentCollector, ProfileCollector,
            )

            collector_map = {
                "metrics": MetricsCollector,
                "comments": CommentCollector,
                "profiles": ProfileCollector,
            }

            if job_type == "stream_refresh":
                from app.services.collector.stream_collector import StreamCollector

                stream_url = await StreamCollector(db, context).fetch_stream_url(dashboard_url, session_id)
                if stream_url:
                    from app.models.live_sessions import LiveSession

                    session = db.query(LiveSession).get(session_id)
                    if session:
                        session.stream_url = stream_url[:2000]
                        db.commit()
            else:
                collector_cls = collector_map.get(job_type)
                if not collector_cls:
                    raise ValueError(f"未知采集任务类型: {job_type}")
                collector = collector_cls(db, context, task, dashboard_url)
                result = await collector.collect()
                await _save_collected_data(db, session_id, job_type, result)
                await collector.close()

            task.status = "completed"
            task.completed_at = datetime.utcnow()
            db.commit()
        except Exception as e:
            logger.error(f"采集失败 [{job_type}/{session_id}]: {e}")
            if task:
                task.status = "failed"
                task.error_message = str(e)[:200]
                db.commit()
        finally:
            db.close()

    async def _cleanup_expired(self):
        """清理过期 session"""
        db = SessionLocal()
        try:
            from app.models.live_sessions import LiveSession
            expired = db.query(LiveSession).filter(
                LiveSession.live_status == "live",
                LiveSession.live_start_time.isnot(None),
            ).all()
            for s in expired:
                # 如果开播超过 12 小时没有下播标记，自动结束
                if s.live_start_time and (datetime.utcnow() - s.live_start_time).total_seconds() > 43200:
                    from app.services.collector.end_live import process_live_end
                    await process_live_end(db, s.id)
                    self.remove_session_jobs(s.id)
        finally:
            db.close()


async def _save_collected_data(db: Session, session_id: int, job_type: str, result: dict):
    """将采集结果存入对应数据表"""
    from app.models.live_metrics import LiveMetric
    from app.models.comments import Comment
    from app.models.live_audience_profiles import LiveAudienceProfile

    if job_type == "metrics" and result:
        metric = LiveMetric(
            session_id=session_id,
            metric_time=datetime.utcnow(),
            online_count=result.get("online_count"),
            exposure_count=result.get("exposure_count"),
            enter_count=result.get("enter_count"),
            like_count=result.get("like_count"),
            comment_count=result.get("comment_count"),
            follow_count=result.get("follow_count"),
        )
        db.add(metric)
        db.commit()

    elif job_type == "comments" and result.get("comments"):
        existing_pairs = {
            ((row.user_nickname or "").strip(), (row.comment_content or "").strip())
            for row in db.query(Comment).filter(Comment.session_id == session_id).all()
        }
        for c in result["comments"]:
            nickname = (c.get("user_nickname", c.get("nickname")) or "").strip()
            content = (c.get("comment_content", c.get("content")) or "").strip()
            if not content or (nickname, content) in existing_pairs:
                continue
            comment = Comment(
                session_id=session_id,
                user_nickname=nickname or None,
                comment_content=content,
                comment_time=c.get("comment_time") or datetime.utcnow(),
            )
            db.add(comment)
            existing_pairs.add((nickname, content))
        db.commit()

    elif job_type == "profiles" and result.get("profiles"):
        # 全量替换
        db.query(LiveAudienceProfile).filter(
            LiveAudienceProfile.session_id == session_id
        ).delete()
        for p in result["profiles"]:
            profile = LiveAudienceProfile(
                session_id=session_id,
                dimension_type=p.get("dimension_type"),
                dimension_name=p.get("dimension_name"),
                ratio=p.get("ratio", 0),
                count=p.get("count", 0),
            )
            db.add(profile)
        db.commit()


# 全局单例
scheduler_manager = SchedulerManager()

# 在模块末尾导入，避免循环引用
from app.services.collector.monitor import LiveStatusResult as _LSR  # noqa: F401
