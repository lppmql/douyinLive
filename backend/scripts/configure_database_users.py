"""幂等创建后端受限 MySQL 账号。

该脚本只在启动阶段使用 root 管理凭据；应用运行时继续使用 ``DB_USER``，
避免把数据库管理员权限长期交给 FastAPI。
"""

from __future__ import annotations

import re

import pymysql

from app.core.config import settings


_SAFE_NAME = re.compile(r"[A-Za-z0-9_]{1,64}")


def _safe_name(name: str, label: str) -> str:
    value = name.strip()
    if not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"{label} 只允许字母、数字和下划线")
    return value


def _create_or_update_user(cursor, user: str, password: str) -> None:
    """创建或更新固定 ``user@%``；密码始终走参数绑定，不拼进 SQL。"""
    # PyMySQL 在带参数语句中使用 ``%`` 做占位格式化，因此主机通配符需写成 ``%%``。
    cursor.execute(f"CREATE USER IF NOT EXISTS '{user}'@'%%' IDENTIFIED BY %s", (password,))
    cursor.execute(f"ALTER USER '{user}'@'%%' IDENTIFIED BY %s", (password,))


def configure_database_users() -> None:
    root_password = settings.MYSQL_ROOT_PASSWORD or (
        settings.DB_PASSWORD if settings.DB_USER.lower() == "root" else ""
    )
    if not root_password:
        raise ValueError("缺少 MYSQL_ROOT_PASSWORD，无法创建受限数据库账号")

    app_user = _safe_name(settings.DB_USER, "DB_USER")
    app_database = _safe_name(settings.DB_NAME, "DB_NAME")
    if app_user.lower() == "root":
        raise ValueError("业务账号不能使用 root")
    if len(settings.DB_PASSWORD) < 7:
        raise ValueError("DB_PASSWORD 至少需要 7 个字符")

    connection = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user="root",
        password=root_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{app_database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            _create_or_update_user(cursor, app_user, settings.DB_PASSWORD)
            cursor.execute(f"GRANT ALL PRIVILEGES ON `{app_database}`.* TO '{app_user}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()

    print(f"MySQL 受限账号已配置：{app_user}@% -> {app_database}")


if __name__ == "__main__":
    configure_database_users()
