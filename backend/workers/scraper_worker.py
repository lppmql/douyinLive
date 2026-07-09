"""
独立采集 Worker 进程

整合 scheduler + monitor + collector，独立于 FastAPI 进程运行。

启动:
    cd backend && source .venv/bin/activate
    python -m workers.scraper_worker

环境变量:
    MONITOR_ENABLED=true     # 启用自动采集
    MONITOR_MOCK_MODE=true   # Mock 模式（无真实直播时使用）
"""
import asyncio
import signal
import sys

from app.core.config import settings
from app.core.logger import logger
from app.core.database import engine
from app.services.collector.scheduler import scheduler_manager
from app.services.collector.browser import browser_manager


async def main():
    logger.info("=" * 50)
    logger.info("Scraper Worker 启动")
    logger.info(f"  MONITOR_ENABLED={settings.MONITOR_ENABLED}")
    logger.info(f"  MONITOR_MOCK_MODE={settings.MONITOR_MOCK_MODE}")
    logger.info(f"  CHECK_INTERVAL={settings.MONITOR_CHECK_INTERVAL}s")
    logger.info("=" * 50)

    # 检查数据库连接
    try:
        with engine.connect() as conn:
            logger.info("✅ 数据库连接成功")
    except Exception as e:
        logger.error(f"❌ 数据库连接失败: {e}")
        sys.exit(1)

    # 启动调度器
    if settings.MONITOR_ENABLED:
        await scheduler_manager.start()
        logger.info("✅ 采集调度器已启动")
    else:
        logger.info("⏸️  采集调度器未启用 (MONITOR_ENABLED=false)")
        logger.info("   设置 MONITOR_ENABLED=true 启用自动采集")

    # 等待停止信号
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，正在关闭...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    await stop_event.wait()

    # 优雅关闭
    if scheduler_manager.running:
        await scheduler_manager.stop()
    await browser_manager.close()
    logger.info("Scraper Worker 已退出")


if __name__ == "__main__":
    asyncio.run(main())
