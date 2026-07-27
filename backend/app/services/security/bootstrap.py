"""首次安装时创建管理员。

数据库已经有用户时什么都不做；只有全新安装才读取根目录 .env。这样不会再出现
人人都知道的默认密码，也不会改动现有管理员。
"""

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User


def bootstrap_admin_if_empty(db: Session) -> bool:
    """在空用户表中创建唯一的首次管理员，成功创建返回 True。"""
    if db.query(User.id).first() is not None:
        return False

    username = settings.BOOTSTRAP_ADMIN_USERNAME.strip()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD
    if not username or len(password) < 15:
        raise RuntimeError(
            "全新安装必须在根目录 .env 配置 BOOTSTRAP_ADMIN_USERNAME，"
            "并设置至少 15 位的 BOOTSTRAP_ADMIN_PASSWORD"
        )

    db.add(
        User(
            username=username,
            password_hash=get_password_hash(password),
            nickname="系统管理员",
            roles=["R_SUPER"],
            status="active",
        )
    )
    db.commit()
    return True
