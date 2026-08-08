"""FunASR 时间戳归一化与纠错文本重映射。

FunASR 返回的是模型 token 的毫秒时间戳，而业务侧会继续做品牌名、行业术语纠错。
本模块把两者解耦：先保留真实识别时间，再把纠错后的文字映射回同一段真实音频，
避免自动剪辑继续用“整句时长按字数平均分”的估算字幕。
"""

from __future__ import annotations

import json
import math
import re
from difflib import SequenceMatcher
from typing import Any

_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9]")
_PUNCTUATION = set("，。！？、；：,.!?;:（）()【】[]《》<>“”‘’\"'…—-~")


def aggregate_timestamp_precision(sources: set[str], *, has_words: bool = True) -> str:
    """聚合多段字幕精度，保留“比例对齐”和“纠错重映射”的语义差异。"""
    if not has_words or not sources or "segment_estimated" in sources:
        return "segment_estimated"
    if "funasr_remapped" in sources:
        return "funasr_remapped"
    if "funasr_aligned" in sources:
        return "funasr_aligned"
    return "funasr_exact"


def _parse_timestamp_pairs(raw_timestamp: Any) -> list[tuple[float, float]]:
    """把 FunASR 的 JSON 字符串或数组转换为合法秒级时间对。"""
    if isinstance(raw_timestamp, str):
        try:
            raw_timestamp = json.loads(raw_timestamp)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw_timestamp, list):
        return []

    pairs: list[tuple[float, float]] = []
    for item in raw_timestamp:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            start = max(0.0, float(item[0]) / 1000)
            end = max(start, float(item[1]) / 1000)
        except (TypeError, ValueError):
            continue
        pairs.append((start, end))
    return pairs


def _tokenize_display_text(text: str) -> list[str]:
    """按中文单字/英文单词切分，并把标点附到前一 token。

    FunASR 通常不给标点独立时间戳。把标点附在前一个发音 token 上，既能保留
    展示文字，也不会因为一句话多了几个标点就让所有时间错位。
    """
    tokens: list[str] = []
    ascii_buffer = ""

    def flush_ascii() -> None:
        nonlocal ascii_buffer
        if ascii_buffer:
            tokens.append(ascii_buffer)
            ascii_buffer = ""

    for char in text.strip():
        if char.isspace():
            flush_ascii()
            continue
        if _ASCII_WORD_RE.fullmatch(char):
            ascii_buffer += char
            continue
        flush_ascii()
        if char in _PUNCTUATION and tokens:
            tokens[-1] += char
        else:
            tokens.append(char)
    flush_ascii()
    return tokens


def normalize_funasr_timestamps(
    text: str,
    raw_timestamp: Any,
) -> tuple[list[dict[str, float | str]], str]:
    """将 FunASR token 时间戳与展示文本对齐。

    数量完全相等时标记为 ``funasr_exact``；中英文混排造成 token 数量不一致时，
    只在真实时间对之间做比例映射，并明确标记为 ``funasr_aligned``。
    """
    pairs = _parse_timestamp_pairs(raw_timestamp)
    tokens = _tokenize_display_text(text)
    if not pairs or not tokens:
        return [], "segment_estimated"

    exact = len(pairs) == len(tokens)
    words: list[dict[str, float | str]] = []
    pair_count = len(pairs)
    token_count = len(tokens)
    for index, token in enumerate(tokens):
        pair_start_index = min(
            pair_count - 1, math.floor(index * pair_count / token_count)
        )
        pair_end_index = min(
            pair_count - 1,
            max(
                pair_start_index, math.ceil((index + 1) * pair_count / token_count) - 1
            ),
        )
        words.append(
            {
                "text": token,
                "start": pairs[pair_start_index][0],
                "end": pairs[pair_end_index][1],
            }
        )
    return words, "funasr_exact" if exact else "funasr_aligned"


def _expand_to_char_timings(
    words: list[dict[str, Any]],
) -> tuple[list[str], list[tuple[float, float]]]:
    """把词级时间展开成字符级时间，供纠错前后文本做差异映射。"""
    chars: list[str] = []
    timings: list[tuple[float, float]] = []
    for word in words:
        text = str(word.get("text") or "")
        visible = [char for char in text if not char.isspace()]
        if not visible:
            continue
        try:
            start = float(word["start"])
            end = max(start, float(word["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        duration = max(0.001, end - start)
        for index, char in enumerate(visible):
            chars.append(char)
            timings.append(
                (
                    start + duration * index / len(visible),
                    start + duration * (index + 1) / len(visible),
                )
            )
    return chars, timings


def _allocate_text(
    chars: list[str],
    start: float,
    end: float,
) -> list[dict[str, float | str]]:
    """在给定的真实音频范围内均匀安放一段替换后的字符。"""
    if not chars:
        return []
    end = max(start + 0.001 * len(chars), end)
    duration = end - start
    return [
        {
            "text": char,
            "start": start + duration * index / len(chars),
            "end": start + duration * (index + 1) / len(chars),
        }
        for index, char in enumerate(chars)
    ]


def remap_corrected_text(
    raw_text: str,
    corrected_text: str,
    words: list[dict[str, Any]],
    source: str,
) -> tuple[list[dict[str, float | str]], str]:
    """把行业词纠错后的文字映射到 FunASR 的真实时间戳。

    相同文字直接保留原时间；替换或插入的文字只占用对应原文字的音频区间。
    因此即使“赵一鸣”等词被纠正，后面的字幕也不会整体向后漂移。
    """
    raw_chars, raw_timings = _expand_to_char_timings(words)
    corrected_chars = [char for char in corrected_text if not char.isspace()]
    if not raw_chars or not corrected_chars:
        return [], "segment_estimated"
    if "".join(raw_chars) == "".join(corrected_chars):
        return words, source

    # 优先以真实 words 还原出的文本为准；部分 FunASR 版本会省略响应 text 中的空格。
    matcher = SequenceMatcher(a=raw_chars, b=corrected_chars, autojunk=False)
    remapped: list[dict[str, float | str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for char, (start, end) in zip(
                corrected_chars[j1:j2], raw_timings[i1:i2], strict=False
            ):
                remapped.append({"text": char, "start": start, "end": end})
            continue
        if tag == "delete":
            continue

        replacement = corrected_chars[j1:j2]
        if i1 < i2:
            window_start = raw_timings[i1][0]
            window_end = raw_timings[i2 - 1][1]
        else:
            previous_end = raw_timings[i1 - 1][1] if i1 > 0 else raw_timings[0][0]
            next_start = (
                raw_timings[i1][0] if i1 < len(raw_timings) else raw_timings[-1][1]
            )
            window_start = previous_end
            window_end = max(previous_end, next_start)
        remapped.extend(_allocate_text(replacement, window_start, window_end))

    return remapped, "funasr_remapped" if remapped else "segment_estimated"


def shift_word_timestamps(
    words: list[dict[str, Any]], offset_seconds: float
) -> list[dict[str, float | str]]:
    """把分片内相对秒数换算为整场直播绝对秒数。"""
    shifted: list[dict[str, float | str]] = []
    for word in words:
        try:
            start = offset_seconds + float(word["start"])
            end = offset_seconds + float(word["end"])
        except (KeyError, TypeError, ValueError):
            continue
        shifted.append(
            {
                "text": str(word.get("text") or ""),
                "start": start,
                "end": max(start, end),
            }
        )
    return shifted
