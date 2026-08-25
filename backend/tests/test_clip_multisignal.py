"""AI 剪辑多信号选段与字幕版本化测试。"""

import asyncio
import subprocess
from datetime import datetime, timedelta

import pytest

from app.models.clip_clips import ClipClip
from app.models.comments import Comment
from app.models.lead_conversion_pairs import LeadConversionPair
from app.models.leads import Lead
from app.models.live_metrics import LiveMetric
from app.models.live_rooms import LiveRoom
from app.models.live_sessions import LiveSession
from app.models.stream_sources import StreamSource
from app.models.transcript_segments import TranscriptSegment
from app.services.clips import clip_service, ffmpeg_clipper
from app.services.clips.multisignal import build_multisignal_map
from app.services.clips.segment_selector import load_transcript_units
from app.services.clips import subtitle_aligner
from app.services.clips.subtitle_aligner import enrich_records_with_precise_subtitles
from app.services.tasks.exceptions import TaskCancellationRequested


def _session(db) -> LiveSession:
    room = LiveRoom(account_name="剪辑测试账号", anchor_name="主播甲")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        session_title="零食店避坑",
        anchor_name="主播甲",
        live_start_time=datetime(2026, 8, 8, 10, 0, 0),
        live_status="ended",
        detail_collection_status="complete",
    )
    db.add(session)
    db.commit()
    return session


def test_multisignal_score_uses_real_comments_metrics_hooks_and_attributed_lead(db):
    session = _session(db)
    segment = TranscriptSegment(
        session_id=session.id,
        segment_start=100,
        segment_end=130,
        text_content="后台私信领取品牌避坑报告，我免费帮你分析",
        asr_status="completed",
        segment_type="asr_offline",
        ai_score=8,
        is_high_conversion=1,
    )
    db.add(segment)
    db.add(
        Comment(
            session_id=session.id,
            user_nickname="准备开店",
            comment_content="预算二十万能开吗，报告发我",
            comment_time=session.live_start_time + timedelta(seconds=135),
            is_high_intent=1,
        )
    )
    db.add_all(
        [
            LiveMetric(
                session_id=session.id,
                metric_time=session.live_start_time + timedelta(seconds=60),
                like_count=100,
                comment_count=10,
                follow_count=2,
                enter_count=30,
            ),
            LiveMetric(
                session_id=session.id,
                metric_time=session.live_start_time + timedelta(seconds=160),
                like_count=180,
                comment_count=16,
                follow_count=4,
                enter_count=50,
            ),
        ]
    )
    douyin_lead = Lead(
        session_id=session.id,
        douyin_id="test-001",
        anchor_name="主播甲",
        create_time=session.live_start_time + timedelta(seconds=170),
    )
    contact_lead = Lead(
        session_id=session.id,
        lead_phone="13800000000",
        anchor_name="主播甲",
        create_time=session.live_start_time + timedelta(seconds=175),
    )
    db.add_all([douyin_lead, contact_lead])
    db.flush()
    db.add(
        LeadConversionPair(
            douyin_lead_id=douyin_lead.id,
            contact_lead_id=contact_lead.id,
            session_id=session.id,
            anchor_name="主播甲",
            douyin_id="test-001",
            contact_type="phone",
            contact_value="13800000000",
            douyin_recorded_at=douyin_lead.create_time,
            contact_recorded_at=contact_lead.create_time,
            converted_at=contact_lead.create_time,
            gap_seconds=5,
            attribution_status="attributed",
            attribution_method="anchor_60s_pair",
        )
    )
    db.commit()

    units = load_transcript_units(db, session.id)
    evidence = build_multisignal_map(db, session.id, units)[segment.id]

    assert evidence["signal_score"] > 50
    assert evidence["comment_count"] == 1
    assert evidence["high_intent_comment_count"] == 1
    assert evidence["hook_count"] == 1
    assert evidence["hook_strength"] == "strong"
    assert evidence["related_lead_count"] == 1
    assert evidence["metric_deltas"]["like_count"] == 80


def test_clip_preflight_stops_before_ai_when_funasr_is_required(
    db, tmp_path, monkeypatch
):
    """历史话术缺逐字时间戳且 FunASR 未启动时，应在 AI 选段前停止。"""
    session = _session(db)
    db.add(
        TranscriptSegment(
            session_id=session.id,
            segment_start=10,
            segment_end=20,
            text_content="真实终稿话术",
            asr_status="completed",
            segment_type="asr_offline",
            word_timestamps_json=None,
        )
    )
    db.add(
        StreamSource(
            session_id=session.id,
            m3u8_url="https://example.invalid/real-replay.m3u8",
            status="active",
        )
    )
    db.commit()
    monkeypatch.setattr(clip_service, "require_clip_ffmpeg", lambda: tmp_path / "ffmpeg")
    monkeypatch.setattr(clip_service, "replay_path", lambda _session_id: tmp_path / "missing.mp4")
    monkeypatch.setattr(clip_service, "is_asr_engine_running", lambda: False)

    with pytest.raises(RuntimeError, match="请先启动 FunASR"):
        clip_service._preflight_clip_generation(db, session.id)


def test_clip_preflight_accepts_real_transcript_and_stream_without_funasr(
    db, tmp_path, monkeypatch
):
    """已有逐字时间戳时无需二次识别引擎，也能使用真实流源进入 AI 阶段。"""
    session = _session(db)
    db.add(
        TranscriptSegment(
            session_id=session.id,
            segment_start=10,
            segment_end=20,
            text_content="真实终稿话术",
            asr_status="completed",
            segment_type="asr_offline",
            word_timestamps_json=[{"text": "真", "start": 10.0, "end": 10.2}],
        )
    )
    db.add(
        StreamSource(
            session_id=session.id,
            m3u8_url="https://example.invalid/real-replay.m3u8",
            status="active",
        )
    )
    db.commit()
    monkeypatch.setattr(clip_service, "require_clip_ffmpeg", lambda: tmp_path / "ffmpeg")
    monkeypatch.setattr(clip_service, "replay_path", lambda _session_id: tmp_path / "missing.mp4")
    monkeypatch.setattr(
        clip_service,
        "is_asr_engine_running",
        lambda: (_ for _ in ()).throw(AssertionError("不应检查 FunASR")),
    )

    result = clip_service._preflight_clip_generation(db, session.id)

    assert result == {
        "transcript_count": 1,
        "missing_word_timestamp_count": 0,
        "replay_source": "stream",
    }


def test_time_nearby_lead_without_formal_hook_is_visible_but_does_not_add_score(db):
    session = _session(db)
    segment = TranscriptSegment(
        session_id=session.id,
        segment_start=100,
        segment_end=130,
        text_content="这是普通的门店经营介绍",
        asr_status="completed",
        segment_type="asr_offline",
    )
    douyin_lead = Lead(
        session_id=session.id,
        douyin_id="nearby-only",
        anchor_name="主播甲",
        create_time=session.live_start_time + timedelta(seconds=170),
    )
    contact_lead = Lead(
        session_id=session.id,
        lead_phone="13900000000",
        anchor_name="主播甲",
        create_time=session.live_start_time + timedelta(seconds=175),
    )
    db.add_all([segment, douyin_lead, contact_lead])
    db.flush()
    db.add(
        LeadConversionPair(
            douyin_lead_id=douyin_lead.id,
            contact_lead_id=contact_lead.id,
            session_id=session.id,
            anchor_name="主播甲",
            douyin_id="nearby-only",
            contact_type="phone",
            contact_value="13900000000",
            douyin_recorded_at=douyin_lead.create_time,
            contact_recorded_at=contact_lead.create_time,
            converted_at=contact_lead.create_time,
            gap_seconds=5,
            attribution_status="attributed",
            attribution_method="anchor_60s_pair",
        )
    )
    db.commit()

    evidence = build_multisignal_map(
        db, session.id, load_transcript_units(db, session.id)
    )[segment.id]

    assert evidence["hook_count"] == 0
    assert evidence["related_lead_count"] == 0
    assert evidence["lead_after_5m_count"] == 1
    assert evidence["signal_score"] == 0


def test_subtitle_rerender_creates_new_version_and_keeps_previous_paths(
    db, tmp_path, monkeypatch
):
    session = _session(db)
    clean = tmp_path / "1" / "clips" / "1" / "v1" / "clean.mp4"
    clean.parent.mkdir(parents=True)
    clean.write_bytes(b"clean-video")
    record = ClipClip(
        session_id=session.id,
        clip_order=1,
        status="approved",
        title="预算避坑",
        segments_json=[
            {
                "start": 10.0,
                "end": 40.0,
                "text": "赵一名品牌",
                "words": [
                    {"text": "赵", "start": 10.0, "end": 10.2},
                    {"text": "一", "start": 10.2, "end": 10.4},
                    {"text": "名", "start": 10.4, "end": 10.6},
                    {"text": "品", "start": 10.7, "end": 10.9},
                    {"text": "牌", "start": 10.9, "end": 11.1},
                ],
                "subtitle_precision": "funasr_exact",
            }
        ],
        clean_video_path=str(clean.relative_to(tmp_path)),
        video_path="1/clips/1/v1/video.mp4",
        cover_path="1/clips/1/v1/cover.jpg",
        subtitle_path="1/clips/1/v1/subtitle.ass",
        subtitle_srt_path="1/clips/1/v1/subtitle.srt",
        subtitle_precision="funasr_exact",
        render_version=1,
    )
    db.add(record)
    db.commit()

    evicted_video = tmp_path / "1" / "clips" / str(record.id) / "v0" / "video.mp4"
    evicted_video.parent.mkdir(parents=True, exist_ok=True)
    evicted_video.write_bytes(b"old-version")
    record.artifact_versions_json = [
        {
            "version": index,
            "video_path": str(evicted_video.relative_to(tmp_path))
            if index == 0
            else None,
        }
        for index in range(20)
    ]
    db.commit()

    monkeypatch.setattr(clip_service, "_storage_root", lambda: tmp_path)

    def fake_rerender(_clean, _segments, **_kwargs):
        version_dir = tmp_path / "1" / "clips" / str(record.id) / "v2"
        version_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "clean_video": clean,
            "video": version_dir / "video.mp4",
            "cover": version_dir / "cover.jpg",
            "subtitle": version_dir / "subtitle.ass",
            "subtitle_srt": version_dir / "subtitle.srt",
        }
        for path in paths.values():
            path.write_bytes(b"ok")
        return paths

    monkeypatch.setattr(clip_service, "rerender_subtitles", fake_rerender)

    updated = clip_service.rerender_clip_subtitles(
        db,
        record.id,
        requested_segments=[{"start": 10.0, "end": 40.0, "text": "赵一鸣品牌"}],
    )

    assert updated.render_version == 2
    assert updated.status == "draft"
    assert updated.subtitle_precision == "funasr_remapped"
    assert updated.segments_json[0]["text"] == "赵一鸣品牌"
    assert len(updated.artifact_versions_json) == 20
    assert not evicted_video.exists()

    monkeypatch.setattr(
        clip_service,
        "rerender_subtitles",
        lambda *_args, **_kwargs: pytest.fail("恢复任务不应重复生成更高版本"),
    )
    recovered = clip_service.rerender_clip_subtitles(
        db,
        record.id,
        requested_segments=[{"start": 10.0, "end": 40.0, "text": "赵一鸣品牌"}],
        target_render_version=2,
    )
    assert recovered.render_version == 2


def test_failed_subtitle_render_removes_unreferenced_version_directory(
    tmp_path, monkeypatch
):
    clean = tmp_path / "clean.mp4"
    clean.write_bytes(b"clean")
    monkeypatch.setattr(ffmpeg_clipper, "_require_ffmpeg", lambda: tmp_path / "ffmpeg")
    monkeypatch.setattr(
        ffmpeg_clipper, "session_video_dir", lambda _session_id: tmp_path
    )
    monkeypatch.setattr(
        ffmpeg_clipper,
        "_run_ffmpeg",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("render failed")),
    )

    with pytest.raises(RuntimeError, match="render failed"):
        ffmpeg_clipper.rerender_subtitles(
            clean,
            [{"start": 1.0, "end": 31.0, "text": "字幕"}],
            session_id=1,
            clip_id=42,
            render_version=2,
            encoder="libx264",
        )

    assert not (tmp_path / "clips" / "42" / "v2").exists()


def test_discarded_full_generation_history_is_bounded_and_removes_unique_media(
    db, tmp_path, monkeypatch
):
    session = _session(db)
    records = [
        ClipClip(
            session_id=session.id,
            clip_order=index + 1,
            status="discarded",
            segments_json=[{"start": 1.0, "end": 31.0, "text": "旧字幕"}],
        )
        for index in range(11)
    ]
    db.add_all(records)
    db.commit()
    for record in records:
        clean = (
            tmp_path / str(session.id) / "clips" / str(record.id) / "v1" / "clean.mp4"
        )
        clean.parent.mkdir(parents=True, exist_ok=True)
        clean.write_bytes(b"old-clean")
        record.clean_video_path = str(clean.relative_to(tmp_path))
    db.commit()
    oldest_id = records[0].id
    oldest_clean = tmp_path / str(records[0].clean_video_path)
    monkeypatch.setattr(clip_service, "_storage_root", lambda: tmp_path)

    removed = clip_service.prune_discarded_clips(db, session.id, keep=10)

    assert removed == 1
    assert db.get(ClipClip, oldest_id) is None
    assert not oldest_clean.exists()
    assert (
        db.query(ClipClip)
        .filter(ClipClip.session_id == session.id, ClipClip.status == "discarded")
        .count()
        == 10
    )


def test_unrendered_drafts_are_marked_failed_after_alignment_cancellation(db):
    session = _session(db)
    record = ClipClip(
        session_id=session.id,
        clip_order=1,
        status="draft",
        segments_json=[{"start": 1.0, "end": 31.0, "text": "待生成"}],
    )
    db.add(record)
    db.commit()

    clip_service._mark_unrendered_records_failed(db, session.id)
    db.refresh(record)

    assert record.status == "failed"
    assert "任务取消或中断" in record.error_message


def test_funasr_alignment_checks_cancellation_while_waiting(monkeypatch):
    closed = False

    class SlowFunasrClient:
        async def connect(self):
            return True

        async def transcribe(self, *_args, **_kwargs):
            await asyncio.sleep(60)
            yield {}

        async def close(self):
            nonlocal closed
            closed = True

    monkeypatch.setattr(subtitle_aligner, "FunasrClient", SlowFunasrClient)
    checks = iter([False, True])

    with pytest.raises(TaskCancellationRequested):
        asyncio.run(
            subtitle_aligner._align_pcm(
                1,
                b"\0" * 3200,
                0.0,
                lambda: next(checks),
            )
        )

    assert closed is True


def test_audio_extraction_terminates_ffmpeg_when_cancelled(tmp_path, monkeypatch):
    terminated = False

    class SlowProcess:
        returncode = None

        def communicate(self, timeout=None):
            if terminated:
                self.returncode = -15
                return b"", b""
            raise subprocess.TimeoutExpired("ffmpeg", timeout)

        def poll(self):
            return self.returncode

        def terminate(self):
            nonlocal terminated
            terminated = True

        def kill(self):
            self.returncode = -9

    monkeypatch.setattr(
        subtitle_aligner, "resolve_clip_ffmpeg", lambda: tmp_path / "ffmpeg"
    )
    monkeypatch.setattr(
        subtitle_aligner.subprocess, "Popen", lambda *_args, **_kwargs: SlowProcess()
    )
    checks = iter([False, True])

    with pytest.raises(TaskCancellationRequested):
        subtitle_aligner._extract_pcm(
            tmp_path / "replay.mp4",
            0,
            30,
            should_cancel=lambda: next(checks),
        )

    assert terminated is True


def test_second_pass_alignment_keeps_authoritative_transcript_text(
    db, tmp_path, monkeypatch
):
    session = _session(db)
    source = TranscriptSegment(
        session_id=session.id,
        segment_start=10,
        segment_end=20,
        text_content="这是已经审核过的权威话术终稿",
        asr_status="completed",
        segment_type="asr_offline",
    )
    db.add(source)
    db.flush()
    record = ClipClip(
        session_id=session.id,
        clip_order=1,
        status="draft",
        segments_json=[
            {
                "transcript_segment_id": source.id,
                "start": 10.0,
                "end": 20.0,
                "text": source.text_content,
                "words": [],
                "subtitle_precision": "segment_estimated",
            }
        ],
    )
    db.add(record)
    db.commit()

    monkeypatch.setattr(
        "app.services.clips.subtitle_aligner.align_replay_segment",
        lambda *_args, **_kwargs: {
            "raw_text": "这是二次识别文字",
            "text": "这是二次识别文字",
            "words": [
                {"text": "这", "start": 10.0, "end": 10.3},
                {"text": "是", "start": 10.3, "end": 10.6},
                {"text": "二", "start": 10.6, "end": 10.9},
                {"text": "次", "start": 10.9, "end": 11.2},
                {"text": "识", "start": 11.2, "end": 11.5},
                {"text": "别", "start": 11.5, "end": 11.8},
                {"text": "文", "start": 11.8, "end": 12.1},
                {"text": "字", "start": 12.1, "end": 12.4},
            ],
            "subtitle_precision": "funasr_exact",
        },
    )

    result = enrich_records_with_precise_subtitles(
        db,
        tmp_path / "replay.mp4",
        [record],
    )
    db.refresh(source)
    db.refresh(record)

    assert result == {
        "aligned_segment_count": 1,
        "fallback_segment_count": 0,
        "fallback_warnings": [],
    }
    assert source.text_content == "这是已经审核过的权威话术终稿"
    assert source.raw_text_content == "这是二次识别文字"
    assert record.segments_json[0]["text"] == source.text_content
    assert record.segments_json[0]["words"]
    assert record.segments_json[0]["subtitle_precision"] == "funasr_remapped"


def test_second_pass_alignment_propagates_task_cancellation(db, tmp_path, monkeypatch):
    session = _session(db)
    record = ClipClip(
        session_id=session.id,
        clip_order=1,
        status="draft",
        segments_json=[
            {
                "start": 10.0,
                "end": 20.0,
                "text": "待对齐话术",
                "words": [],
            }
        ],
    )
    db.add(record)
    db.commit()
    monkeypatch.setattr(
        "app.services.clips.subtitle_aligner.align_replay_segment",
        lambda *_args, **_kwargs: {
            "text": "待对齐话术",
            "words": [{"text": "待", "start": 10.0, "end": 10.2}],
            "subtitle_precision": "funasr_exact",
        },
    )
    checks = iter([False, False, True])

    with pytest.raises(TaskCancellationRequested):
        enrich_records_with_precise_subtitles(
            db,
            tmp_path / "replay.mp4",
            [record],
            should_cancel=lambda: next(checks),
        )


def test_second_pass_alignment_records_fallback_reason(db, tmp_path, monkeypatch):
    """精确对齐失败必须保留结构化原因，不能只留下一个降级数量。"""
    session = _session(db)
    record = ClipClip(
        session_id=session.id,
        clip_order=1,
        status="draft",
        segments_json=[
            {
                "start": 10.0,
                "end": 20.0,
                "text": "待对齐话术",
                "words": [],
            }
        ],
    )
    db.add(record)
    db.commit()

    def fail_alignment(*_args, **_kwargs):
        raise RuntimeError("FunASR 暂时不可用")

    monkeypatch.setattr(
        "app.services.clips.subtitle_aligner.align_replay_segment",
        fail_alignment,
    )

    result = enrich_records_with_precise_subtitles(
        db,
        tmp_path / "replay.mp4",
        [record],
    )

    assert result["fallback_segment_count"] == 1
    assert result["fallback_warnings"] == [
        {
            "clip_id": record.id,
            "transcript_segment_id": None,
            "start": 10.0,
            "end": 20.0,
            "error_code": "RuntimeError",
            "message": "FunASR 暂时不可用",
        }
    ]
