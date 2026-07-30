"""话术完整度与语速计算。

完整度只回答“真实音频时间轴是否全部处理”，不会把正常沉默误判成缺失。
语速使用有文字片段的合并时间作为分母，避免重叠片段重复计算说话时长。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class TranscriptQuality:
    """一场直播的话术质量快照。"""

    status: str
    coverage_percent: float | None
    covered_seconds: float
    duration_seconds: float
    missing_ranges: tuple[tuple[float, float], ...]
    speech_char_count: int
    speech_seconds: float
    speech_rate_cpm: int | None
    rate_source: str

    def to_dict(self) -> dict[str, Any]:
        """转换成可由 Pydantic/FastAPI 直接序列化的结构。"""
        return asdict(self)


def elapsed_live_seconds(
    live_start_time: datetime | None,
    *,
    now: datetime | None = None,
) -> float:
    """按数据库时间语义计算已开播秒数。

    MySQL 当前保存的是上海本地朴素时间，因此朴素值必须配对 ``datetime.now()``；
    若未来迁移为带时区时间，则自动使用相同 tzinfo，避免再次混用 UTC。
    """
    if live_start_time is None:
        return 0.0
    current = now or datetime.now(live_start_time.tzinfo)
    if (current.tzinfo is None) != (live_start_time.tzinfo is None):
        current = current.replace(tzinfo=live_start_time.tzinfo)
    return max(0.0, (current - live_start_time).total_seconds())


def _merge_ranges(
    ranges: Iterable[tuple[float, float]],
    *,
    duration_seconds: float,
) -> tuple[tuple[float, float], ...]:
    """裁剪并合并重叠区间，返回稳定有序的时间范围。"""
    duration = max(0.0, float(duration_seconds or 0))
    normalized = sorted(
        (
            max(0.0, float(start)),
            min(duration, float(end)),
        )
        for start, end in ranges
        if end is not None and float(end) > float(start)
    )
    merged: list[list[float]] = []
    for start, end in normalized:
        if start >= duration or end <= 0:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return tuple((round(start, 1), round(end, 1)) for start, end in merged)


def _missing_ranges(
    covered: tuple[tuple[float, float], ...],
    *,
    duration_seconds: float,
) -> tuple[tuple[float, float], ...]:
    """从覆盖区间反推仍需自动补齐的时间段。"""
    duration = max(0.0, float(duration_seconds or 0))
    missing: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in covered:
        if start > cursor:
            missing.append((round(cursor, 1), round(start, 1)))
        cursor = max(cursor, end)
    if cursor < duration:
        missing.append((round(cursor, 1), round(duration, 1)))
    return tuple(missing)


def _normalized_spoken_text(text: str) -> str:
    """保留语速统计使用的可读字符，便于识别相邻累计初稿。"""
    return "".join(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]", text or ""))


def _repeated_prefix_length(history: str, current: str) -> int:
    """返回当前文本与历史末尾的最长重复前缀，短口头禅不强行去重。"""
    upper = min(len(history), len(current))
    for size in range(upper, 3, -1):
        if history.endswith(current[:size]):
            return size
    return 0


def assess_transcript_quality(
    *,
    duration_seconds: float,
    chunks: Iterable[Any],
    segments: Iterable[Any],
    source: str,
) -> TranscriptQuality:
    """计算完整度、缺失区间和每分钟有效字数。

    Args:
        duration_seconds: 直播真实总时长。
        chunks: ASR 音频分片，只有 completed 才算已覆盖。
        segments: 已公开的话术片段。
        source: ``offline`` 表示离线终稿，否则按实时估算展示。
    """
    duration = max(0.0, float(duration_seconds or 0))
    rate_source = "offline_final" if source == "offline" else "realtime_estimate"
    if duration <= 0:
        return TranscriptQuality(
            status="waiting_duration",
            coverage_percent=None,
            covered_seconds=0.0,
            duration_seconds=0.0,
            missing_ranges=(),
            speech_char_count=0,
            speech_seconds=0.0,
            speech_rate_cpm=None,
            rate_source=rate_source,
        )

    covered = _merge_ranges(
        (
            (float(chunk.start_seconds or 0), float(chunk.end_seconds or 0))
            for chunk in chunks
            if str(getattr(chunk, "status", "")) == "completed"
            and getattr(chunk, "end_seconds", None) is not None
        ),
        duration_seconds=duration,
    )
    covered_seconds = round(sum(end - start for start, end in covered), 1)
    missing = _missing_ranges(covered, duration_seconds=duration)

    segment_rows = [
        segment
        for segment in segments
        if str(getattr(segment, "text_content", "") or "").strip()
        and getattr(segment, "segment_start", None) is not None
        and getattr(segment, "segment_end", None) is not None
    ]
    speech_ranges = _merge_ranges(
        (
            (float(segment.segment_start), float(segment.segment_end))
            for segment in segment_rows
        ),
        duration_seconds=duration,
    )
    speech_seconds = round(sum(end - start for start, end in speech_ranges), 1)
    # online 与 2pass-offline 可能针对同一时间段各返回一次文本。字符数按新增
    # 说话时长比例折算，避免同一句累计初稿被重复计入后把语速抬高一倍。
    counted_ranges: list[tuple[float, float]] = []
    weighted_character_count = 0.0
    recent_text = ""
    for segment in sorted(
        segment_rows,
        key=lambda item: (float(item.segment_start), float(item.segment_end)),
    ):
        start = float(segment.segment_start)
        end = float(segment.segment_end)
        before = _merge_ranges(counted_ranges, duration_seconds=duration)
        before_seconds = sum(range_end - range_start for range_start, range_end in before)
        counted_ranges.append((start, end))
        after = _merge_ranges(counted_ranges, duration_seconds=duration)
        after_seconds = sum(range_end - range_start for range_start, range_end in after)
        unique_seconds = max(0.0, after_seconds - before_seconds)
        segment_seconds = max(0.1, min(duration, end) - max(0.0, start))
        normalized_text = _normalized_spoken_text(str(segment.text_content or ""))
        time_weighted_count = len(normalized_text) * min(1.0, unique_seconds / segment_seconds)
        repeated_prefix = _repeated_prefix_length(recent_text, normalized_text)
        weighted_character_count += min(
            time_weighted_count,
            max(0, len(normalized_text) - repeated_prefix),
        )
        recent_text = (recent_text + normalized_text)[-1000:]
    speech_char_count = round(weighted_character_count)
    speech_rate = (
        round(speech_char_count * 60 / speech_seconds)
        if speech_char_count > 0 and speech_seconds > 0
        else None
    )
    coverage_percent = round(min(100.0, covered_seconds * 100 / duration), 1)

    return TranscriptQuality(
        status="complete" if not missing else "incomplete",
        coverage_percent=coverage_percent,
        covered_seconds=covered_seconds,
        duration_seconds=round(duration, 1),
        missing_ranges=missing,
        speech_char_count=speech_char_count,
        speech_seconds=speech_seconds,
        speech_rate_cpm=speech_rate,
        rate_source=rate_source,
    )
