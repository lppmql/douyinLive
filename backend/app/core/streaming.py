"""确保 SSE 客户端断开时，及时关闭上游异步生成器。"""

import anyio
from starlette.responses import StreamingResponse


class ClosingStreamingResponse(StreamingResponse):
    """除等待 token 外，也覆盖生成器暂停在 yield、下游发送阻塞的断开场景。"""

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                # Starlette 已取消发送任务时，仍须让上游模型连接完成清理。
                with anyio.CancelScope(shield=True):
                    await close()
