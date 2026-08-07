"""ASS 字幕生成：把剪辑片段的话术文本转成抖音风格大字字幕。

FunASR 转写文本没有标点，无法按句切分，这里按字符数分块（每行约 13 字），
时间按字符比例均匀分配到片段时长内，保证字幕节奏自然。
样式：底部居中、白色大字、黑色描边，适配 1080x1920 竖屏。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# 每行最多显示字符数（1080 宽、Fontsize 62 下约 15 字/行，留安全边距取 13）
MAX_CHARS_PER_LINE = 13
# 单块字幕显示时长下限/上限（秒），过长会继续切分
MIN_SUBTITLE_SECONDS = 0.8
MAX_SUBTITLE_SECONDS = 3.5

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


def _split_text(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> list[str]:
    """按字符数切分文本；优先在自然停顿处（逗号/空格）断开。"""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
        # 在窗口内找最后一个停顿符，找不到就硬切
        window = text[: max_chars + 2]
        break_at = max(
            window.rfind(ch) for ch in ("，", "。", "？", "！", "、", " ", ",")
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


def build_ass(segments: list[dict[str, Any]]) -> str:
    """把片段 [{start, end, text}] 转成 ASS 字幕内容（时间轴从 0 开始）。"""
    events: list[str] = []
    cursor = 0.0
    for segment in segments:
        start = float(segment["start"])
        end = float(segment["end"])
        text = str(segment.get("text") or "").strip()
        if not text or end <= start:
            continue
        lines = _split_text(text)
        if not lines:
            continue
        total_chars = sum(len(line) for line in lines)
        # 每行字幕在其片段时间内按字符比例显示；超长行继续二分直到符合时长窗口
        blocks: list[tuple[str, float, float]] = []
        for line in lines:
            ratio = len(line) / max(total_chars, 1)
            duration = (end - start) * ratio
            blocks.append((line, duration, len(line)))
        # 时长窗口校准：太短的并到下一块，太长的按比例拆
        calibrated: list[tuple[str, float]] = []
        for line, duration, char_count in blocks:
            if duration < MIN_SUBTITLE_SECONDS:
                duration = MIN_SUBTITLE_SECONDS
            while duration > MAX_SUBTITLE_SECONDS:
                half = _split_text(line, max(1, len(line) // 2 + 1))
                if len(half) < 2:
                    break
                left, line = half[0], half[-1]
                calibrated.append((left, duration / 2))
                duration = duration / 2
            calibrated.append((line, duration))
        for line, duration in calibrated:
            # 清洗 ASS 特殊字符：换行折叠为空格，{ } 转义为全角（防样式注入）
            clean_line = (
                re.sub(r"[\r\n]+", " ", line).replace("{", "｛").replace("}", "｝")
            )
            events.append(
                f"Dialogue: 0,{_format_timestamp(cursor)},{_format_timestamp(cursor + duration)},"
                f"Default,,0,0,0,,{clean_line}"
            )
            cursor += duration
    return ASS_HEADER.format(
        fontname="PingFang SC",  # macOS 默认中文字体；Linux 部署时改为系统可用中文字体
        fontsize=62,
        outline=4,
        shadow=1,
        margin_v=120,
    ) + "\n".join(events)


def write_ass_file(segments: list[dict[str, Any]], output_path: Path) -> Path:
    """生成 ASS 字幕文件并返回路径。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = build_ass(segments)
    output_path.write_text(content, encoding="utf-8")
    return output_path
