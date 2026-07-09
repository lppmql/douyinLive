"""
独立采集 Worker 进程

Phase 3: 骨架 — 仅包含启动入口和日志
Phase 4: 完善 — 实现定时轮询、自动采集、调度逻辑

启动方式:
    cd backend && source .venv/bin/activate
    python -m workers.scraper_worker
"""
import asyncio
import signal
import sys

from app.core.logger import logger


async def main():
    logger.info("=" * 50)
    logger.info("Scraper Worker 启动")
    logger.info("Phase 3 骨架 — 等待 Phase 4 完善")
    logger.info("=" * 50)

    # 保持进程运行
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("收到停止信号，Worker 退出")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            pass

    await stop_event.wait()
    logger.info("Scraper Worker 已退出")


if __name__ == "__main__":
    asyncio.run(main())
