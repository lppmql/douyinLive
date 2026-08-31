"""使用本地大模型对离线 ASR 终稿做保守纠错。

本模块只负责组批、调用本机 Ollama 和校验返回内容，不直接读写数据库。原始
FunASR 文本由调用方永久保留；任何格式异常、数字变化或大幅改写都会拒绝，
避免为了“通顺”篡改主播真实表达。
"""

from __future__ import annotations

import asyncio
import json
import re
from difflib import SequenceMatcher
from typing import Any

from app.core.config import settings
from app.services.ai.llm_client import async_chat_json
from app.services.asr.hotwords import get_correction_dict_cached


_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?")
_CHINESE_FACT_PATTERN = re.compile(
    r"百分之[零〇一二两三四五六七八九十百千万亿点]+"
    r"|[零〇一二两三四五六七八九十百千万亿点]+"
    r"(?:亿元|万元|平方米|平方|平米|块钱|元|万|亿|家|个|年|月|天|小时|分钟|成)"
)
_PUNCTUATION_PATTERN = re.compile(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()【】\[\]—…]+")
_PROTECTED_REGIONS = (
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
)


def build_correction_batches(
    items: list[dict[str, Any]], max_chars: int, *, start_after_id: int = 0
) -> list[tuple[list[dict[str, Any]], str, str]]:
    """按连续上下文组批，并为每批附带前后各一段只读语境。"""
    if not items:
        return []
    limit = max(300, int(max_chars or 0))
    batches: list[tuple[list[dict[str, Any]], str, str]] = []
    start = next(
        (index for index, item in enumerate(items) if int(item["id"]) > start_after_id),
        len(items),
    )
    while start < len(items):
        end = start
        used = 0
        while end < len(items):
            text = str(items[end].get("text") or "")
            cost = len(text) + 32
            if end > start and used + cost > limit:
                break
            used += cost
            end += 1
        batch = items[start:end]
        before = str(items[start - 1].get("text") or "") if start else ""
        after = str(items[end].get("text") or "") if end < len(items) else ""
        batches.append((batch, before, after))
        start = end
    return batches


def _validate_corrected_text(source: str, corrected: str) -> bool:
    """只接受数字不变、长度合理且与原话高度相似的保守修改。"""
    source = str(source or "").strip()
    corrected = str(corrected or "").strip().replace(",", "，")
    if not source or not corrected:
        return False
    if _NUMBER_PATTERN.findall(source) != _NUMBER_PATTERN.findall(corrected):
        return False
    if _CHINESE_FACT_PATTERN.findall(source) != _CHINESE_FACT_PATTERN.findall(
        corrected
    ):
        return False
    if any(source.count(term) != corrected.count(term) for term in _PROTECTED_REGIONS):
        return False
    protected_terms = {
        str(term).strip()
        for term in get_correction_dict_cached().values()
        if str(term).strip() and str(term).strip() in source
    }
    if any(source.count(term) != corrected.count(term) for term in protected_terms):
        return False
    length_ratio = len(corrected) / max(1, len(source))
    if not 0.8 <= length_ratio <= 1.2:
        return False
    compact_source = "".join(source.split())
    compact_corrected = "".join(corrected.split())
    return (
        SequenceMatcher(
            a=compact_source,
            b=compact_corrected,
            autojunk=False,
        ).ratio()
        >= 0.75
    )


def validate_correction_payload(
    source_items: list[dict[str, Any]], payload: dict[str, Any]
) -> dict[int, str]:
    """校验模型必须逐条原样返回 ID；可疑单条回退到输入文本。"""
    result_items = payload.get("items")
    if not isinstance(result_items, list):
        raise ValueError("本地模型纠错结果缺少 items 数组")

    source_by_id = {
        int(item["id"]): str(item.get("text") or "") for item in source_items
    }
    result_by_id: dict[int, str] = {}
    result_ids: list[int] = []
    for item in result_items:
        if not isinstance(item, dict) or "id" not in item:
            raise ValueError("本地模型纠错结果包含无效条目")
        item_id = int(item["id"])
        if item_id in result_by_id:
            raise ValueError("本地模型纠错结果包含重复 ID")
        result_ids.append(item_id)
        result_by_id[item_id] = str(item.get("text") or "").replace(",", "，")
    if result_ids != list(source_by_id):
        raise ValueError("本地模型纠错结果与输入段落 ID 不一致")

    return {
        item_id: corrected
        if _validate_corrected_text(source_by_id[item_id], corrected)
        and _PUNCTUATION_PATTERN.sub("", source_by_id[item_id])
        != _PUNCTUATION_PATTERN.sub("", corrected)
        else source_by_id[item_id]
        for item_id, corrected in result_by_id.items()
    }


def _correction_glossary() -> list[str]:
    """复用项目手工维护的可靠词典，去重后限制提示词体积。"""
    terms = {
        str(term).strip()
        for term in get_correction_dict_cached().values()
        if str(term).strip()
    }
    return sorted(terms, key=lambda item: (-len(item), item))[:300]


async def correct_transcript_batch(
    items: list[dict[str, Any]],
    *,
    context_before: str = "",
    context_after: str = "",
    session_id: int | None = None,
) -> dict[int, str]:
    """调用本机 Ollama 纠正一批连续话术，并返回通过校验的文本。"""
    if not items:
        return {}
    payload = await asyncio.wait_for(
        async_chat_json(
            system_prompt=(
                "你是零食店直播话术的中文 ASR 保守纠错器。"
                "只修正确认度高的同音字、近音字、品牌名、行业术语和明显断句；"
                "不得总结、扩写、删减事实，不得改变数字、金额、地区、人物称呼和语气。"
                "结合零食店语境重点识别常见近音错误，例如："
                "郝某想来/好好想来→好想来，赵某一名→赵一鸣，"
                "临食店/临时店→零食店，一线零点→一线品牌，二加牌→二线品牌，"
                "投的美食美/投的美食品→投入的成本。只有语境明确时才允许替换。"
                "context_before 与 context_after 只用于理解上下文，禁止输出或改写它们。"
                "必须返回 JSON 对象，格式为"
                '{"items":[{"id":原数字ID,"text":"修正后的原段落"}]}。'
                "items 的数量、顺序和 ID 必须与输入完全一致。"
            ),
            user_message=json.dumps(
                {
                    "context_before": context_before,
                    "items": items,
                    "context_after": context_after,
                    "trusted_glossary": _correction_glossary(),
                },
                ensure_ascii=False,
            ),
            temperature=0.0,
            operation="asr_transcript_correction",
            session_id=session_id,
            prompt_name="asr_conservative_correction",
            prompt_version=1,
        ),
        timeout=settings.ASR_LLM_CORRECTION_TIMEOUT_SECONDS,
    )
    return validate_correction_payload(items, payload)
