"""AI 手动剪辑 - 选段服务。

从一场直播的完整话术（transcript_segments，含句子级秒级时间戳）中，
由本地 Ollama 挑选出适合做成短视频的片段方案。参考 FunClip 的
"LLM 输出 `N. [start-end] text` 契约、程序解析执行" 与 AutoCut 的
"保留句即剪辑单" 思路：LLM 只负责决策（选哪些时间片段、起什么标题），
真正的 ffmpeg 剪辑由剪辑引擎按返回的时间戳执行，不依赖 AI 输出视频。

输入压缩策略（控制 token 成本）：
- 每段话术截断到 MAX_UNIT_CHARS 字符；
- 片段总数超过 MAX_UNITS 时按时间均匀抽样，保证全片覆盖；
- 高价值段（ai_score>=8 或 is_high_conversion=1）加 [高价值] 标注引导优先选。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.logger import logger
from app.models.transcript_segments import TranscriptSegment
from app.services.ai.llm_client import chat
from app.services.clips.multisignal import build_multisignal_map

# 最多 500 段真实话术，除正文外还有信号和行号；项目本地模型使用 64K 上下文。
MAX_UNITS = 500
MAX_UNIT_CHARS = 120
# 单条方案输出时长约束（秒）
MIN_CLIP_SECONDS = 30
MAX_CLIP_SECONDS = 90
MAX_SEGMENTS_PER_CLIP = 3
# 保留 5 条方案 JSON 的输出预算；本地客户端已关闭额外思考内容。
MAX_OUTPUT_TOKENS = 12000
# 时间戳映射容差（秒）：AI 返回的 start/end 必须能在输入话术中精确找到
TIMESTAMP_TOLERANCE = 1.0


@dataclass
class TranscriptUnit:
    """一条可用于剪辑的话术单元（句子级）。"""

    start: float
    end: float
    text: str
    segment_id: int | None = None
    words: list[dict[str, Any]] | None = None
    timestamp_source: str = "segment_estimated"
    seg_type: str | None = None
    ai_score: float | None = None
    high_value: bool = False
    signal_score: float = 0
    evidence: dict[str, Any] | None = None


def load_transcript_units(db: Session, session_id: int) -> list[TranscriptUnit]:
    """读取场次已完成的离线终稿话术，按时间排序。

    优先 asr_offline（终稿），其缺失时回退 realtime（初稿），
    避免出现整场只有初稿、剪辑无依据的情况。
    """
    rows = (
        db.query(TranscriptSegment)
        .filter(
            TranscriptSegment.session_id == session_id,
            TranscriptSegment.asr_status == "completed",
            TranscriptSegment.segment_start.isnot(None),
            TranscriptSegment.segment_end.isnot(None),
            TranscriptSegment.text_content.isnot(None),
        )
        .order_by(TranscriptSegment.segment_start.asc(), TranscriptSegment.id.asc())
        .all()
    )
    offline = [r for r in rows if r.segment_type in (None, "", "asr_offline")]
    if not offline:
        offline = rows
    units = [
        TranscriptUnit(
            start=float(r.segment_start),
            end=float(r.segment_end),
            text=(r.text_content or "").strip(),
            segment_id=int(r.id),
            words=list(r.word_timestamps_json or []),
            timestamp_source=r.timestamp_source or "segment_estimated",
            seg_type=r.segment_type,
            ai_score=float(r.ai_score) if r.ai_score is not None else None,
            high_value=bool(r.is_high_conversion)
            or (r.ai_score is not None and float(r.ai_score) >= 8),
        )
        for r in offline
        if (r.text_content or "").strip()
    ]
    return units


def _sample_units(units: list[TranscriptUnit]) -> list[TranscriptUnit]:
    """超长话术保留高信号候选，同时均匀覆盖全场避免只看局部。"""
    if len(units) <= MAX_UNITS:
        return units
    priority_limit = min(250, MAX_UNITS // 2)
    priority = sorted(
        units, key=lambda item: (item.signal_score, item.high_value), reverse=True
    )[:priority_limit]
    priority_ids = {id(item) for item in priority}
    remaining = [item for item in units if id(item) not in priority_ids]
    coverage_limit = MAX_UNITS - len(priority)
    step = len(remaining) / max(coverage_limit, 1)
    coverage = [
        remaining[min(len(remaining) - 1, int(i * step))] for i in range(coverage_limit)
    ]
    picked = sorted([*priority, *coverage], key=lambda item: (item.start, item.end))
    logger.info(
        "话术片段超限，多信号优先+全场覆盖抽样 %s -> %s 条", len(units), len(picked)
    )
    return picked


def _unit_text(unit: TranscriptUnit, index: int) -> str:
    text = unit.text[:MAX_UNIT_CHARS]
    prefix = "[高价值] " if unit.high_value else ""
    seg_type = f"|{unit.seg_type}" if unit.seg_type else ""
    evidence = unit.evidence or {}
    signal = (
        f"|信号分{int(unit.signal_score)}"
        f"/评论{int(evidence.get('comment_count') or 0)}"
        f"/高意向{int(evidence.get('high_intent_comment_count') or 0)}"
        f"/钩子{int(evidence.get('hook_count') or 0)}"
        f"/客资窗{int(evidence.get('related_lead_count') or 0)}"
    )
    return (
        f"[{index}] {unit.start:.1f}-{unit.end:.1f}{seg_type}{signal}| {prefix}{text}"
    )


def build_input_text(
    session_title: str | None,
    anchor_name: str | None,
    units: list[TranscriptUnit],
) -> str:
    """把话术时间轴压缩成 AI 可读的文本输入（带行号引用）。"""
    header = f"直播标题：{session_title or '未知'}\n主播：{anchor_name or '未知'}\n"
    lines = [_unit_text(u, i) for i, u in enumerate(units, start=1)]
    return header + "\n".join(lines)


SYSTEM_PROMPT = """你是抖音「零食店避坑」赛道的资深短视频编导。系统会把一场直播的真实话术按
"[行号] 开始秒-结束秒|话术类型|文本" 的格式发给你，你要从里面挑选片段，规划出适合发布的短视频方案。

要求：
1. 共输出 {count} 条短视频方案（素材不足时可少于 {count} 条，宁缺毋滥）。
2. 每条方案由 1-{max_segments} 个片段拼接而成，主题必须明确、内容连贯：
   开头要有吸引人的钩子，中间是干货内容，结尾自然收束。
3. 片段必须用行号引用输入话术中的某一行（segments 里写 index），
   禁止自编时间戳或把时间戳改小改大，程序会按行号取真实时间。
   每条方案片段总时长（按行的起止时间累计）在 {min_seconds}-{max_seconds} 秒之间。
4. “信号分”只来自真实评论、互动指标、钩子和确认客资的可解释计算。优先选择信号强、
   [高价值] 标注的片段、以及「选址避坑、品牌判断、预算测算、供应链、
   毛利损耗、资料钩子、私信承接」这类干货类型；避免无信息量的寒暄和口误。
5. 标题要吸睛但不过度夸大（≤25 字）；发布文案 80-150 字，口语化，
   结尾自然引导「评论区扣1/私信领取资料」类行动；话题 3-6 个，围绕零食店避坑、
   开零食店、品牌选择、选址、预算回本等。
6. 只能基于输入话术的真实内容，不得虚构事实。

严格按如下 JSON 输出，不要输出其他内容：
{{"clips": [{{"title": "标题", "theme": "主题一句话",
  "segments": [{{"index": 行号}}],
  "description": "发布文案", "topics": ["话题1", "话题2"]}}]}}"""


def select_clips(
    db: Session,
    session_id: int,
    *,
    session_title: str | None = None,
    anchor_name: str | None = None,
    count: int = 5,
    user_hint: str | None = None,
) -> dict:
    """调用本地 Ollama 生成短视频方案，返回 {"units": [...], "clips": [...]}。

    返回的 clips 是 AI 原始输出（未校验），由 copywriter 统一校验落库。
    解析失败时重试一次（temperature 降低），仍失败抛异常交由任务层记录。
    """
    units = load_transcript_units(db, session_id)
    if not units:
        raise ValueError(f"场次 #{session_id} 没有已完成的话术，无法选段")
    signal_map = build_multisignal_map(db, session_id, units)
    for unit in units:
        evidence = signal_map.get(int(unit.segment_id or 0), {})
        unit.evidence = evidence
        unit.signal_score = float(evidence.get("signal_score") or 0)
    units = _sample_units(units)

    user_message = build_input_text(session_title, anchor_name, units)
    if user_hint:
        user_message += (
            f"\n\n额外要求（人工指定，可据此调整主题或时间范围）：{user_hint}"
        )

    system_prompt = SYSTEM_PROMPT.format(
        count=count,
        max_segments=MAX_SEGMENTS_PER_CLIP,
        min_seconds=MIN_CLIP_SECONDS,
        max_seconds=MAX_CLIP_SECONDS,
    )

    last_error: Exception | None = None
    for attempt, temperature in enumerate((0.4, 0.1)):
        try:
            content = chat(
                system_prompt,
                user_message,
                temperature=temperature,
                max_tokens=MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
                operation="clip_select",
                session_id=session_id,
                response_mode="json",
            )
            result = json.loads(content)
            clips = result.get("clips")
            if not isinstance(clips, list) or not clips:
                raise ValueError("AI 未返回任何剪辑方案")
            return {"units": units, "clips": clips}
        except Exception as exc:  # noqa: BLE001 - 解析失败统一重试，由任务层记录最终错误
            last_error = exc
            logger.warning("AI 选段第 %s 次尝试失败: %s", attempt + 1, exc)
    raise ValueError(f"AI 选段失败: {last_error}")
