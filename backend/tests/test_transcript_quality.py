"""话术完整度、自动补齐范围和语速的业务测试。"""

from datetime import datetime
from types import SimpleNamespace

from app.services.asr.transcript_quality import assess_transcript_quality, elapsed_live_seconds


def test_quality_finds_missing_audio_range_and_deduplicates_speech_time():
    """完整度按音频覆盖计算，语速按合并后的说话时间计算。"""
    chunks = [
        SimpleNamespace(start_seconds=0, end_seconds=120, status="completed"),
        SimpleNamespace(start_seconds=180, end_seconds=300, status="completed"),
    ]
    segments = [
        SimpleNamespace(segment_start=10, segment_end=20, text_content="开零食店先看预算"),
        # 这段与上一段重叠 5 秒，分母只能按 15 秒说话时间计算。
        SimpleNamespace(segment_start=15, segment_end=25, text_content="再看选址和品牌"),
    ]

    quality = assess_transcript_quality(
        duration_seconds=300,
        chunks=chunks,
        segments=segments,
        source="offline",
    )

    assert quality.coverage_percent == 80.0
    assert quality.covered_seconds == 240.0
    assert quality.missing_ranges == ((120.0, 180.0),)
    assert quality.status == "incomplete"
    assert quality.speech_seconds == 15.0
    # 两条话术有 5 秒重叠，重叠时间内的字符不能重复计入语速。
    assert quality.speech_char_count == 12
    assert quality.speech_rate_cpm == 48
    assert quality.rate_source == "offline_final"


def test_quality_marks_unknown_duration_without_inventing_percentage():
    """直播时长未知时不能用文字条数猜完整度。"""
    quality = assess_transcript_quality(
        duration_seconds=0,
        chunks=[],
        segments=[],
        source="realtime",
    )

    assert quality.status == "waiting_duration"
    assert quality.coverage_percent is None
    assert quality.speech_rate_cpm is None
    assert quality.rate_source == "realtime_estimate"


def test_quality_removes_cumulative_online_text_across_adjacent_segments():
    """在线修正版即使时间段相邻，也不能把上一句累计文本再算一次。"""
    segments = [
        SimpleNamespace(segment_start=0, segment_end=10, text_content="开零食店先看预算"),
        SimpleNamespace(segment_start=10, segment_end=20, text_content="开零食店先看预算和选址"),
    ]

    quality = assess_transcript_quality(
        duration_seconds=20,
        chunks=[SimpleNamespace(start_seconds=0, end_seconds=20, status="completed")],
        segments=segments,
        source="realtime",
    )

    assert quality.speech_char_count == 11
    assert quality.speech_rate_cpm == 33


def test_live_elapsed_time_uses_same_local_naive_clock_as_database():
    """数据库本地朴素时间不能与 UTC 当前时间相减。"""
    assert elapsed_live_seconds(
        datetime(2026, 7, 30, 15, 8),
        now=datetime(2026, 7, 30, 15, 10),
    ) == 120
