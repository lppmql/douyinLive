"""本地模型 ASR 纠错的组批与防篡改校验。"""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy.orm import sessionmaker

from app.models.asr_tasks import AsrTask
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.transcript_full_texts import TranscriptFullText
from app.models.transcript_segments import TranscriptSegment
from app.services.asr.llm_corrector import (
    build_correction_batches,
    correct_transcript_batch,
    validate_correction_payload,
)


def test_batches_keep_order_and_adjacent_context():
    previous = "上一段说明品牌" * 20
    current = "赵某一名很忙" * 20
    following = "下一段说明投资预算" * 20
    items = [
        {"id": 1, "text": previous},
        {"id": 2, "text": current},
        {"id": 3, "text": following},
    ]
    batches = build_correction_batches(items, max_chars=300)

    assert [item["id"] for batch, _before, _after in batches for item in batch] == [
        1,
        2,
        3,
    ]
    assert batches[1][1] == previous
    assert batches[1][2] == following


def test_batches_resume_only_unprocessed_ids_but_keep_context():
    items = [
        {"id": 1, "text": "已经纠正后变得很长" * 30},
        {"id": 2, "text": "等待纠正的第一段"},
        {"id": 3, "text": "等待纠正的第二段"},
    ]
    batches = build_correction_batches(items, max_chars=300, start_after_id=1)

    assert [item["id"] for batch, _before, _after in batches for item in batch] == [
        2,
        3,
    ]
    assert batches[0][1] == items[0]["text"]


def test_payload_preserves_numbers_and_rejects_large_rewrite():
    source = [
        {"id": 1, "text": "100平方投资10万元"},
        {"id": 2, "text": "赵某一名很忙属于一线品牌"},
    ]
    result = validate_correction_payload(
        source,
        {
            "items": [
                {"id": 1, "text": "100 平方投资 20 万元"},
                {"id": 2, "text": "赵一鸣、零食很忙属于一线品牌"},
            ]
        },
    )

    assert result[1] == source[0]["text"]
    assert result[2] == "赵一鸣、零食很忙属于一线品牌"


@pytest.mark.parametrize(
    "source,corrected",
    [
        ("前期投入十万元", "前期投入十五万元"),
        ("门店在江西有两百平米", "门店在广西有两百平米"),
        ("利润大约百分之十", "利润大约百分之十五"),
        ("这是零食店选址建议", "这是一段完全不同且被模型重新总结的营销文案"),
    ],
)
def test_payload_rejects_changed_facts_and_large_rewrites(source, corrected):
    result = validate_correction_payload(
        [{"id": 1, "text": source}],
        {"items": [{"id": 1, "text": corrected}]},
    )
    assert result[1] == source


def test_payload_requires_exact_unique_ids():
    with pytest.raises(ValueError, match="ID 不一致"):
        validate_correction_payload(
            [{"id": 1, "text": "原文"}],
            {"items": [{"id": 2, "text": "修正"}]},
        )


def test_correct_batch_uses_local_model_and_validates(monkeypatch):
    calls = []

    async def fake_chat_json(**kwargs):
        calls.append(kwargs)
        return {"items": [{"id": 9, "text": "开零食店先核算投资预算"}]}

    monkeypatch.setattr(
        "app.services.asr.llm_corrector.async_chat_json", fake_chat_json
    )
    monkeypatch.setattr(
        "app.services.asr.llm_corrector.get_correction_dict_cached",
        lambda: {"投资预算": "投资预算"},
    )

    result = asyncio.run(
        correct_transcript_batch(
            [{"id": 9, "text": "开临时店先核算投资预算"}],
            context_before="准备开店",
            context_after="再分析选址",
            session_id=100,
        )
    )

    assert result == {9: "开零食店先核算投资预算"}
    assert calls[0]["operation"] == "asr_transcript_correction"
    assert calls[0]["session_id"] == 100


def test_worker_correction_updates_final_text_but_preserves_raw(db, monkeypatch):
    """终稿纠错成功后更新可读文字和全文，但不能覆盖 FunASR 原文。"""
    room = LiveRoom(
        account_name="纠错账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        anchor_name="主播",
        live_status="ended",
        live_start_time=datetime(2026, 8, 31, 10, 0),
    )
    db.add(session)
    db.flush()
    task = AsrTask(
        session_id=session.id,
        task_type="offline",
        status="completed",
        postprocess_status="processing",
        postprocess_attempt_count=1,
    )
    db.add(task)
    db.flush()
    segment = TranscriptSegment(
        session_id=session.id,
        segment_start=10,
        segment_end=15,
        raw_text_content="赵某一名很忙",
        text_content="赵某一名很忙",
        segment_type="asr_offline",
        asr_status="completed",
        timestamp_source="segment_estimated",
    )
    db.add(segment)
    db.add(TranscriptFullText(session_id=session.id, full_text="旧全文"))
    db.commit()

    test_session_factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr("workers.asr_worker.SessionLocal", test_session_factory)
    monkeypatch.setattr(
        "workers.asr_worker.correct_transcript_batch",
        _async_correction({segment.id: "赵一鸣、零食很忙"}),
    )
    monkeypatch.setattr(
        "workers.asr_worker.publish_task_event", lambda *_args, **_kwargs: None
    )

    from workers.asr_worker import AsrWorker

    asyncio.run(AsrWorker()._process_correction(task.id))

    db.expire_all()
    updated_task = db.get(AsrTask, task.id)
    updated_segment = db.get(TranscriptSegment, segment.id)
    full_text = db.query(TranscriptFullText).filter_by(session_id=session.id).one()
    assert updated_task.postprocess_status == "completed"
    assert updated_task.postprocess_result["changed_count"] == 1
    assert updated_segment.raw_text_content == "赵某一名很忙"
    assert updated_segment.text_content == "赵一鸣、零食很忙"
    assert "赵一鸣、零食很忙" in full_text.full_text


def test_worker_correction_yields_to_realtime_without_consuming_attempt(
    db, monkeypatch
):
    """纠错批次看到实时任务后保存进度并礼让，不算模型失败。"""
    room = LiveRoom(
        account_name="礼让账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    offline_session = LiveSession(room_id=room.id, live_status="ended")
    live_session = LiveSession(room_id=room.id, live_status="live")
    db.add_all([offline_session, live_session])
    db.flush()
    correction_task = AsrTask(
        session_id=offline_session.id,
        task_type="offline",
        status="completed",
        postprocess_status="processing",
        postprocess_attempt_count=1,
    )
    realtime_task = AsrTask(
        session_id=live_session.id,
        task_type="realtime",
        status="queued",
    )
    db.add_all([correction_task, realtime_task])
    db.flush()
    db.add(
        TranscriptSegment(
            session_id=offline_session.id,
            text_content="待纠错话术",
            raw_text_content="待纠错话术",
            segment_type="asr_offline",
            asr_status="completed",
        )
    )
    db.commit()

    test_session_factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr("workers.asr_worker.SessionLocal", test_session_factory)

    from workers.asr_worker import AsrWorker

    asyncio.run(AsrWorker()._process_correction(correction_task.id))

    db.expire_all()
    updated = db.get(AsrTask, correction_task.id)
    assert updated.postprocess_status == "pending"
    assert updated.postprocess_attempt_count == 0
    assert "礼让" in updated.postprocess_error


def _async_correction(result):
    async def correct(_items, **_kwargs):
        return result

    return correct


def test_worker_failed_commit_does_not_advance_correction_progress(db, monkeypatch):
    """全文刷新失败时，本批文字和进度必须一起回滚，下次仍会处理该批。"""
    room = LiveRoom(
        account_name="事务账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, live_status="ended")
    db.add(session)
    db.flush()
    task = AsrTask(
        session_id=session.id,
        task_type="offline",
        status="completed",
        postprocess_status="processing",
        postprocess_attempt_count=1,
    )
    segment = TranscriptSegment(
        session_id=session.id,
        text_content="赵某一名很忙",
        raw_text_content="赵某一名很忙",
        segment_type="asr_offline",
        asr_status="completed",
    )
    db.add_all([task, segment])
    db.commit()

    test_session_factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr("workers.asr_worker.SessionLocal", test_session_factory)
    monkeypatch.setattr(
        "workers.asr_worker.correct_transcript_batch",
        _async_correction({segment.id: "赵一鸣、零食很忙"}),
    )
    monkeypatch.setattr(
        "workers.asr_worker.publish_task_event", lambda *_args, **_kwargs: None
    )
    from workers.asr_worker import AsrWorker

    worker = AsrWorker()
    original_refresh = worker._refresh_corrected_full_text
    monkeypatch.setattr(
        worker,
        "_refresh_corrected_full_text",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("刷新失败")),
    )
    asyncio.run(worker._process_correction(task.id))

    db.expire_all()
    assert db.get(AsrTask, task.id).postprocess_result is None
    assert db.get(TranscriptSegment, segment.id).text_content == "赵某一名很忙"

    failed_task = db.get(AsrTask, task.id)
    failed_task.postprocess_status = "processing"
    db.commit()
    monkeypatch.setattr(worker, "_refresh_corrected_full_text", original_refresh)
    asyncio.run(worker._process_correction(task.id))
    db.expire_all()
    assert db.get(AsrTask, task.id).postprocess_result["corrected_count"] == 1
    assert db.get(TranscriptSegment, segment.id).text_content == "赵一鸣、零食很忙"


def test_asr_waits_until_correction_is_cancelled_and_closed(db, monkeypatch):
    """新 ASR 只能排队，必须等纠错协程完成取消后才允许创建处理协程。"""
    room = LiveRoom(
        account_name="资源互斥账号", anchor_name="主播", platform="douyin", status=True
    )
    db.add(room)
    db.flush()
    session = LiveSession(room_id=room.id, live_status="live")
    db.add(session)
    db.flush()
    db.add(AsrTask(session_id=session.id, task_type="realtime", status="queued"))
    db.commit()

    test_session_factory = sessionmaker(bind=db.get_bind())
    monkeypatch.setattr("workers.asr_worker.SessionLocal", test_session_factory)
    monkeypatch.setattr(
        "workers.asr_worker.queue_auto_transcriptions", lambda *_args, **_kwargs: {}
    )

    from workers.asr_worker import AsrWorker

    events = []

    async def scenario():
        worker = AsrWorker()

        async def correction():
            try:
                await asyncio.Event().wait()
            finally:
                events.append("ollama_closed")

        async def asr_process(_task_id):
            events.append("asr_started")

        worker._correction_task = asyncio.create_task(correction())
        await asyncio.sleep(0)
        monkeypatch.setattr(worker, "_process_task", asr_process)
        monkeypatch.setattr(
            worker,
            "_current_resource_plan",
            lambda: type(
                "Plan",
                (),
                {"message": "", "target_concurrency": 1, "queue_capacity": 1},
            )(),
        )

        await worker._poll_tasks()
        assert events == []
        await worker._poll_corrections()
        assert events == ["ollama_closed"]
        await worker._poll_tasks()
        await asyncio.sleep(0)
        assert events == ["ollama_closed", "asr_started"]

    asyncio.run(scenario())
