"""
统一异常处理器 — 把 FastAPI 默认的 {"detail":"..."} 转成前端认识的样子。

背景：
  前端 SoybeanAdmin 的 backendRequest 拦截器在 onBackendFail 里找 body.msg 来显示错误消息。
  但 FastAPI 抛 HTTPException 时默认返回 {"detail":"..."}，没有 msg 字段。
  结果就是：后端报错了，前端用户看不到错误消息（弹窗不出来）。

这个模块做的事：
  1. 拦截所有 HTTPException → 返回 {"code":"XXXX","msg":"错误描述"}
  2. 拦截 Pydantic 验证错误（422）→ 返回中文可读的校验错误
  3. 拦截未知异常（500）→ 返回统一的服务端错误，不泄露内部细节
"""

import traceback
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import logger


# ── 状态码 → 业务错误码映射 ──
# 前端通过 code 判断错误类型，而非解析 HTTP 状态码
_STATUS_TO_CODE: dict[int, str] = {
    400: "0400",  # 请求参数错误
    401: "0401",  # 未登录/token 失效
    403: "0403",  # 无权限
    404: "0404",  # 资源不存在
    409: "0409",  # 资源冲突
    422: "0422",  # 参数校验失败
    429: "0429",  # 请求过于频繁
    500: "0500",  # 服务端内部错误
    502: "0502",  # 上游服务不可用
}


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    统一处理所有 HTTPException（包括 FastAPI 内部抛的）。

    输出格式：
        {"code": "0404", "msg": "场次不存在"}
    前端 backendRequest.onBackendFail 可以正确显示 msg。
    """
    code = _STATUS_TO_CODE.get(exc.status_code, f"{exc.status_code:04d}")
    logger.warning(
        "HTTP %s [%s] %s %s → %s",
        exc.status_code,
        code,
        request.method,
        request.url.path,
        str(exc.detail)[:200],
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "msg": str(exc.detail), "data": None},
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    统一处理 Pydantic 校验失败（FastAPI 默认 422）。

    把 Pydantic 的嵌套错误结构转成中文可读的一句话。
    前端用户看到的是：「参数校验失败：username - 字段必填」
    """
    # 提取第一个校验错误，转成人类可读的中文
    messages: list[str] = []
    for error in exc.errors():
        loc = " → ".join(str(part) for part in error["loc"])
        msg = error.get("msg", "校验失败")
        messages.append(f"{loc}: {msg}")

    detail = "；".join(messages[:3])  # 最多显示 3 条，避免太长
    if len(messages) > 3:
        detail += f"（还有 {len(messages) - 3} 个错误）"

    logger.warning("校验失败 %s %s → %s", request.method, request.url.path, detail[:200])
    return JSONResponse(
        status_code=422,
        content={"code": "0422", "msg": f"参数校验失败：{detail}", "data": None},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    兜底处理所有未捕获异常（500）。

    不暴露内部 traceback 给前端，只记录到日志。
    """
    logger.error(
        "未处理异常 %s %s: %s\n%s",
        request.method,
        request.url.path,
        str(exc)[:300],
        traceback.format_exc(),
    )
    return JSONResponse(
        status_code=500,
        content={"code": "0500", "msg": "服务端内部错误，请稍后重试或联系管理员", "data": None},
    )


def register_exception_handlers(app):
    """
    在 FastAPI app 实例上注册所有异常处理器。

    用这个函数而不是装饰器，是为了保持 main.py 的整洁：
    在 main.py 里只需一行 register_exception_handlers(app)。

    使用方式（main.py）：
        from app.core.error_handler import register_exception_handlers
        register_exception_handlers(app)
    """
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
