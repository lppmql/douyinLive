import logging

from app.core.observability import configure_logging


def setup_logger(name: str = "douyin_live") -> logging.Logger:
    """配置根日志，确保所有模块都带 Trace ID。"""
    configure_logging()
    return logging.getLogger(name)


logger = setup_logger()
