"""单 FunASR 连接的直播/终稿分时调度器。"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

AsrLane = Literal["realtime", "offline"]


def choose_asr_lane(
    realtime_waiting: bool,
    offline_waiting: bool,
    *,
    live_streak: int,
    live_quota: int,
) -> AsrLane | None:
    """根据等待队列和直播连续执行次数选择下一条逻辑通道。"""
    if realtime_waiting and not offline_waiting:
        return "realtime"
    if offline_waiting and not realtime_waiting:
        return "offline"
    if not realtime_waiting and not offline_waiting:
        return None
    return "offline" if live_streak >= max(1, live_quota) else "realtime"


class AsrLaneCoordinator:
    """允许两个逻辑任务等待，但每次只放行一条 FunASR 连接。"""

    def __init__(self, live_quota: int = 3) -> None:
        self._condition = asyncio.Condition()
        self._live_quota = max(1, int(live_quota))
        self._live_streak = 0
        self._active_lane: AsrLane | None = None
        self._waiting: dict[AsrLane, int] = {"realtime": 0, "offline": 0}

    async def acquire(self, lane: AsrLane) -> None:
        """等待并取得唯一模型连接使用权。"""
        async with self._condition:
            self._waiting[lane] += 1
            try:
                await self._condition.wait_for(lambda: self._can_run(lane))
                self._active_lane = lane
            finally:
                self._waiting[lane] -= 1

    def _can_run(self, lane: AsrLane) -> bool:
        if self._active_lane is not None:
            return False
        selected = choose_asr_lane(
            self._waiting["realtime"] > 0,
            self._waiting["offline"] > 0,
            live_streak=self._live_streak,
            live_quota=self._live_quota,
        )
        return selected == lane

    async def release(self, lane: AsrLane) -> None:
        """释放模型连接并更新下一轮权重。"""
        async with self._condition:
            if self._active_lane != lane:
                raise RuntimeError(f"ASR 调度释放通道不一致: active={self._active_lane}, lane={lane}")
            self._active_lane = None
            self._live_streak = self._live_streak + 1 if lane == "realtime" else 0
            self._condition.notify_all()

    @asynccontextmanager
    async def slot(self, lane: AsrLane) -> AsyncIterator[None]:
        """以异步上下文方式安全取得并释放模型连接。"""
        await self.acquire(lane)
        try:
            yield
        finally:
            await self.release(lane)
