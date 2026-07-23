"""旧进程实时采集任务回收测试。"""

from datetime import datetime, timedelta

from app.core.status import TaskStatus
from app.models.scraper_tasks import ScraperTask
from app.services.tasks.recovery import recover_orphaned_monitor_tasks


def _running_task(task_id: int, *, worker_id: str, age_seconds: int) -> ScraperTask:
    started_at = datetime.utcnow() - timedelta(seconds=age_seconds)
    return ScraperTask(
        id=task_id,
        task_type="live_detail",
        status=TaskStatus.RUNNING,
        started_at=started_at,
        heartbeat_at=started_at,
        worker_id=worker_id,
    )


def test_recover_orphaned_monitor_tasks_marks_old_process_task_failed(db):
    stale = _running_task(1, worker_id="monitor:test-host:1001", age_seconds=300)
    db.add(stale)
    db.commit()

    recovered = recover_orphaned_monitor_tasks(
        db,
        current_pid=2002,
        stale_after_seconds=120,
    )

    db.refresh(stale)
    assert [task.id for task in recovered] == [stale.id]
    assert stale.status == TaskStatus.FAILED
    assert stale.progress_stage == "interrupted"
    assert stale.worker_id is None
    assert stale.completed_at is not None


def test_recover_orphaned_monitor_tasks_keeps_current_and_fresh_tasks(db):
    current_process = _running_task(1, worker_id="monitor:test-host:2002", age_seconds=300)
    fresh_old_process = _running_task(2, worker_id="monitor:test-host:1001", age_seconds=30)
    db.add_all([current_process, fresh_old_process])
    db.commit()

    recovered = recover_orphaned_monitor_tasks(
        db,
        current_pid=2002,
        stale_after_seconds=120,
    )

    db.refresh(current_process)
    db.refresh(fresh_old_process)
    assert recovered == []
    assert current_process.status == TaskStatus.RUNNING
    assert fresh_old_process.status == TaskStatus.RUNNING
