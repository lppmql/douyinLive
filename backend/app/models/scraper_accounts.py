"""采集账号表"""
from sqlalchemy import Column, Integer, String, DateTime, Text
from app.models.base import Base, TimestampMixin


class ScraperAccount(Base, TimestampMixin):
    """采集账号 — 存储扫码登录后的浏览器状态"""

    __tablename__ = "scraper_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="账号ID")
    account_name = Column(String(50), nullable=True, comment="账号名称")
    douyin_id = Column(String(100), nullable=True, comment="抖音号")
    storage_state_path = Column(String(500), nullable=True, comment="浏览器状态文件路径")
    user_agent = Column(String(500), nullable=True, comment="User-Agent")
    viewport_width = Column(Integer, nullable=True, comment="视口宽度")
    viewport_height = Column(Integer, nullable=True, comment="视口高度")
    login_status = Column(String(20), default="never", comment="登录状态: logged_in/expired/never")
    expires_at = Column(DateTime, nullable=True, comment="登录态过期时间")
    last_login_at = Column(DateTime, nullable=True, comment="最后登录时间")
    cookies_json = Column(Text, nullable=True, comment="Cookie 备份(JSON)")
    browser_fingerprint_json = Column(Text, nullable=True, comment="浏览器指纹快照(JSON)")

    @property
    def cookie_saved(self) -> bool:
        return bool(self.cookies_json and self.storage_state_path)

    @property
    def fingerprint_saved(self) -> bool:
        return bool(self.browser_fingerprint_json)
