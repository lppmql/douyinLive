"""
统一 API 响应包装 — 消除 auth.py 和 user_mgmt.py 中重复的 _ok() 函数。

SoybeanAdmin 前端期望的响应格式：
    {"code": "0000", "data": {...}, "msg": "success"}

使用方式：
    from app.core.response import ok_response
    return ok_response(data=user_info)
    return ok_response(data=token, msg="登录成功")
"""

from typing import Any


def ok_response(data: Any = None, msg: str = "success") -> dict[str, Any]:
    """
    包装 SoybeanAdmin 兼容的成功响应。

    Args:
        data: 响应数据体（dict、list、Pydantic model 等）
        msg:  提示消息，默认 "success"

    Returns:
        {"code": "0000", "data": ..., "msg": ...}
    """
    return {"code": "0000", "data": data, "msg": msg}
