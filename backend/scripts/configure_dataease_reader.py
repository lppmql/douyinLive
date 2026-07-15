"""创建 DataEase 专用只读 MySQL 账号。"""
import re

import pymysql

from app.core.config import settings


def configure_reader() -> None:
    user = settings.DATAEASE_READER_USER.strip()
    password = settings.DATAEASE_READER_PASSWORD
    database = settings.DB_NAME.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,32}", user):
        raise ValueError("DATAEASE_READER_USER 只允许字母、数字和下划线")
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", database):
        raise ValueError("DB_NAME 不是安全的 MySQL 数据库名")
    if len(password) < 12:
        raise ValueError("DATAEASE_READER_PASSWORD 至少需要 12 个字符")

    connection = pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE USER IF NOT EXISTS '{user}'@'%%' IDENTIFIED BY %s", (password,))
            cursor.execute(f"ALTER USER '{user}'@'%%' IDENTIFIED BY %s", (password,))
            cursor.execute(f"GRANT SELECT, SHOW VIEW ON `{database}`.* TO '{user}'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()
    print(f"DataEase 只读账号已配置: {user}@% -> {database} (SELECT, SHOW VIEW)")


if __name__ == "__main__":
    configure_reader()
