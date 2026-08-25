from types import SimpleNamespace

from sqlalchemy.dialects.mysql import LONGTEXT

from app.core.config import Settings
from app.models.knowledge_base import KnowledgeBase
from app.models.transcript_full_texts import TranscriptFullText
from app.services.asr.chunks import build_chunk_ranges, reconcile_existing_chunks
from app.services.asr.queue import (
    recover_interrupted_chunk,
    requeue_offline_task_for_live_priority,
    reset_failed_task_for_retry,
)
from app.services.asr.m3u8_pipe import M3u8Pipe, sanitize_ffmpeg_error
from app.services.tasks import runtime
from workers.asr_worker import build_chunk_failure_message, is_full_text_too_long_error


def test_build_chunk_ranges_covers_real_duration_without_overlap():
    assert build_chunk_ranges(0, 300) == [(0.0, None)]
    assert build_chunk_ranges(0, 120, is_live=True) == [(0.0, 120.0)]
    assert build_chunk_ranges(601, 300) == [
        (0.0, 300.0),
        (300.0, 600.0),
        (600.0, 601.0),
    ]


def test_reconcile_chunks_skips_ranges_beyond_corrected_live_duration():
    """场次时长被修正后，超出真实结尾的旧分片不能继续反复读取。"""
    chunks = [
        SimpleNamespace(
            id=index + 1,
            chunk_index=index,
            start_seconds=float(index * 120),
            end_seconds=float((index + 1) * 120),
            status="completed" if index < 44 else "failed",
            retry_count=1 if index < 44 else 2,
            segment_count=3 if index < 44 else 0,
            error_message=None if index < 44 else "旧流读取失败",
            completed_at="2026-07-27",
            worker_id="asr:old",
        )
        for index in range(59)
    ]

    missing_ranges = reconcile_existing_chunks(
        chunks,
        duration_seconds=5397,
        chunk_seconds=120,
        is_live=False,
    )

    assert missing_ranges == []
    assert chunks[44].end_seconds == 5397.0
    assert chunks[44].status == "pending"
    assert chunks[44].retry_count == 0
    assert chunks[50].status == "skipped"
    assert "超出真实直播时长" in chunks[50].error_message


def test_reconcile_live_chunk_replaces_infinite_range_with_two_minute_window():
    """直播中的实时任务必须有分片边界，资源保护和断点恢复才有机会生效。"""
    chunk = SimpleNamespace(
        id=3,
        chunk_index=0,
        start_seconds=0.0,
        end_seconds=None,
        status="pending",
        retry_count=0,
        segment_count=0,
        error_message=None,
        completed_at=None,
        worker_id=None,
    )

    missing_ranges = reconcile_existing_chunks(
        [chunk],
        duration_seconds=0,
        chunk_seconds=120,
        is_live=True,
    )

    assert missing_ranges == []
    assert chunk.end_seconds == 120.0
    assert chunk.status == "pending"


def test_reconcile_preserves_legacy_completed_boundary_without_overlap():
    """旧 300 秒文字分片升级后不能改成 120 秒，也不能从 120 秒处重复补建。"""
    completed = SimpleNamespace(
        id=8,
        chunk_index=0,
        start_seconds=0.0,
        end_seconds=300.0,
        status="completed",
        retry_count=1,
        segment_count=9,
        error_message=None,
        completed_at="2026-07-27",
        worker_id="asr:old",
    )

    missing_ranges = reconcile_existing_chunks(
        [completed],
        duration_seconds=600,
        chunk_seconds=120,
        is_live=False,
    )

    assert completed.start_seconds == 0.0
    assert completed.end_seconds == 300.0
    assert missing_ranges == [
        (1, 300.0, 420.0),
        (2, 420.0, 540.0),
        (3, 540.0, 600.0),
    ]


def test_reconcile_resizes_legacy_failed_chunk_to_two_minutes():
    """没有真实文字的旧失败分片可以安全重排，不能继续占用 300 秒。"""
    failed = SimpleNamespace(
        id=9,
        chunk_index=0,
        start_seconds=0.0,
        end_seconds=300.0,
        status="failed",
        retry_count=2,
        segment_count=0,
        error_message="旧任务失败",
        completed_at="2026-07-27",
        worker_id="asr:old",
    )

    missing_ranges = reconcile_existing_chunks(
        [failed],
        duration_seconds=300,
        chunk_seconds=120,
        is_live=False,
    )

    assert failed.start_seconds == 0.0
    assert failed.end_seconds == 120.0
    assert failed.status == "pending"
    assert missing_ranges == [
        (1, 120.0, 240.0),
        (2, 240.0, 300.0),
    ]


def test_reconcile_closes_failed_live_chunk_even_if_partial_text_exists():
    """失败尝试留下的部分文字不能让实时分片继续无限取流，重试时会原子替换。"""
    failed = SimpleNamespace(
        id=10,
        chunk_index=0,
        start_seconds=0.0,
        end_seconds=None,
        status="failed",
        retry_count=1,
        segment_count=2,
        error_message="连接中断",
        completed_at="2026-07-27",
        worker_id="asr:old",
    )

    missing_ranges = reconcile_existing_chunks(
        [failed],
        duration_seconds=0,
        chunk_seconds=120,
        is_live=True,
    )

    assert missing_ranges == []
    assert failed.end_seconds == 120.0
    assert failed.status == "pending"
    assert failed.segment_count == 2


def test_worker_restart_does_not_consume_business_retry():
    """Worker 进程退出属于基础设施中断，不应让真实转写提前耗尽重试次数。"""
    chunk = SimpleNamespace(
        status="processing",
        retry_count=2,
        max_retries=2,
        error_message=None,
        completed_at=None,
        worker_id="asr:old",
        heartbeat_at="2026-07-27",
    )

    recover_interrupted_chunk(chunk)

    assert chunk.status == "pending"
    assert chunk.retry_count == 1
    assert chunk.worker_id is None
    assert "断点续传" in chunk.error_message


def test_offline_task_yields_without_consuming_retry():
    """离线回放礼让实时直播属于正常调度，不应消耗失败重试次数。"""
    task = SimpleNamespace(
        status="processing",
        retry_count=2,
        error_message=None,
        started_at="2026-07-27",
        completed_at=None,
        worker_id="asr:worker",
        heartbeat_at=None,
    )

    requeue_offline_task_for_live_priority(task)

    assert task.status == "queued"
    assert task.retry_count == 1
    assert task.worker_id is None
    assert "礼让" in task.error_message


def test_m3u8_pipe_adds_seek_and_duration_for_offline_chunk():
    pipe = M3u8Pipe(
        "https://example.invalid/real-playback.m3u8",
        {"Referer": "https://example.invalid/live"},
        start_seconds=300,
        duration_seconds=120,
    )
    command = pipe._build_cmd()

    assert command[command.index("-ss") + 1] == "300.000"
    assert command[command.index("-t") + 1] == "120.000"
    assert "https://example.invalid/real-playback.m3u8" in command


def test_m3u8_pipe_slow_seek_places_ss_after_input():
    """slow-seek 必须把 -ss 放在 -i 之后，才能精确读到 HLS 回放末尾音频。"""
    pipe = M3u8Pipe(
        "https://example.invalid/real-playback.m3u8",
        {"Referer": "https://example.invalid/live"},
        start_seconds=300,
        duration_seconds=120,
        seek_mode="slow",
    )
    command = pipe._build_cmd()

    assert command.index("-ss") > command.index("-i")
    assert command[command.index("-ss") + 1] == "300.000"


def test_m3u8_pipe_default_fast_seek_places_ss_before_input():
    """默认 fast-seek 保持 -ss 在 -i 前，正常分片不改变原有定位方式。"""
    pipe = M3u8Pipe(
        "https://example.invalid/real-playback.m3u8",
        start_seconds=300,
        duration_seconds=120,
    )
    command = pipe._build_cmd()

    assert command.index("-ss") < command.index("-i")


def test_chunk_failure_message_includes_ffmpeg_stream_error():
    """空音频失败要把 ffmpeg 的真实 404/403 原因带到任务抽屉。"""
    pipe = SimpleNamespace(
        last_error_message=(
            "Error opening input: Server returned 404 Not Found\n"
            "Error opening input file https://pull-flv.example.invalid/expired.flv"
        )
    )

    message = build_chunk_failure_message(
        RuntimeError("真实流未输出任何音频帧，请刷新流地址后从断点重试"),
        pipe,
    )

    assert "真实流未输出任何音频帧" in message
    assert "ffmpeg 错误" in message
    assert "404 Not Found" in message


def test_ffmpeg_error_hides_signed_stream_url():
    """ffmpeg 错误可用于排查，但不能把带 sign 的真实流地址写进数据库。"""
    message = sanitize_ffmpeg_error(
        "Error opening input: Server returned 404 Not Found\n"
        "Error opening input file https://pull-flv.example.invalid/live.flv?expire=1&sign=secret"
    )

    assert "404 Not Found" in message
    assert "https://" not in message
    assert "sign=secret" not in message
    assert "[流地址已隐藏]" in message


def test_chunk_failure_message_is_truncated_for_database_field():
    """错误信息要限制长度，避免长 URL 或长日志撑爆数据库字段。"""
    pipe = SimpleNamespace(last_error_message="x" * 1000)

    message = build_chunk_failure_message(
        RuntimeError("真实流未输出任何音频帧，请刷新流地址后从断点重试"),
        pipe,
    )

    assert len(message) == 500


def test_synthetic_data_requires_all_explicit_switches():
    disabled = Settings(
        _env_file=None,
        DEBUG=True,
        ALLOW_SYNTHETIC_DATA=False,
        MONITOR_MOCK_MODE=True,
        ASR_ALLOW_MOCK=True,
    )
    enabled = Settings(
        _env_file=None,
        DEBUG=True,
        ALLOW_SYNTHETIC_DATA=True,
        MONITOR_MOCK_MODE=True,
        ASR_ALLOW_MOCK=True,
    )

    assert disabled.monitor_mock_enabled is False
    assert disabled.asr_mock_enabled is False
    assert enabled.monitor_mock_enabled is True
    assert enabled.asr_mock_enabled is True


def test_database_sql_echo_is_disabled_by_default():
    assert Settings.model_fields["DATABASE_ECHO"].default is False


def test_task_event_is_written_to_redis_stream(monkeypatch):
    calls = []

    class FakeRedis:
        @classmethod
        def from_url(cls, *_args, **_kwargs):
            return cls()

        def xadd(self, stream, payload, **options):
            calls.append((stream, payload, options))
            return "1-0"

        def close(self):
            return None

    monkeypatch.setattr(runtime, "Redis", FakeRedis)
    task = SimpleNamespace(
        id=12,
        status="running",
        trace_id="trace-12",
        worker_id="worker-1",
        retry_count=1,
    )

    event_id = runtime.publish_task_event("scraper", task, "progress", {"percent": 50})

    assert event_id == "1-0"
    assert calls[0][1]["trace_id"] == "trace-12"
    assert '"percent": 50' in calls[0][1]["details"]


def test_complete_transcript_uses_longtext_for_long_live_sessions():
    assert isinstance(TranscriptFullText.__table__.c.full_text.type, LONGTEXT)


def test_knowledge_content_uses_longtext_for_complete_transcripts_and_reviews():
    assert isinstance(KnowledgeBase.__table__.c.content.type, LONGTEXT)


def test_manual_retry_resets_failed_task_and_keeps_completed_chunks():
    failed_chunk = SimpleNamespace(
        status="failed",
        retry_count=3,
        error_message="Worker 重启",
        completed_at="2026-07-15",
        worker_id="asr:old",
    )
    completed_chunk = SimpleNamespace(status="completed", retry_count=1, error_message=None)
    task = SimpleNamespace(
        session_id=13246,
        stream_id=1,
        status="failed",
        retry_count=3,
        error_message="达到最大执行次数",
        started_at="2026-07-15",
        completed_at="2026-07-15",
        worker_id="asr:old",
        heartbeat_at="2026-07-15",
        trace_id="trace-13246",
        idempotency_key="asr:session:13246",
    )

    reset_failed_task_for_retry(task, [failed_chunk], stream_id=9)

    assert task.status == "queued"
    assert task.retry_count == 0
    assert task.stream_id == 9
    assert task.error_message is None
    assert task.postprocess_status == "skipped"
    assert failed_chunk.status == "pending"
    assert failed_chunk.retry_count == 0
    assert completed_chunk.status == "completed"


def test_old_mysql_text_overflow_is_recognized_as_cache_only_failure():
    error = SimpleNamespace(orig=SimpleNamespace(args=(1406, "Data too long for column 'full_text'")))

    assert is_full_text_too_long_error(error) is True
