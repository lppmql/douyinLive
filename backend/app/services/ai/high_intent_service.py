"""高意向用户识别服务 — AI 从评论中识别高意向用户"""
import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.comments import Comment
from app.models.high_intent_users import HighIntentUser
from app.services.ai.deepseek_client import chat_json
from app.services.ai.prompt_service import get_prompt_template

logger = logging.getLogger(__name__)


def _match_real_comment(comments: list[Comment], item: dict[str, Any]) -> Comment | None:
    """只接受可唯一追溯的评论序号或完全一致的唯一昵称。"""
    comment_index = item.get("comment_index", item.get("index"))
    if isinstance(comment_index, int) and 1 <= comment_index <= len(comments):
        return comments[comment_index - 1]

    user_name = item.get("user_name", item.get("name", ""))
    if not user_name:
        return None
    exact_matches = [comment for comment in comments if comment.user_nickname == user_name]
    return exact_matches[0] if len(exact_matches) == 1 else None


def identify_high_intent(session_id: int, db: Session | None = None) -> list[dict[str, Any]]:
    """从指定场次的评论中识别高意向用户"""
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False

    try:
        # 获取评论（排除已标记高意向的）
        comments = db.query(Comment).filter(
            Comment.session_id == session_id,
            Comment.is_high_intent == 0,
        ).order_by(Comment.created_at.desc()).limit(200).all()

        if not comments:
            logger.info("场次 %d 没有未处理的评论", session_id)
            return []

        # 拼接评论列表
        comments_text = "\n".join([
            f"[{i + 1}] {c.user_nickname or '匿名'}: {c.comment_content or ''}"
            for i, c in enumerate(comments)
        ])

        prompt_template = get_prompt_template(db, "high_intent")
        if not prompt_template:
            logger.error("未找到 high_intent 提示词模板")
            return []

        try:
            result = chat_json(
                system_prompt=(
                    "你是零食店开店避坑知识科普直播的意向分析员。"
                    "只根据真实评论识别选址、预算、品牌、供应链、毛利损耗、证照或资料领取意向，"
                    "不得猜测联系方式，请按JSON格式输出。"
                ),
                user_message=prompt_template.content.replace("{comments}", comments_text),
                temperature=0.3,
                operation="high_intent_detection",
                session_id=session_id,
                prompt_name=prompt_template.type,
                prompt_version=prompt_template.version,
            )
        except Exception as e:
            logger.error("DeepSeek 高意向用户识别失败: %s", e)
            return []

        # 解析结果并入库
        identified = result.get("users", result.get("high_intent_users", []))
        if not identified:
            logger.info("场次 %d 未识别出高意向用户", session_id)
            return []

        saved = []
        for item in identified:
            matched_comment = _match_real_comment(comments, item)
            user_name = item.get("user_name", item.get("name", ""))

            if not matched_comment:
                logger.warning("场次 %d 的AI意向结果无法匹配真实评论，已跳过: %s", session_id, item)
                continue

            existing = db.query(HighIntentUser).filter(
                HighIntentUser.session_id == session_id,
                HighIntentUser.comment_id == matched_comment.id,
            ).first()
            if existing:
                continue

            user_name = matched_comment.user_nickname or user_name

            user = HighIntentUser(
                session_id=session_id,
                comment_id=matched_comment.id if matched_comment else None,
                user_name=user_name,
                phone=None,
                product_interest=item.get("product_interest", item.get("product", "")),
                intent_level=item.get("intent_level", "medium"),
                intent_reason=item.get("reason", item.get("intent_reason", "")),
            )
            db.add(user)

            # 更新评论标记
            if matched_comment:
                matched_comment.is_high_intent = 1

            saved.append({
                "user_name": user_name,
                "product_interest": user.product_interest,
                "intent_level": user.intent_level,
            })

        db.commit()
        logger.info("场次 %d 识别出 %d 个高意向用户", session_id, len(saved))
        return saved

    except Exception as e:
        logger.exception("高意向用户识别异常: %s", e)
        db.rollback()
        return []
    finally:
        if should_close:
            db.close()


def list_high_intent_users(
    db: Session,
    session_id: int | None = None,
    intent_level: str | None = None,
    is_contacted: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[HighIntentUser]:
    """查询高意向用户"""
    q = db.query(HighIntentUser)
    if session_id:
        q = q.filter(HighIntentUser.session_id == session_id)
    if intent_level:
        q = q.filter(HighIntentUser.intent_level == intent_level)
    if is_contacted is not None:
        q = q.filter(HighIntentUser.is_contacted == is_contacted)
    return q.order_by(HighIntentUser.created_at.desc()).offset(skip).limit(limit).all()
