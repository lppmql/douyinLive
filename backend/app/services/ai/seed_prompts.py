"""把代码内受版本控制的默认提示词补入数据库。"""

from sqlalchemy.orm import Session

from app.models.prompt_templates import PromptTemplate
from app.prompts import DEFAULT_PROMPTS


def seed_prompts(db: Session) -> None:
    """只补缺失的默认版本，不覆盖用户在数据库中创建的新版本。"""
    inserted = 0
    for definition in DEFAULT_PROMPTS:
        exists = (
            db.query(PromptTemplate.id)
            .filter(
                PromptTemplate.type == definition.type,
                PromptTemplate.version == definition.version,
            )
            .first()
        )
        if exists:
            continue
        db.add(PromptTemplate(**definition.to_record()))
        inserted += 1
    if inserted:
        db.commit()
        print(f"已补充 {inserted} 条零食店直播领域默认提示词")
