"""AI 自动剪辑模块测试。

覆盖：
- AI 方案校验（行号映射 / 时间戳容差 / 时长约束 / 重叠检测 / 字段缺失）；
- ASS 字幕生成（无标点切分、时间格式、空文本）；
- API 契约（场次总览、确认/丢弃状态流转、文件服务降级）；
- 话术单元加载（asr_status 过滤与排序）。
"""

from datetime import datetime

from fastapi.testclient import TestClient

from app.models.clip_clips import ClipClip
from app.models.live_sessions import LiveSession
from app.models.live_rooms import LiveRoom
from app.models.transcript_segments import TranscriptSegment
from app.services.clips.ass_subtitle import _format_timestamp, _split_text, build_ass
from app.services.clips.copywriter import normalize_clip
from app.services.clips.segment_selector import TranscriptUnit, load_transcript_units


def _unit(
    start: float, end: float, text: str = "测试话术内容", seg_type: str | None = None
) -> TranscriptUnit:
    return TranscriptUnit(start=start, end=end, text=text, seg_type=seg_type)


UNITS = [
    _unit(100.0, 130.0, "第一段话术内容", "选址避坑"),
    _unit(200.0, 230.0, "第二段话术内容", "品牌判断"),
    _unit(300.0, 335.0, "第三段话术内容", "预算测算"),
]


class TestNormalizeClip:
    """AI 输出校验：不合法方案必须被拒绝，合法方案映射真实话术。"""

    def test_index_reference_resolves_real_timestamps(self):
        """行号引用：AI 只给 index，程序映射回真实话术时间戳。"""
        raw = {
            "title": "开零食店避坑",
            "description": "文案内容",
            "segments": [{"index": 2}],
            "topics": ["零食店避坑"],
        }
        result = normalize_clip(raw, UNITS, 1)
        assert result is not None
        assert result["segments"] == [
            {"start": 200.0, "end": 230.0, "text": "第二段话术内容"}
        ]
        assert result["duration_seconds"] == 30

    def test_index_out_of_range_rejected(self):
        raw = {"title": "t", "description": "d", "segments": [{"index": 99}]}
        assert normalize_clip(raw, UNITS, 1) is None

    def test_timestamp_fallback_within_tolerance(self):
        """时间戳兜底：与真实话术偏差在容差内可匹配。"""
        raw = {
            "title": "t",
            "description": "d",
            "segments": [{"start": 200.4, "end": 230.2}],
        }
        result = normalize_clip(raw, UNITS, 1)
        assert result is not None
        assert result["segments"][0]["start"] == 200.0

    def test_fabricated_timestamp_rejected(self):
        """AI 编造时间戳（话术中不存在）必须拒绝。"""
        raw = {
            "title": "t",
            "description": "d",
            "segments": [{"start": 9999.0, "end": 10000.0}],
        }
        assert normalize_clip(raw, UNITS, 1) is None

    def test_duration_over_limit_rejected(self):
        """总时长超过 90 秒必须拒绝。"""
        long_units = [_unit(0.0, 60.0), _unit(100.0, 140.0)]
        raw = {
            "title": "t",
            "description": "d",
            "segments": [{"index": 1}, {"index": 2}],
        }
        assert normalize_clip(raw, long_units, 1) is None

    def test_overlapping_segments_rejected(self):
        """片段间严重重叠（>2 秒）必须拒绝，防止重复画面。"""
        overlapping = [
            _unit(100.0, 115.0),
            _unit(112.0, 130.0),  # 与上一段重叠 3 秒
        ]
        raw = {
            "title": "t",
            "description": "d",
            "segments": [{"index": 1}, {"index": 2}],
        }
        assert normalize_clip(raw, overlapping, 1) is None

    def test_missing_fields_rejected(self):
        assert (
            normalize_clip(
                {"title": "", "description": "d", "segments": [{"index": 1}]}, UNITS, 1
            )
            is None
        )
        assert (
            normalize_clip(
                {"title": "t", "description": "", "segments": [{"index": 1}]}, UNITS, 1
            )
            is None
        )
        assert (
            normalize_clip({"title": "t", "description": "d", "segments": []}, UNITS, 1)
            is None
        )

    def test_too_many_segments_rejected(self):
        raw = {
            "title": "t",
            "description": "d",
            "segments": [{"index": i} for i in (1, 2, 3, 3, 3)],
        }
        assert normalize_clip(raw, UNITS, 1) is None

    def test_automatic_reorder(self):
        """自动模式按校验通过顺序重排 clip_order（丢弃的不占位）。"""
        raw = {
            "title": "t",
            "description": "d",
            "segments": [{"start": 9999.0, "end": 10000.0}],  # 非法，会被丢弃
        }
        assert normalize_clip(raw, UNITS, 3) is None  # 校验失败的不占位


class TestAssSubtitle:
    """ASS 字幕生成：无标点 ASR 文本按字符切分，时间轴格式正确。"""

    def test_split_text_no_punctuation(self):
        """无标点长文本按字符数硬切。"""
        text = "一二三四五六七八九十一二三四五六七八九十"
        chunks = _split_text(text)
        assert all(len(chunk) <= 13 for chunk in chunks)
        assert "".join(chunks) == text

    def test_split_text_break_at_comma(self):
        """有标点时优先在标点处断开。"""
        text = "一二三四五六七八九十，一二三四五六七八九十一二三四五"
        chunks = _split_text(text)
        assert chunks[0].endswith("，")

    def test_format_timestamp(self):
        assert _format_timestamp(0) == "0:00:00.00"
        assert _format_timestamp(125.5) == "0:02:05.50"
        assert _format_timestamp(3723.05) == "1:02:03.05"

    def test_build_ass_skips_empty(self):
        content = build_ass([{"start": 0.0, "end": 5.0, "text": "  "}])
        assert "Dialogue:" not in content

    def test_build_ass_events_and_header(self):
        content = build_ass(
            [{"start": 10.0, "end": 20.0, "text": "这是一段十多个字的话术内容测试" * 2}]
        )
        assert content.startswith("[Script Info]")
        assert "PlayResX: 1080" in content
        assert "PlayResY: 1920" in content
        assert content.count("Dialogue:") >= 2


class TestLoadTranscriptUnits:
    """话术单元加载：只取已完成且带时间戳的句子，按时间排序。"""

    def test_filters_and_sorts(self, db):
        session = _seed_session(db)
        db.add_all(
            [
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=300,
                    segment_end=310,
                    text_content="第三句",
                    asr_status="completed",
                    segment_type="asr_offline",
                ),
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=100,
                    segment_end=110,
                    text_content="第一句",
                    asr_status="completed",
                    segment_type="asr_offline",
                ),
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=200,
                    segment_end=210,
                    text_content="未完成",
                    asr_status="pending",
                    segment_type="asr_offline",
                ),
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=None,
                    segment_end=210,
                    text_content="缺开始时间",
                    asr_status="completed",
                    segment_type="asr_offline",
                ),
            ]
        )
        db.commit()
        units = load_transcript_units(db, session.id)
        assert [u.text for u in units] == ["第一句", "第三句"]
        assert units[0].start == 100.0


class TestClipApi:
    """剪辑 API 契约：总览、状态流转、文件服务降级。"""

    def test_session_not_found(self, client: TestClient, auth_headers):
        resp = client.get("/api/v1/clip/sessions/999999", headers=auth_headers)
        assert resp.status_code == 404

    def test_session_overview_with_clips(self, client: TestClient, db, auth_headers):
        session = _seed_session(db)
        db.add(
            ClipClip(
                session_id=session.id,
                clip_order=1,
                status="draft",
                title="测试成片",
                description="文案",
                topics_json=["零食店避坑"],
                segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
                duration_seconds=4,
            )
        )
        db.commit()

        resp = client.get(f"/api/v1/clip/sessions/{session.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_title"] == "测试场次"
        assert len(data["clips"]) == 1
        assert data["clips"][0]["title"] == "测试成片"
        assert data["clips"][0]["topics"] == ["零食店避坑"]

    def test_approve_and_discard_status_flow(
        self, client: TestClient, db, auth_headers
    ):
        session = _seed_session(db)
        clip = ClipClip(
            session_id=session.id,
            clip_order=1,
            status="draft",
            video_path="2130/clip_1.mp4",
            title="t",
            description="d",
            segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
        )
        db.add(clip)
        db.commit()

        resp = client.post(
            f"/api/v1/clip/clips/{clip.id}/approve", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        db.expire_all()
        assert db.get(ClipClip, clip.id).status == "approved"

        resp = client.post(
            f"/api/v1/clip/clips/{clip.id}/discard", headers=auth_headers
        )
        assert resp.status_code == 200
        db.expire_all()
        assert db.get(ClipClip, clip.id).status == "discarded"

    def test_approve_without_video_rejected(self, client: TestClient, db, auth_headers):
        session = _seed_session(db)
        clip = ClipClip(
            session_id=session.id,
            clip_order=1,
            status="draft",
            title="t",
            description="d",
            segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
        )
        db.add(clip)
        db.commit()
        resp = client.post(
            f"/api/v1/clip/clips/{clip.id}/approve", headers=auth_headers
        )
        assert resp.status_code == 409

    def test_video_file_missing_returns_404(self, client: TestClient, db, auth_headers):
        session = _seed_session(db)
        clip = ClipClip(
            session_id=session.id,
            clip_order=1,
            status="draft",
            title="t",
            description="d",
            segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
        )
        db.add(clip)
        db.commit()
        resp = client.get(f"/api/v1/clip/clips/{clip.id}/video", headers=auth_headers)
        assert resp.status_code == 404

    def test_video_path_traversal_rejected(self, client: TestClient, db, auth_headers):
        """路径穿越防护：../ 越界路径必须被拒绝（400），不能读取存储目录外文件。"""
        session = _seed_session(db)
        clip = ClipClip(
            session_id=session.id,
            clip_order=1,
            status="draft",
            title="t",
            description="d",
            segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
            video_path="../../.env",  # 恶意污染 DB 场景
            cover_path="../../.env",
        )
        db.add(clip)
        db.commit()
        resp = client.get(f"/api/v1/clip/clips/{clip.id}/video", headers=auth_headers)
        assert resp.status_code == 400
        resp = client.get(f"/api/v1/clip/clips/{clip.id}/cover", headers=auth_headers)
        assert resp.status_code == 400

    def test_generate_requires_existing_session(self, client: TestClient, auth_headers):
        resp = client.post(
            "/api/v1/clip/sessions/999999/generate", headers=auth_headers
        )
        assert resp.status_code == 404

    def test_candidate_sessions_returns_aggregates(
        self, client: TestClient, db, auth_headers
    ):
        """候选场次列表：只返回已结束+详情完整的场次，并带话术/成片统计。"""
        session = _seed_session(db)  # ended + detail complete
        db.add_all(
            [
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=100,
                    segment_end=110,
                    text_content="第一句",
                    asr_status="completed",
                    segment_type="asr_offline",
                ),
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=200,
                    segment_end=210,
                    text_content="第二句",
                    asr_status="completed",
                    segment_type="asr_offline",
                ),
                TranscriptSegment(
                    session_id=session.id,
                    segment_start=300,
                    segment_end=310,
                    text_content="第三句",
                    asr_status="pending",
                    segment_type="asr_offline",
                ),
            ]
        )
        db.add(
            ClipClip(
                session_id=session.id,
                clip_order=1,
                status="draft",
                title="t",
                description="d",
                segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
                video_path="2130/x.mp4",
            )
        )
        db.add(
            ClipClip(
                session_id=session.id,
                clip_order=2,
                status="discarded",
                title="t",
                description="d",
                segments_json=[{"start": 1.0, "end": 5.0, "text": "x"}],
            )
        )
        # 未结束的场次不应出现在候选中
        room = LiveRoom(account_name="测试账号", anchor_name="主播B")
        db.add(room)
        db.flush()
        db.add(
            LiveSession(
                room_id=room.id,
                session_title="直播中场次",
                anchor_name="主播B",
                live_status="live",
                detail_collection_status="complete",
            )
        )
        db.commit()

        resp = client.get("/api/v1/clip/candidate-sessions", headers=auth_headers)
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        item = items[0]
        assert item["session_id"] == session.id
        assert item["anchor_name"] == "测试主播"
        # 3 段话术里 2 段完成 → partial
        assert item["transcript_segment_count"] == 3
        assert item["transcript_completed_count"] == 2
        assert item["transcript_status"] == "partial"
        # 2 条成片记录里只有 1 条可用（draft）
        assert item["clip_count"] == 2
        assert item["clip_available_count"] == 1
        assert item["clip_status"] == "has_clips"


def _seed_session(db) -> LiveSession:
    """插入最小可用的直播间 + 场次种子数据。"""
    room = LiveRoom(account_name="测试账号", anchor_name="测试主播")
    db.add(room)
    db.flush()
    session = LiveSession(
        room_id=room.id,
        session_title="测试场次",
        anchor_name="测试主播",
        live_status="ended",
        detail_collection_status="complete",
        live_start_time=datetime(2026, 8, 1, 10, 0, 0),
        live_duration_seconds=3600,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session
