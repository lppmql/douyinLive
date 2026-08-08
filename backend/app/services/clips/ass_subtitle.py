"""逐字时间驱动的 ASS/SRT 字幕生成。

新转写数据优先使用 FunASR 的真实逐字/词时间戳；历史数据没有逐字时间时才按
整句话术片段估算。多段画面拼接时会把整场绝对时间映射为成片局部时间，
删除片段之间的空档，避免第二段字幕仍沿用原直播时间而错位。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_CHARS_PER_LINE = 13
MAX_SUBTITLE_SECONDS = 3.5
SILENCE_BREAK_SECONDS = 0.65
_ENDING_PUNCTUATION = ("。", "！", "？", "；", ".", "!", "?", ";")

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},&H00FFFFFF,&H000000FF,&H00101010,&H96000000,1,0,0,0,100,100,0,0,1,{outline},{shadow},2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


@dataclass(frozen=True)
class SubtitleCue:
    """一条已经映射到成片局部时间的字幕。"""

    start: float
    end: float
    text: str
    precision: str


def _split_text(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> list[str]:
    """按字符数切分文本，优先在自然停顿处断开。"""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        window = text[: max_chars + 2]
        break_at = max(
            window.rfind(char) for char in ("，", "。", "？", "！", "、", " ", ",")
        )
        take = break_at + 1 if break_at > max_chars * 0.5 else max_chars
        chunks.append(text[:take])
        text = text[take:]
    return chunks


def _format_timestamp(seconds: float) -> str:
    """ASS 时间格式 h:mm:ss.cc（厘秒，正确处理进位）。"""
    total_centis = int(round(max(0.0, seconds) * 100))
    hours = total_centis // 360000
    minutes = (total_centis % 360000) // 6000
    secs = (total_centis % 6000) // 100
    centis = total_centis % 100
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _format_srt_timestamp(seconds: float) -> str:
    """SRT 时间格式 hh:mm:ss,mmm。"""
    total_millis = int(round(max(0.0, seconds) * 1000))
    hours = total_millis // 3_600_000
    minutes = (total_millis % 3_600_000) // 60_000
    secs = (total_millis % 60_000) // 1000
    millis = total_millis % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _valid_segment_words(segment: dict[str, Any]) -> list[dict[str, float | str]]:
    """读取并钳制当前剪辑区间内的真实逐字时间。"""
    segment_start = float(segment["start"])
    segment_end = float(segment["end"])
    words: list[dict[str, float | str]] = []
    for item in segment.get("words") or []:
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        text = str(item.get("text") or "").strip()
        if not text or end < segment_start or start > segment_end:
            continue
        start = max(segment_start, start)
        end = min(segment_end, max(start, end))
        words.append({"text": text, "start": start, "end": end})
    return sorted(words, key=lambda item: (float(item["start"]), float(item["end"])))


def _precise_segment_cues(
    segment: dict[str, Any],
    clip_offset: float,
) -> list[SubtitleCue]:
    """按真实词间停顿、标点、字数和显示时长组合字幕。"""
    segment_start = float(segment["start"])
    segment_end = float(segment["end"])
    local_segment_end = clip_offset + segment_end - segment_start
    words = _valid_segment_words(segment)
    if not words:
        return []

    precision = str(segment.get("subtitle_precision") or "funasr_exact")
    cues: list[SubtitleCue] = []
    group: list[dict[str, float | str]] = []

    def flush() -> None:
        if not group:
            return
        text = "".join(str(item["text"]) for item in group).strip()
        if not text:
            group.clear()
            return
        start = clip_offset + float(group[0]["start"]) - segment_start
        end = clip_offset + float(group[-1]["end"]) - segment_start
        start = max(0.0, start)
        if start >= local_segment_end:
            group.clear()
            return
        cues.append(
            SubtitleCue(
                start=start,
                end=min(local_segment_end, max(start + 0.01, end)),
                text=text,
                precision=precision,
            )
        )
        group.clear()

    for word in words:
        if group:
            current_text = "".join(str(item["text"]) for item in group)
            gap = float(word["start"]) - float(group[-1]["end"])
            projected_duration = float(word["end"]) - float(group[0]["start"])
            should_break = (
                gap >= SILENCE_BREAK_SECONDS
                or len(current_text) + len(str(word["text"])) > MAX_CHARS_PER_LINE
                or projected_duration > MAX_SUBTITLE_SECONDS
                or current_text.endswith(_ENDING_PUNCTUATION)
            )
            if should_break:
                flush()
        group.append(word)
    flush()
    return cues


def _estimated_segment_cues(
    segment: dict[str, Any],
    clip_offset: float,
) -> list[SubtitleCue]:
    """历史数据降级：严格守住片段总时长，不再因最小时长累加而漂移。"""
    start = float(segment["start"])
    end = float(segment["end"])
    text = str(segment.get("text") or "").strip()
    duration = end - start
    if not text or duration <= 0:
        return []

    seconds_per_char = duration / max(1, len(text))
    time_limited_chars = (
        max(1, math.floor(MAX_SUBTITLE_SECONDS / seconds_per_char))
        if seconds_per_char > 0
        else MAX_CHARS_PER_LINE
    )
    lines = _split_text(text, min(MAX_CHARS_PER_LINE, time_limited_chars))
    total_chars = sum(len(line) for line in lines)
    cues: list[SubtitleCue] = []
    cursor = clip_offset
    for index, line in enumerate(lines):
        # 最后一条直接收口到片段终点，消除浮点累计误差。
        cue_end = (
            clip_offset + duration
            if index == len(lines) - 1
            else cursor + duration * len(line) / max(total_chars, 1)
        )
        cues.append(
            SubtitleCue(
                start=cursor,
                end=max(cursor + 0.01, cue_end),
                text=line,
                precision="segment_estimated",
            )
        )
        cursor = cue_end
    return cues


def build_subtitle_cues(segments: list[dict[str, Any]]) -> list[SubtitleCue]:
    """把多个原直播片段映射到连续成片时间轴。"""
    cues: list[SubtitleCue] = []
    clip_offset = 0.0
    for segment in segments:
        try:
            duration = float(segment["end"]) - float(segment["start"])
        except (KeyError, TypeError, ValueError):
            continue
        if duration <= 0:
            continue
        precise = _precise_segment_cues(segment, clip_offset)
        cues.extend(precise or _estimated_segment_cues(segment, clip_offset))
        clip_offset += duration
    return cues


def _clean_ass_text(text: str) -> str:
    """折叠换行并阻止 ASS 样式注入。"""
    return re.sub(r"[\r\n]+", " ", text).replace("{", "｛").replace("}", "｝")


def build_ass(segments: list[dict[str, Any]]) -> str:
    """生成可直接烧录的 ASS 字幕。"""
    events = [
        (
            f"Dialogue: 0,{_format_timestamp(cue.start)},{_format_timestamp(cue.end)},"
            f"Default,,0,0,0,,{_clean_ass_text(cue.text)}"
        )
        for cue in build_subtitle_cues(segments)
    ]
    return ASS_HEADER.format(
        fontname="PingFang SC",
        fontsize=62,
        outline=4,
        shadow=1,
        margin_v=120,
    ) + "\n".join(events)


def build_srt(segments: list[dict[str, Any]]) -> str:
    """生成便于运营复查和第三方剪辑软件导入的 SRT 字幕。"""
    blocks = [
        f"{index}\n{_format_srt_timestamp(cue.start)} --> {_format_srt_timestamp(cue.end)}\n{cue.text}"
        for index, cue in enumerate(build_subtitle_cues(segments), start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_ass_file(segments: list[dict[str, Any]], output_path: Path) -> Path:
    """生成 ASS 字幕文件并返回路径。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_ass(segments), encoding="utf-8")
    return output_path


def write_srt_file(segments: list[dict[str, Any]], output_path: Path) -> Path:
    """生成 SRT 字幕文件并返回路径。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_srt(segments), encoding="utf-8")
    return output_path
