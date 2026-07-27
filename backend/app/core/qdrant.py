"""Qdrant 向量数据库客户端（单例）

和 deepseek_client.py 一样用懒初始化模式，第一次调用时才连接。
Qdrant 挂了不影响现有功能——所有方法都降级返回空结果。"""

import logging
from qdrant_client import QdrantClient

from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局客户端（懒初始化）
_client: QdrantClient | None = None


def get_client() -> QdrantClient | None:
    """获取 Qdrant 客户端单例。

    如果 Qdrant 还没启动或连不上，返回 None，
    调用方检查 None 后降级为纯关键词搜索。"""
    global _client
    if _client is None:
        try:
            _client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                timeout=10,  # 10 秒超时，不阻塞主流程
            )
            # 验证连接是否正常
            _client.get_collections()
            logger.info("Qdrant 客户端初始化成功 (host=%s port=%d)", settings.QDRANT_HOST, settings.QDRANT_PORT)
        except Exception as exc:
            logger.warning("Qdrant 连接失败，将降级为纯关键词搜索: %s", exc)
            _client = None
    return _client


def reset_client() -> None:
    """重置客户端（测试用）。"""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
