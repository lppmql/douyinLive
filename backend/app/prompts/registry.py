"""AI 提示词注册表的数据结构与查询入口。"""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PromptDefinition:
    """一条可写入数据库的默认提示词，版本变化必须显式修改 version。"""

    type: str
    name: str
    version: int
    description: str
    content: str

    def to_record(self) -> dict:
        """转为 SQLAlchemy 模型可直接接收的字段字典。"""
        return asdict(self)


def build_prompt_index(definitions: tuple[PromptDefinition, ...]) -> dict[str, PromptDefinition]:
    """构建类型索引，并在启动和测试时尽早发现重复类型。"""
    index = {definition.type: definition for definition in definitions}
    if len(index) != len(definitions):
        raise ValueError("默认 AI 提示词存在重复 type")
    return index
