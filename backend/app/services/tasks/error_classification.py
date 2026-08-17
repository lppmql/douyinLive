"""把底层异常转换为页面可解释、可执行的任务失败信息。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskErrorInfo:
    code: str
    stage: str
    retryable: bool


_AUTH_MARKERS = (
    "登录已过期",
    "登录状态不可用",
    "cookie 失效",
    "cookie不可用",
    "cookie 不可用",
    "重新扫码",
    "没有可用采集账号",
    "没有已登录的采集账号",
)
_TIMEOUT_MARKERS = ("timeout", "timed out", "超时", "超过")
_NETWORK_MARKERS = (
    "net::",
    "network",
    "connection reset",
    "connection refused",
    "网络",
    "连接中断",
    "浏览器进程意外退出",
)
_STREAM_MARKERS = ("流地址", "真实拉流", "直播流", "stream")


def classify_task_error(
    error: object,
    *,
    current_stage: str | None = None,
    task_type: str | None = None,
) -> TaskErrorInfo:
    """根据稳定的业务特征分类；未知异常保留可重试能力。"""
    message = str(error or "").strip().lower()
    if any(marker in message for marker in _AUTH_MARKERS):
        return TaskErrorInfo("collector_auth_expired", "authentication", False)
    if any(marker in message for marker in _TIMEOUT_MARKERS):
        return TaskErrorInfo(
            "collector_timeout",
            current_stage or "page_navigation",
            True,
        )
    if task_type == "stream_refresh" or any(marker in message for marker in _STREAM_MARKERS):
        return TaskErrorInfo("stream_unavailable", current_stage or "stream_resolution", True)
    if any(marker in message for marker in _NETWORK_MARKERS):
        return TaskErrorInfo(
            "collector_network_error",
            current_stage or "page_navigation",
            True,
        )
    return TaskErrorInfo("unexpected_error", current_stage or "execution", True)
