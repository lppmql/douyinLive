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
            cls._instance._paused_for_collection = False
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
            next_run_time=datetime.now(),
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
        self._paused_for_collection = False
        logger.info("SchedulerManager 已启动")

    async def stop(self):
        """仅停止实时监控任务；共享浏览器由应用生命周期统一管理。"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._running = False
        self._paused_for_collection = False
        self._session_jobs.clear()
        logger.info("SchedulerManager 已停止")

    @property
    def running(self) -> bool:
        return self._running

    def add_session_jobs(self, session_id: int, dashboard_url: str):
        """开播后注册该 session 的所有采集任务"""
        if session_id in self._session_jobs:
            return

        # 指标、趋势、评论和主播信息通过同一个大屏页面统一采集，避免多个页面
        # 并发争用同一个登录上下文，也确保实时链路与刷新采集使用相同数据结构。
        jobs = {}
        detail_id = f"live_detail_{session_id}"
        self._scheduler.add_job(
            self._collect_wrapper,
            IntervalTrigger(seconds=max(settings.METRICS_COLLECT_INTERVAL, 30)),
            id=detail_id,
            args=[session_id, dashboard_url, "live_detail"],
            replace_existing=True,
            misfire_grace_time=20,
            max_instances=1,
            coalesce=True,
        )
        jobs["live_detail"] = detail_id

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

    @property
    def paused_for_collection(self) -> bool:
        """全量刷新接管浏览器期间，监控服务保持开启但不重复采集。"""
        return self._paused_for_collection

    def resume_after_collection(self) -> None:
        """全量刷新结束后立即唤醒监控，不等待下一个轮询周期。"""
        self._paused_for_collection = False
        if not self._running or not self._scheduler or not self._scheduler.running:
            return
        job = self._scheduler.get_job("monitor_check")
        if job:
            job.modify(next_run_time=datetime.now())

    @staticmethod
    def _has_running_full_collection(db: Session) -> bool:
        return db.query(ScraperTask.id).filter(
            ScraperTask.task_type == "collect_all",
            ScraperTask.status == "running",
        ).first() is not None

    async def _monitor_check(self):
        """开播检测任务"""
        from app.core.database import SessionLocal
        from app.models.live_rooms import LiveRoom
        from app.models.live_sessions import LiveSession
        from app.services.collector.monitor import MockLiveDetector

        db = SessionLocal()
        try:
            if self._has_running_full_collection(db):
                if not self._paused_for_collection:
                    logger.info("刷新数据采集正在运行，实时监控保持开启并暂缓重复浏览器任务")
                self._paused_for_collection = True
                self._last_error = None
                return
            self._paused_for_collection = False
            rooms = db.query(LiveRoom).filter(LiveRoom.status == True).all()
            self._last_error = None
            for room in rooms:
                if not settings.MONITOR_MOCK_MODE:
                    await self._monitor_enterprise_room(db, room)
                    continue

                detector = MockLiveDetector()
                dashboard_url = ""
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

    async def _monitor_enterprise_room(self, db: Session, room):
        """按企业账号下的全部主播同步当前开播场次。"""
        from app.models.live_sessions import LiveSession
        from app.services.collector.manual_collect import discover_enterprise_live_sessions

        context, is_valid, message = await browser_manager.get_logged_in_context()
        if not is_valid or not context:
            raise RuntimeError(message or "采集账号登录状态不可用")

        live_items = await discover_enterprise_live_sessions(context, room)
        live_urls = {item["dashboard_url"] for item in live_items}
        for item in live_items:
            session = db.query(LiveSession).filter(
                LiveSession.room_id == room.id,
                LiveSession.dashboard_url == item["dashboard_url"],
            ).first()
            if session is None:
                session = LiveSession(room_id=room.id, dashboard_url=item["dashboard_url"])
                db.add(session)

            session.live_status = "live"
            session.session_title = item.get("session_title") or session.session_title or "直播场次"
            session.live_start_time = item.get("live_start_time") or session.live_start_time or datetime.now()
            for field in ("anchor_name", "anchor_nickname", "anchor_avatar_url", "douyin_id", "douyin_uid"):
                value = item.get(field)
                if value:
                    setattr(session, field, value)
            db.commit()
            db.refresh(session)
            if session.id not in self._session_jobs:
                self.add_session_jobs(session.id, session.dashboard_url)

        active_sessions = db.query(LiveSession).filter(
            LiveSession.room_id == room.id,
            LiveSession.live_status == "live",
        ).all()
        for session in active_sessions:
            if session.dashboard_url not in live_urls:
                await self._end_live_session(db, session)

        logger.info(
            "企业直播监控完成: room=%s active_anchors=%s",
            room.id,
            len(live_items),
        )

    async def _on_live_start(self, db: Session, room, result):
        """开播事件处理"""
        from app.models.live_sessions import LiveSession

        session = LiveSession(
            room_id=room.id,
            session_title=result.session_title or f"{room.anchor_name} 直播",
            live_start_time=result.start_time or datetime.now(),
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
            await self._end_live_session(db, active_session)

    async def _end_live_session(self, db: Session, session):
        """结束指定场次，避免同一企业账号的多主播互相覆盖。"""
        from app.services.collector.end_live import process_live_end

        await process_live_end(db, session.id)
        self.remove_session_jobs(session.id)

    async def _collect_wrapper(self, session_id: int, dashboard_url: str, job_type: str):
        """统一采集包装器 — 异常处理 + 任务记录"""
        db = SessionLocal()
        task = None
        try:
            if self._has_running_full_collection(db):
                if not self._paused_for_collection:
                    logger.info("刷新数据采集已接管实时数据，本轮 %s 任务自动跳过", job_type)
                self._paused_for_collection = True
                return
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

                    session = db.get(LiveSession, session_id)
                    if session:
                        session.stream_url = stream_url[:2000]
                        db.commit()
            elif job_type == "live_detail":
                from app.models.live_sessions import LiveSession
                from app.services.collector.manual_collect import collect_live_session_snapshot

                session = db.get(LiveSession, session_id)
                if not session:
                    raise RuntimeError(f"直播场次不存在: {session_id}")
                result = await collect_live_session_snapshot(db, context, session)
                try:
                    from app.services.sync import sync_session

                    sync_session(db, session_id)
                    result["dataease_synced"] = True
                except Exception as sync_exc:
                    db.rollback()
                    result["dataease_synced"] = False
                    logger.exception("实时 DataEase 同步失败 session=%s: %s", session_id, sync_exc)
                task.progress_percent = 100
                task.progress_stage = "live_detail"
                task.progress_message = (
                    f"汇总字段 {result['overview_field_count']}，趋势 {result['trend_row_count']} 条，"
                    f"指标写入 {result['new_metric_count']} 条，评论记录 {result['new_comment_count']} 条，"
                    f"画像 {result['profile_count']} 条，DataEase {'已同步' if result['dataease_synced'] else '同步失败'}"
                )
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
                if s.live_start_time and (datetime.now() - s.live_start_time).total_seconds() > 43200:
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
