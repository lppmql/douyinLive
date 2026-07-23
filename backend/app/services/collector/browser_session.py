"""协调所有需要复用采集账号登录态的浏览器操作。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal


BrowserLeaseKind = Literal["refresh", "monitor", "account", "login", "maintenance"]


class BrowserSessionCoordinator:
    """为共享 BrowserContext 提供刷新优先、可观测的独占租约。

    刷新和监控可以同时保持业务上的开启状态，但浏览器页面不能并发使用。
    当刷新开始等待时，后来的监控任务会让路；已经打开的监控页面会先安全结束。
    """

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._active_owner: str | None = None
        self._active_kind: BrowserLeaseKind | None = None
        self._active_task: asyncio.Task | None = None
        self._active_depth = 0
        self._waiting_refresh = 0
        self._waiting_regular = 0

    @asynccontextmanager
    async def lease(
        self,
        owner: str,
        *,
        kind: BrowserLeaseKind = "maintenance",
    ) -> AsyncIterator[None]:
        """独占使用浏览器登录会话；同一协程内嵌套调用不会自锁。"""
        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("浏览器会话租约必须在 asyncio 任务中使用")

        async with self._condition:
            if self._active_task is current_task:
                self._active_depth += 1
            else:
                is_refresh = kind == "refresh"
                if is_refresh:
                    self._waiting_refresh += 1
                else:
                    self._waiting_regular += 1
                try:
                    await self._condition.wait_for(
                        lambda: self._active_task is None
                        and (is_refresh or self._waiting_refresh == 0)
                    )
                    self._active_task = current_task
                    self._active_owner = owner
                    self._active_kind = kind
                    self._active_depth = 1
                finally:
                    if is_refresh:
                        self._waiting_refresh = max(0, self._waiting_refresh - 1)
                    else:
                        self._waiting_regular = max(0, self._waiting_regular - 1)
                    self._condition.notify_all()

        try:
            yield
        finally:
            async with self._condition:
                if self._active_task is current_task:
                    self._active_depth = max(0, self._active_depth - 1)
                    if self._active_depth == 0:
                        self._active_task = None
                        self._active_owner = None
                        self._active_kind = None
                        self._condition.notify_all()

    def snapshot(self) -> dict[str, str | int | None]:
        """返回页面和日志可直接展示的轻量排队状态。"""
        return {
            "active_owner": self._active_owner,
            "active_kind": self._active_kind,
            "waiting_refresh": self._waiting_refresh,
            "waiting_regular": self._waiting_regular,
        }

    async def wait_for_refresh_waiter(self, timeout_seconds: float = 1) -> None:
        """等待刷新进入优先队列，主要供并发回归测试和安全交接使用。"""
        deadline = asyncio.get_running_loop().time() + max(0.1, timeout_seconds)
        while self._waiting_refresh == 0:
            if asyncio.get_running_loop().time() >= deadline:
                raise asyncio.TimeoutError("等待刷新浏览器租约超时")
            await asyncio.sleep(0.005)

    async def wait_until_idle(self, timeout_seconds: float = 15) -> bool:
        """等待所有持有者和等待者离开，关闭 Chromium 前使用。"""
        deadline = asyncio.get_running_loop().time() + max(0.1, timeout_seconds)
        while (
            self._active_task is not None
            or self._waiting_refresh > 0
            or self._waiting_regular > 0
        ):
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(0.05)
        return True
