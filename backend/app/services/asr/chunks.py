"""ASR 音频分片规划。

把分片规则从 Worker 主流程中拆出来，方便单独测试：
1. 直播结束后按真实时长切片；
2. 正在直播时只创建有限的滚动窗口；
3. 场次时长被修正后，自动跳过越界旧分片。
"""

from __future__ import annotations

from typing import Any

from app.core.status import TaskStatus


def build_chunk_ranges(
    duration_seconds: int,
    chunk_seconds: int,
    *,
    is_live: bool = False,
) -> list[tuple[float, float | None]]:
    """生成连续、不重叠的分片范围。

    已结束但时长未知时保留“读到流结束”的兼容行为；正在直播时必须给出有限
    结束点，避免 ffmpeg 永远运行、资源保护永远等不到分片边界。
    """
    duration = max(0, int(duration_seconds or 0))
    size = max(60, int(chunk_seconds or 0))
    if duration == 0:
        return [(0.0, float(size))] if is_live else [(0.0, None)]
    return [
        (float(start), float(min(duration, start + size)))
        for start in range(0, duration, size)
    ]


def _reset_changed_chunk(chunk: Any) -> None:
    """边界变化后重置未完成分片，让它按新范围重新执行。"""
    if chunk.status == TaskStatus.COMPLETED:
        return
    chunk.status = TaskStatus.PENDING
    chunk.retry_count = 0
    chunk.error_message = None
    chunk.completed_at = None
    chunk.worker_id = None


def reconcile_existing_chunks(
    chunks: list[Any],
    *,
    duration_seconds: int,
    chunk_seconds: int,
    is_live: bool,
) -> list[tuple[int, float, float | None]]:
    """校准已有分片并返回需要补建的范围。

    已经识别成功的真实文字绝不删除。只有没有文字且超出真实直播结尾的技术分片
    会标记为 skipped（已跳过），让进度能够正常结束。
    """
    if not chunks:
        return [
            (index, start_seconds, end_seconds)
            for index, (start_seconds, end_seconds) in enumerate(
                build_chunk_ranges(duration_seconds, chunk_seconds, is_live=is_live)
            )
        ]

    size = float(max(60, int(chunk_seconds or 0)))
    ordered = sorted(chunks, key=lambda item: int(item.chunk_index))

    if is_live:
        # 老任务可能有 300 秒的已完成分片，文字时间轴已经与旧边界绑定。
        # 这里绝不重写它；尚未成功完成的旧分片统一收口为两分钟窗口。
        for chunk in ordered:
            # failed/pending 里的文字只是一次未完成尝试，重试时本来就会原子替换；
            # 只有 completed 才是可长期保留的成功分片。
            is_preserved = chunk.status == TaskStatus.COMPLETED
            expected_end = float(chunk.start_seconds or 0) + size
            if not is_preserved and (
                chunk.end_seconds is None or float(chunk.end_seconds) != expected_end
            ):
                chunk.end_seconds = expected_end
                _reset_changed_chunk(chunk)
        # 实时任务由 Worker 从最后一个真实结束点继续追加，避免按新索引回填造成重叠。
        return []

    duration = max(0, int(duration_seconds or 0))
    if duration == 0:
        # 已结束但真实时长未知时保留原边界，继续沿用兼容的“读到流结束”行为。
        return []

    preserved = []
    reusable = []
    for chunk in ordered:
        is_preserved = chunk.status == TaskStatus.COMPLETED
        if is_preserved:
            start = max(0.0, float(chunk.start_seconds or 0))
            # 历史“读到流结束”分片在下播后可安全落到真实结束时间；
            # 这里只补齐结束点，不改变文字的起点和覆盖范围。
            if chunk.end_seconds is None:
                chunk.end_seconds = float(duration)
            end = min(float(duration), float(chunk.end_seconds))
            if start < end:
                preserved.append((start, end))
        else:
            reusable.append(chunk)

    # 合并已有文字覆盖区间，再把剩余空白严格切成两分钟窗口。
    # 旧 failed/pending 300 秒分片会被复用为 120 秒，不会继续按旧长度重跑。
    merged = []
    for start, end in sorted(preserved):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    uncovered = []
    cursor = 0.0
    for start, end in merged:
        while cursor < start:
            next_end = min(start, cursor + size)
            uncovered.append((cursor, next_end))
            cursor = next_end
        cursor = max(cursor, end)
    while cursor < duration:
        next_end = min(float(duration), cursor + size)
        uncovered.append((cursor, next_end))
        cursor = next_end

    for chunk, (start, end) in zip(reusable, uncovered):
        chunk.start_seconds = start
        chunk.end_seconds = end
        _reset_changed_chunk(chunk)

    for chunk in reusable[len(uncovered):]:
        chunk.status = TaskStatus.SKIPPED
        chunk.error_message = "该分片超出真实直播时长或已由历史文字覆盖，已安全跳过"
        chunk.completed_at = None
        chunk.worker_id = None

    next_index = max(int(chunk.chunk_index) for chunk in ordered) + 1
    return [
        (next_index + offset, start, end)
        for offset, (start, end) in enumerate(uncovered[len(reusable):])
    ]


def next_live_chunk_range(chunks: list[Any], chunk_seconds: int) -> tuple[int, float, float]:
    """生成下一段实时窗口；每段都有明确结束点。"""
    size = float(max(60, int(chunk_seconds or 0)))
    if not chunks:
        return 0, 0.0, size
    last = max(chunks, key=lambda item: int(item.chunk_index))
    start = float(last.end_seconds if last.end_seconds is not None else last.start_seconds)
    return int(last.chunk_index) + 1, start, start + size
