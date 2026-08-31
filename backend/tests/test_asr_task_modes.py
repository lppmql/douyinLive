"""直播中与下播后必须走不同的 FunASR 协议。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.api.v1.ws import delete_transcription_task, list_transcript_segments
from app.models.asr_audio_chunks import AsrAudioChunk
from app.models.asr_tasks import AsrTask
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.transcript_full_texts import TranscriptFullText
from app.models.transcript_segments import TranscriptSegment
from app.services.asr.funasr_client import FunasrClient, RealtimeDraftBuffer
from workers.asr_worker import (
    AsrWorker,
    advance_completeness_repair_round,
    is_transient_realtime_failure,
    postprocess_status_for_task,
    reset_failed_chunks_for_automatic_retry,
    seal_partial_realtime_chunk,
    segment_type_for_task,
    should_handoff_realtime_failure,
    should_handoff_realtime_task,
    should_refresh_stream_after_chunk_failure,
)


def _run_and_read_start_message(task_type: str) -> dict:
    """纯函数式读取握手配置，测试可以在毫秒内完成。"""
    return FunasrClient("ws://test.invalid").build_start_message(task_type)


def test_live_task_uses_online_protocol():
    """直播中必须边说边转，不能继续冒充离线任务。"""
    assert _run_and_read_start_message("realtime")["mode"] == "online"
    assert FunasrClient.frame_interval_for("online") < 0.06


def test_finished_task_uses_offline_protocol():
    """下播后必须使用离线精修协议。"""
    assert _run_and_read_start_message("offline")["mode"] == "offline"
    assert FunasrClient.frame_interval_for("offline") == 0.001


def test_protocol_rejects_unknown_task_type():
    """拼错任务类型时立即失败，避免默默走错识别通道。"""
    client = FunasrClient("ws://test.invalid")
    try:
        client.protocol_mode_for("unknown")
    except ValueError as exc:
        assert "任务类型" in str(exc)
    else:
        raise AssertionError("未知任务类型不应该被接受")


def test_live_draft_prefers_corrected_sentence_over_word_fragments():
    """有停顿修正版时只输出完整句子，不把每个字都写成一条话术。"""
    buffer = RealtimeDraftBuffer()
    assert (
        buffer.push({"text": "开零", "segment_start": 0, "segment_end": 1}, "online", 1)
        is None
    )
    assert (
        buffer.push({"text": "食店", "segment_start": 1, "segment_end": 2}, "online", 2)
        is None
    )
    final = buffer.push(
        {"text": "开零食店先算预算。", "segment_start": 0, "segment_end": 3},
        "2pass-offline",
        3,
    )
    assert final["text"] == "开零食店先算预算。"
    assert final["is_final"] is True


def test_live_draft_still_outputs_when_server_only_returns_online_results():
    """只有 online 响应的服务也必须每 10 秒形成初稿，不能一直显示空白。"""
    buffer = RealtimeDraftBuffer()
    assert (
        buffer.push({"text": "先看", "segment_start": 0, "segment_end": 1}, "online", 1)
        is None
    )
    draft = buffer.push(
        {"text": "预算", "segment_start": 1, "segment_end": 11}, "online", 11
    )
    assert draft["text"] == "先看预算"
    assert draft["is_final"] is False


def test_live_draft_removes_emitted_prefix_across_multiple_flushes():
    """累计在线响应跨过两次落盘时，第二段只能保存新增后缀。"""
    buffer = RealtimeDraftBuffer()
    assert (
        buffer.push({"text": "开零食店先看预算", "segment_start": 0}, "online", 1)
        is None
    )
    first = buffer.push(
        {"text": "开零食店先看预算和选址", "segment_start": 0},
        "online",
        11,
    )
    assert first["text"] == "开零食店先看预算和选址"

    assert (
        buffer.push(
            {"text": "开零食店先看预算和选址再看品牌", "segment_start": 0},
            "online",
            21,
        )
        is None
    )
    second = buffer.push(
        {"text": "开零食店先看预算和选址再看品牌最后算回本", "segment_start": 0},
        "online",
        31,
    )

    assert second["text"] == "再看品牌最后算回本"
    assert second["segment_start"] == first["segment_end"]


def test_queued_live_task_keeps_identity_after_stream_ends():
    """排队期间下播时要转交新终稿任务，不能把原任务从 realtime 改成 offline。"""
    assert should_handoff_realtime_task("realtime", "ended") is True
    assert should_handoff_realtime_task("realtime", "live") is False
    assert should_handoff_realtime_task("offline", "ended") is False


def test_realtime_stream_end_failure_handoffs_after_live_ends():
    """最后一个直播分片撞上下播 404 时应转交终稿，不能标记整场失败。"""
    assert should_handoff_realtime_failure(
        "realtime",
        "ended",
        "真实流未输出任何音频帧；ffmpeg 错误：HTTP error 404 Not Found",
    )
    assert should_handoff_realtime_failure(
        "realtime",
        "ended",
        "直播音频缓存不完整：请求 120.0 秒，实际仅读取 52.4 秒",
    )
    assert not should_handoff_realtime_failure(
        "realtime",
        "live",
        "真实流未输出任何音频帧",
    )
    assert not should_handoff_realtime_failure(
        "realtime",
        "live",
        "直播音频缓存不完整：请求 120.0 秒，实际仅读取 52.4 秒",
    )
    assert not should_handoff_realtime_failure(
        "offline",
        "ended",
        "HTTP error 404 Not Found",
    )
    assert not should_handoff_realtime_failure(
        "offline",
        "ended",
        "直播音频缓存不完整：请求 120.0 秒，实际仅读取 52.4 秒",
    )


def test_classify_chunk_failure_out_of_bounds_skips(monkeypatch):
    """分片起点超出回放真实时长时应安全跳过，而不是刷新地址。"""

    async def fake_probe(
        _url, _headers, probe_seconds=3.0, timeout=12.0, start_seconds=0.0
    ):
        return {"alive": True, "error": None, "duration_seconds": 2883.61}

    monkeypatch.setattr("workers.asr_worker.probe_stream_url", fake_probe)
    chunk = SimpleNamespace(chunk_index=24, start_seconds=2884.0)
    result = asyncio.run(
        AsrWorker._classify_chunk_failure(
            None, SimpleNamespace(id=59), chunk, "https://example.invalid/a.m3u8", {}
        )
    )
    assert result == "skip"


def test_classify_chunk_failure_slow_retry_when_seek_misses(monkeypatch):
    """地址有效且起点在回放时长内但 fast-seek 读不到 → 用 slow-seek 兜底。"""

    async def fake_probe(
        _url, _headers, probe_seconds=3.0, timeout=12.0, start_seconds=0.0
    ):
        return {"alive": True, "error": None, "duration_seconds": 2883.61}

    monkeypatch.setattr("workers.asr_worker.probe_stream_url", fake_probe)
    chunk = SimpleNamespace(chunk_index=24, start_seconds=2880.0)
    result = asyncio.run(
        AsrWorker._classify_chunk_failure(
            None, SimpleNamespace(id=59), chunk, "https://example.invalid/a.m3u8", {}
        )
    )
    assert result == "slow_retry"


def test_classify_chunk_failure_refreshes_on_dead_stream(monkeypatch):
    """地址真正失效（404）且时长未知时，保持原有刷新行为。"""

    async def fake_probe(
        _url, _headers, probe_seconds=3.0, timeout=12.0, start_seconds=0.0
    ):
        return {
            "alive": False,
            "error": "流地址已失效（404 Not Found）",
            "duration_seconds": None,
        }

    monkeypatch.setattr("workers.asr_worker.probe_stream_url", fake_probe)
    chunk = SimpleNamespace(chunk_index=24, start_seconds=0.0)
    result = asyncio.run(
        AsrWorker._classify_chunk_failure(
            None, SimpleNamespace(id=59), chunk, "https://example.invalid/a.m3u8", {}
        )
    )
    assert result == "refresh"


def test_offline_chunk_stream_failure_refreshes_before_retry():
    """离线分片的 404/TLS/空音频应刷新地址，实时缓存错误不能误刷新。"""
    assert should_refresh_stream_after_chunk_failure(
        "offline",
        "真实流未输出任何音频帧；ffmpeg 错误：404 Not Found",
    )
    assert should_refresh_stream_after_chunk_failure(
        "offline",
        "TLS Unknown error: Input/output error",
    )
    assert not should_refresh_stream_after_chunk_failure(
        "realtime",
        "直播音频缓存不完整：请求 120 秒，实际读取 52 秒",
    )
    assert is_transient_realtime_failure(
        "直播音频缓存不完整：请求 120 秒，实际读取 52 秒"
    )
    assert is_transient_realtime_failure("ffmpeg 错误：404 Not Found")
    assert not is_transient_realtime_failure("本地模型返回格式错误")


def test_offline_segments_use_hidden_staging_type():
    """离线分段在整场成功前属于隐藏暂存，实时初稿仍然立即可见。"""
    assert segment_type_for_task("realtime") == "asr_realtime"
    assert segment_type_for_task("offline") == "asr_offline_pending"


def test_offline_final_enters_local_llm_correction(monkeypatch):
    """实时初稿不增加延迟，离线终稿才进入本地模型纠错。"""
    monkeypatch.setattr("workers.asr_worker.settings.ASR_LLM_CORRECTION_ENABLED", True)
    assert postprocess_status_for_task("realtime") == "skipped"
    assert postprocess_status_for_task("offline") == "pending"


def test_automatic_retry_only_resets_failed_chunks(db):
    """任务级续接不能重跑已经完成的真实分片。"""
    room = LiveRoom(
        account_name="断点账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, anchor_name="主播", live_status="live")
    db.add(session)
    db.flush()
    task = AsrTask(session_id=session.id, status="processing", task_type="realtime")
    db.add(task)
    db.flush()
    completed = AsrAudioChunk(
        task_id=task.id,
        session_id=session.id,
        chunk_index=0,
        start_seconds=0,
        end_seconds=120,
        source_url_hash="source",
        status="completed",
        retry_count=2,
    )
    failed = AsrAudioChunk(
        task_id=task.id,
        session_id=session.id,
        chunk_index=1,
        start_seconds=120,
        end_seconds=240,
        source_url_hash="source",
        status="failed",
        retry_count=2,
        error_message="404 Not Found",
    )
    db.add_all([completed, failed])
    db.commit()

    assert reset_failed_chunks_for_automatic_retry(db, task.id) == 1
    db.commit()
    db.refresh(completed)
    db.refresh(failed)
    assert completed.status == "completed"
    assert completed.retry_count == 2
    assert failed.status == "pending"
    assert failed.retry_count == 0


def test_partial_realtime_tail_keeps_committed_segments(db):
    """尾段已识别文字在缓存不足时应封存，自动续接不能删除或重跑。"""
    room = LiveRoom(
        account_name="尾段账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, anchor_name="主播", live_status="live")
    db.add(session)
    db.flush()
    task = AsrTask(session_id=session.id, status="processing", task_type="realtime")
    db.add(task)
    db.flush()
    chunk = AsrAudioChunk(
        task_id=task.id,
        session_id=session.id,
        chunk_index=1,
        start_seconds=120,
        end_seconds=240,
        source_url_hash="source",
        status="processing",
    )
    db.add(chunk)
    db.flush()
    segment = TranscriptSegment(
        session_id=session.id,
        asr_chunk_id=chunk.id,
        segment_start=121,
        segment_end=187,
        text_content="尾段已经识别的真实话术",
        raw_text_content="尾段已经识别的真实话术",
        segment_type="asr_realtime",
        asr_status="completed",
    )
    db.add(segment)
    db.commit()

    assert seal_partial_realtime_chunk(
        db,
        task,
        chunk,
        "直播音频缓存不完整：请求 120.0 秒，实际仅读取 69.4 秒",
    )
    db.commit()
    db.refresh(chunk)
    assert chunk.status == "completed"
    assert chunk.segment_count == 1
    assert chunk.end_seconds == pytest.approx(189.4)
    assert reset_failed_chunks_for_automatic_retry(db, task.id) == 0
    assert (
        db.get(TranscriptSegment, segment.id).text_content == "尾段已经识别的真实话术"
    )


def test_offline_prepare_keeps_old_full_text_until_atomic_switch(db):
    """新终稿准备分片时必须保留页面当前可读全文，失败也不能出现空窗。"""
    room = LiveRoom(
        account_name="全文保护账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播",
        live_status="ended",
        live_start_time=datetime(2026, 7, 27, 10, 0),
        live_end_time=datetime(2026, 7, 27, 10, 2),
        live_duration_seconds=120,
    )
    db.add(session)
    db.flush()
    task = AsrTask(
        session_id=session.id,
        status="processing",
        task_type="offline",
        idempotency_key=f"asr:offline:session:{session.id}",
    )
    db.add(task)
    db.add(TranscriptFullText(session_id=session.id, full_text="直播初稿仍然可读"))
    db.commit()

    chunks = AsrWorker()._prepare_chunks(
        db,
        task,
        session,
        "https://example.invalid/replay.m3u8",
    )

    assert len(chunks) == 1
    assert (
        db.query(TranscriptFullText).filter_by(session_id=session.id).one().full_text
        == "直播初稿仍然可读"
    )


def test_offline_prepare_appends_range_when_real_duration_grows(db):
    """终稿处理期间真实时长被修正变长时，只追加新缺口。"""
    room = LiveRoom(
        account_name="时长修正账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播",
        live_status="ended",
        live_duration_seconds=120,
    )
    db.add(session)
    db.flush()
    task = AsrTask(session_id=session.id, status="processing", task_type="offline")
    db.add(task)
    db.commit()
    worker = AsrWorker()
    chunks = worker._prepare_chunks(
        db,
        task,
        session,
        "https://example.invalid/replay.m3u8",
    )
    chunks[0].status = "completed"
    db.commit()

    session.live_duration_seconds = 240
    db.commit()
    refreshed = worker._prepare_chunks(
        db,
        task,
        session,
        "https://example.invalid/replay.m3u8",
    )

    assert [
        (item.start_seconds, item.end_seconds, item.status) for item in refreshed
    ] == [
        (0.0, 120.0, "completed"),
        (120.0, 240.0, "pending"),
    ]


def test_completeness_repair_stops_after_three_successful_append_rounds():
    """真实时长持续增长也只能自动追加三轮，不能无限占用 Worker。"""
    current = 0
    for _ in range(3):
        current = advance_completeness_repair_round(current, 3)
    assert current == 3
    try:
        advance_completeness_repair_round(current, 3)
    except RuntimeError as exc:
        assert "已自动补齐 3 轮" in str(exc)
    else:
        raise AssertionError("第 4 轮完整度补齐必须被硬上限阻止")


def test_pending_offline_segments_are_hidden_from_rest_page(db):
    """离线半成品写入数据库用于断点恢复，但普通页面只能看到当前完整版本。"""
    room = LiveRoom(
        account_name="暂存隐藏账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, anchor_name="主播", live_status="ended")
    db.add(session)
    db.flush()
    db.add_all(
        [
            TranscriptSegment(
                session_id=session.id,
                text_content="当前可见初稿",
                segment_type="asr_realtime",
                asr_status="completed",
            ),
            TranscriptSegment(
                session_id=session.id,
                text_content="尚未完成的终稿",
                segment_type="asr_offline_pending",
                asr_status="processing",
            ),
        ]
    )
    db.commit()

    result = list_transcript_segments(session.id, limit=200, db=db)

    assert [item["text_content"] for item in result] == ["当前可见初稿"]


def test_deleting_failed_offline_task_keeps_realtime_draft(db):
    """清理失败终稿只能删自己的分片，不能把同场直播初稿一起删除。"""
    room = LiveRoom(
        account_name="任务清理账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, anchor_name="主播", live_status="ended")
    db.add(session)
    db.flush()
    realtime_task = AsrTask(
        session_id=session.id,
        status="completed",
        task_type="realtime",
        idempotency_key=f"asr:realtime:session:{session.id}",
    )
    offline_task = AsrTask(
        session_id=session.id,
        status="failed",
        task_type="offline",
        idempotency_key=f"asr:offline:session:{session.id}",
    )
    db.add_all([realtime_task, offline_task])
    db.flush()
    realtime_chunk = AsrAudioChunk(
        task_id=realtime_task.id,
        session_id=session.id,
        chunk_index=0,
        start_seconds=0,
        end_seconds=120,
        source_url_hash="realtime-source",
        status="completed",
    )
    offline_chunk = AsrAudioChunk(
        task_id=offline_task.id,
        session_id=session.id,
        chunk_index=0,
        start_seconds=0,
        end_seconds=120,
        source_url_hash="offline-source",
        status="failed",
    )
    db.add_all([realtime_chunk, offline_chunk])
    db.flush()
    db.add_all(
        [
            TranscriptSegment(
                session_id=session.id,
                asr_chunk_id=realtime_chunk.id,
                text_content="必须保留的直播初稿",
                segment_type="asr_realtime",
            ),
            TranscriptSegment(
                session_id=session.id,
                asr_chunk_id=offline_chunk.id,
                text_content="失败的离线半成品",
                segment_type="asr_offline_pending",
            ),
        ]
    )
    db.commit()

    delete_transcription_task(offline_task.id, db=db)

    remaining = db.query(TranscriptSegment).all()
    assert [segment.text_content for segment in remaining] == ["必须保留的直播初稿"]
