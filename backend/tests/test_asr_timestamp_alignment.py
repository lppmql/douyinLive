"""FunASR 逐字时间戳与纠错映射回归测试。"""

from app.services.asr.timestamp_alignment import (
    aggregate_timestamp_precision,
    normalize_funasr_timestamps,
    remap_corrected_text,
    shift_word_timestamps,
)


def test_aggregate_timestamp_precision_keeps_aligned_distinct_from_remapped():
    assert (
        aggregate_timestamp_precision({"funasr_aligned", "funasr_exact"})
        == "funasr_aligned"
    )
    assert (
        aggregate_timestamp_precision({"funasr_remapped", "funasr_aligned"})
        == "funasr_remapped"
    )


def test_normalize_exact_timestamps_keeps_punctuation_with_previous_token():
    words, source = normalize_funasr_timestamps(
        "你好，世界！",
        [[0, 200], [200, 400], [600, 800], [800, 1000]],
    )

    assert source == "funasr_exact"
    assert [item["text"] for item in words] == ["你", "好，", "世", "界！"]
    assert words[2]["start"] == 0.6
    assert words[-1]["end"] == 1.0


def test_normalize_mixed_text_uses_real_timestamp_bounds_when_token_counts_differ():
    words, source = normalize_funasr_timestamps(
        "开店ROI怎么算",
        [[0, 100], [100, 200], [200, 400], [400, 600], [600, 800]],
    )

    assert source == "funasr_aligned"
    assert "".join(str(item["text"]) for item in words) == "开店ROI怎么算"
    assert words[0]["start"] == 0
    assert words[-1]["end"] == 0.8


def test_corrected_brand_name_stays_inside_original_audio_window():
    raw_words, source = normalize_funasr_timestamps(
        "赵一名品牌",
        [[0, 200], [200, 400], [400, 600], [700, 900], [900, 1100]],
    )

    remapped, remapped_source = remap_corrected_text(
        "赵一名品牌",
        "赵一鸣品牌",
        raw_words,
        source,
    )

    assert remapped_source == "funasr_remapped"
    assert "".join(str(item["text"]) for item in remapped) == "赵一鸣品牌"
    assert remapped[0]["start"] == 0
    assert remapped[-1]["end"] == 1.1
    assert all(float(item["end"]) >= float(item["start"]) for item in remapped)


def test_shift_word_timestamps_converts_chunk_relative_to_session_absolute():
    shifted = shift_word_timestamps(
        [{"text": "预算", "start": 1.2, "end": 1.8}],
        120.0,
    )

    assert shifted == [{"text": "预算", "start": 121.2, "end": 121.8}]
