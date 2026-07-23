"""AI 提示词统一入口。"""

from app.prompts.registry import PromptDefinition, build_prompt_index
from app.prompts.snack_store import DEFAULT_PROMPTS
from app.prompts.system import SYSTEM_PROMPTS, get_system_prompt


DEFAULT_PROMPT_INDEX = build_prompt_index(DEFAULT_PROMPTS)


def get_default_prompt(prompt_type: str) -> PromptDefinition | None:
    """获取代码内受版本控制的默认用户提示词。"""
    return DEFAULT_PROMPT_INDEX.get(prompt_type)


__all__ = [
    "DEFAULT_PROMPTS",
    "DEFAULT_PROMPT_INDEX",
    "SYSTEM_PROMPTS",
    "PromptDefinition",
    "get_default_prompt",
    "get_system_prompt",
]
