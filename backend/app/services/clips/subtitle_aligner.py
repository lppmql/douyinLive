"""只对最终入选画面做 FunASR 二次精确对齐。

历史话术只有句级时间戳。全场重新转写成本高且会拖慢剪辑，因此仅抽取最终候选的
30-90 秒音频做离线识别，并把逐字时间写回话术表。新话术已有逐字时间时直接跳过。
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.models.clip_clips import ClipClip
from app.models.transcript_segments import TranscriptSegment
from app.services.asr.corrector import correct_text as correct_asr_text
from app.services.asr.funasr_client import FunasrClient
from app.services.asr.timestamp_alignment import (
    aggregate_timestamp_precision,
    remap_corrected_text,
    shift_word_timestamps,
)
from app.services.clips.ffmpeg_clipper import resolve_clip_ffmpeg
from app.services.tasks.exceptions import TaskCancellationRequested

CancellationChecker = Callable[[], bool]


def _ensure_running(should_cancel: CancellationChecker | None) -> None:
    if should_cancel and should_cancel():
        raise TaskCancellationRequested("用户已停止任务")


def build_audio_extract_command(
    binary: Path,
    replay: Path,
    start: float,
    duration: float,
) -> list[str]:
    """构建候选片段 PCM 提取命令；stdout 是 16kHz 单声道 s16le。"""
    return [
        str(binary),
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(replay),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(settings.ASR_SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]


def _extract_pcm(
    replay: Path,
    start: float,
    end: float,
    *,
    should_cancel: CancellationChecker | None = None,
) -> bytes:
    binary = resolve_clip_ffmpeg()
    if not binary:
        raise RuntimeError("找不到可用 ffmpeg，无法做候选字幕精确对齐")
    timeout_seconds = max(60, int(end - start) * 3)
    process = subprocess.Popen(
        build_audio_extract_command(binary, replay, start, end - start),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            _ensure_running(should_cancel)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"候选音频提取超时（{timeout_seconds} 秒）")
            try:
                stdout, stderr = process.communicate(timeout=min(0.5, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
        raise
    if process.returncode != 0 or not stdout:
        error = stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"候选音频提取失败 code={process.returncode}: {error}")
    return stdout


async def _align_pcm(
    session_id: int,
    pcm: bytes,
    absolute_offset: float,
    should_cancel: CancellationChecker | None = None,
) -> dict[str, Any]:
    client = FunasrClient()
    connected = await client.connect()
    if not connected:
        raise RuntimeError("FunASR 不可用，无法完成候选字幕精确对齐")

    # 与实时 Worker 保持相同的 60ms PCM 帧大小；离线协议会快速消费，不按实时速度等待。
    frame_bytes = max(2, int(settings.ASR_SAMPLE_RATE * 2 * 0.06))

    async def frames() -> AsyncGenerator[bytes, None]:
        for offset in range(0, len(pcm), frame_bytes):
            yield pcm[offset : offset + frame_bytes]

    raw_texts: list[str] = []
    corrected_texts: list[str] = []
    words: list[dict[str, float | str]] = []
    sources: set[str] = set()
    pending_result: asyncio.Task | None = None
    iterator = client.transcribe(session_id, frames(), task_type="offline").__aiter__()
    try:
        while True:
            _ensure_running(should_cancel)
            pending_result = asyncio.create_task(iterator.__anext__())
            while not pending_result.done():
                await asyncio.wait({pending_result}, timeout=0.5)
                _ensure_running(should_cancel)
            try:
                result = pending_result.result()
            except StopAsyncIteration:
                break
            pending_result = None
            raw_text = str(result.get("text") or "").strip()
            if not raw_text:
                continue
            corrected_text = correct_asr_text(raw_text)
            absolute_words = shift_word_timestamps(
                list(result.get("word_timestamps") or []), absolute_offset
            )
            corrected_words, source = remap_corrected_text(
                raw_text,
                corrected_text,
                absolute_words,
                str(result.get("timestamp_source") or "segment_estimated"),
            )
            raw_texts.append(raw_text)
            corrected_texts.append(corrected_text)
            words.extend(corrected_words)
            sources.add(source)
    finally:
        if pending_result and not pending_result.done():
            pending_result.cancel()
            await asyncio.gather(pending_result, return_exceptions=True)
        await client.close()

    if not corrected_texts:
        raise RuntimeError("FunASR 未返回候选片段文字")
    precision = aggregate_timestamp_precision(sources, has_words=bool(words))
    return {
        "raw_text": "".join(raw_texts),
        "text": "".join(corrected_texts),
        "words": words,
        "subtitle_precision": precision,
    }


def align_replay_segment(
    session_id: int,
    replay: Path,
    start: float,
    end: float,
    *,
    should_cancel: CancellationChecker | None = None,
) -> dict[str, Any]:
    """同步任务线程入口：抽取真实音频并运行离线 FunASR。"""
    if end <= start:
        raise ValueError("候选片段起止时间非法")
    _ensure_running(should_cancel)
    pcm = _extract_pcm(
        replay,
        start,
        end,
        should_cancel=should_cancel,
    )
    _ensure_running(should_cancel)
    aligned = asyncio.run(_align_pcm(session_id, pcm, start, should_cancel))
    _ensure_running(should_cancel)
    return aligned


def enrich_records_with_precise_subtitles(
    db: Session,
    replay: Path,
    records: list[ClipClip],
    *,
    should_cancel: CancellationChecker | None = None,
) -> dict[str, Any]:
    """补齐记录的逐字字幕并写回源话术；失败片段保留可见的估算降级标记。"""
    cache: dict[
        tuple[int | None, float, float],
        tuple[dict[str, Any] | None, dict[str, Any] | None],
    ] = {}
    aligned_count = 0
    fallback_count = 0
    fallback_warnings: list[dict[str, Any]] = []
    for record in records:
        _ensure_running(should_cancel)
        updated_segments: list[dict[str, Any]] = []
        for segment in list(record.segments_json or []):
            _ensure_running(should_cancel)
            if segment.get("words"):
                updated_segments.append(segment)
                continue
            segment_id = int(segment.get("transcript_segment_id") or 0) or None
            start = float(segment["start"])
            end = float(segment["end"])
            key = (segment_id, start, end)
            source = db.get(TranscriptSegment, segment_id) if segment_id else None
            if source and source.word_timestamps_json:
                aligned = {
                    "text": source.text_content or segment.get("text") or "",
                    "words": list(source.word_timestamps_json),
                    "subtitle_precision": source.timestamp_source or "funasr_exact",
                }
                warning = None
            elif key in cache:
                aligned, warning = cache[key]
            else:
                warning = None
                try:
                    aligned = align_replay_segment(
                        record.session_id,
                        replay,
                        start,
                        end,
                        should_cancel=should_cancel,
                    )
                except TaskCancellationRequested:
                    raise
                except Exception as exc:  # noqa: BLE001 - 单段失败需降级，其它成片继续
                    aligned = None
                    warning = {
                        "transcript_segment_id": segment_id,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "error_code": type(exc).__name__,
                        "message": str(exc)[:200],
                    }
                    logger.warning(
                        "成片 #%s 片段 %.1f-%.1f 秒精确字幕对齐失败，保留估算字幕: %s",
                        record.id,
                        start,
                        end,
                        exc,
                    )
                if aligned is None and warning is None:
                    warning = {
                        "transcript_segment_id": segment_id,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "error_code": "empty_alignment_result",
                        "message": "FunASR 未返回对齐结果",
                    }
                elif aligned and not aligned.get("words"):
                    warning = {
                        "transcript_segment_id": segment_id,
                        "start": round(start, 3),
                        "end": round(end, 3),
                        "error_code": "missing_word_timestamps",
                        "message": "FunASR 未返回逐字时间戳",
                    }
                cache[key] = (aligned, warning)
            _ensure_running(should_cancel)
            if aligned and aligned.get("words"):
                # 剪辑任务不能静默改写已经参与 AI 复盘、知识库和全文缓存的权威话术。
                # 二次识别只提供时间锚点；文字仍使用已完成终稿，并映射到新锚点。
                if (
                    source
                    and source.text_content
                    and aligned["text"] != source.text_content
                ):
                    authoritative_words, authoritative_precision = remap_corrected_text(
                        str(aligned["text"]),
                        source.text_content,
                        list(aligned["words"]),
                        str(aligned["subtitle_precision"]),
                    )
                    aligned = {
                        **aligned,
                        "text": source.text_content,
                        "words": authoritative_words,
                        "subtitle_precision": authoritative_precision,
                    }
                merged = {
                    **segment,
                    "text": aligned["text"],
                    "words": aligned["words"],
                    "subtitle_precision": aligned["subtitle_precision"],
                }
                if source:
                    source.raw_text_content = (
                        aligned.get("raw_text") or source.raw_text_content
                    )
                    source.word_timestamps_json = aligned["words"]
                    source.timestamp_source = str(aligned["subtitle_precision"])
                updated_segments.append(merged)
                aligned_count += 1
            else:
                if warning:
                    fallback_warnings.append({"clip_id": record.id, **warning})
                updated_segments.append(
                    {
                        **segment,
                        "words": [],
                        "subtitle_precision": "segment_estimated",
                    }
                )
                fallback_count += 1
        record.segments_json = updated_segments
    _ensure_running(should_cancel)
    db.commit()
    return {
        "aligned_segment_count": aligned_count,
        "fallback_segment_count": fallback_count,
        "fallback_warnings": fallback_warnings,
    }
