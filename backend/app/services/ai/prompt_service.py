"""提示词模板管理服务"""
import logging
from typing import List

from sqlalchemy.orm import Session

from app.models.prompt_templates import PromptTemplate

logger = logging.getLogger(__name__)


def get_prompt(db: Session, type: str, version: int | None = None) -> str | None:
    """获取指定类型和版本的提示词内容

    Args:
        db: 数据库会话
        type: 提示词类型
        version: 版本号，None 表示最新版

    Returns:
        提示词内容，找不到返回 None
    """
    q = db.query(PromptTemplate).filter(PromptTemplate.type == type)
    if version:
        q = q.filter(PromptTemplate.version == version)
    else:
        q = q.order_by(PromptTemplate.version.desc())
    template = q.first()
    if template:
        return template.content
    logger.warning("未找到提示词模板: type=%s, version=%s", type, version)
    return None


def create_prompt(db: Session, type: str, content: str,
                  name: str | None = None, description: str | None = None) -> PromptTemplate:
    """创建新版本提示词（自动递增版本号）"""
    latest = db.query(PromptTemplate).filter(
        PromptTemplate.type == type
    ).order_by(PromptTemplate.version.desc()).first()
    version = (latest.version + 1) if latest else 1
    t = PromptTemplate(
        type=type,
        name=name or f"{type}_v{version}",
        content=content,
        version=version,
        description=description,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    logger.info("创建提示词模板: type=%s, version=%d", type, version)
    return t


def list_prompts(db: Session, type: str | None = None,
                 skip: int = 0, limit: int = 100) -> List[PromptTemplate]:
    """列出提示词模板"""
    q = db.query(PromptTemplate)
    if type:
        q = q.filter(PromptTemplate.type == type)
    return q.order_by(PromptTemplate.type, PromptTemplate.version.desc()).offset(skip).limit(limit).all()


def delete_prompt(db: Session, prompt_id: int) -> bool:
    """删除提示词模板"""
    t = db.query(PromptTemplate).get(prompt_id)
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True
