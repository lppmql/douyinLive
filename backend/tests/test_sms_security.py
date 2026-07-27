"""短信验证码安全回归测试。"""

import asyncio

import pytest

from app.services.sms import tencent


def test_sms_code_uses_fixed_length_secure_random(monkeypatch):
    """随机值为零时仍应得到六位验证码，且不出现前导长度错误。"""
    monkeypatch.setattr(tencent.secrets, "randbelow", lambda _upper: 0)

    assert tencent._generate_code() == "100000"


def test_sms_code_is_not_stored_as_plain_text():
    """Redis 中保存的是不可逆摘要，不是用户收到的六位明文。"""
    digest = tencent._code_digest("13800138000", "123456")

    assert digest != "123456"
    assert len(digest) == 64


def test_unconfigured_sms_never_logs_or_returns_debug_code(monkeypatch):
    """未配置短信供应商时明确失败，不能把验证码写到日志或响应里。"""
    monkeypatch.setattr(tencent, "hit_rate_limit", lambda *_args, **_kwargs: 1)
    monkeypatch.setattr(tencent.settings, "TENCENT_SMS_APP_ID", "")
    monkeypatch.setattr(tencent.settings, "TENCENT_SMS_APP_KEY", "")
    monkeypatch.setattr(tencent.settings, "TENCENT_SMS_SIGN", "")
    monkeypatch.setattr(tencent.settings, "TENCENT_SMS_TEMPLATE_CODE", "")

    with pytest.raises(tencent.TencentSmsError, match="短信服务尚未完成配置"):
        asyncio.run(tencent.send_sms_code("13800138000", "127.0.0.1"))
