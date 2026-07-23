"""任务控制领域异常。"""

from typing import Any


class TaskCancellationRequested(RuntimeError):
    """用户已经请求安全停止，执行器应在当前检查点退出。"""


class TaskBatchFailed(RuntimeError):
    """批处理全部失败，同时保留可供页面展示的结构化结果。"""

    def __init__(self, message: str, result: dict[str, Any] | None = None):
        super().__init__(message)
        self.result = result or {}
