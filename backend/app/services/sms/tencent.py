"""腾讯云短信验证码服务。

流程：
1. 发送验证码 → 腾讯云 API → 用户手机
2. 验证码以 phone:code 形式存入 Redis，有效期 5 分钟
3. 登录时从 Redis 取出校验
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from redis import Redis

from app.core.config import settings
from app.services.security.rate_limit import (
    RateLimitExceeded,
    clear_rate_limit,
    hit_rate_limit,
)

logger = logging.getLogger(__name__)


class TencentSmsError(Exception):
    """腾讯云短信服务异常"""


def _redis_client() -> Redis:
    """创建 Redis 连接。"""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _generate_code(length: int = 6) -> str:
    """使用密码学安全随机数生成固定长度验证码。"""
    lower = 10 ** (length - 1)
    return str(lower + secrets.randbelow(9 * lower))


def _code_digest(phone: str, code: str) -> str:
    """验证码只以摘要形式存入 Redis，避免缓存泄露后直接看到验证码。"""
    return hmac.new(
        settings.JWT_SECRET_KEY.encode("utf-8"),
        f"{phone}:{code}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


async def send_sms_code(phone: str, client_identity: str = "unknown") -> dict:
    """向指定手机号发送验证码。

    步骤：
    1. 检查 Redis 中是否已有未过期的验证码（防止频繁发送）
    2. 生成 6 位随机验证码
    3. 调用腾讯云 SDK 发送短信
    4. 验证码存入 Redis（key = sms_code:{phone}, TTL = 5min）

    Returns:
        {"success": True, "message": "验证码已发送"}
    """
    try:
        hit_rate_limit("sms-ip", client_identity, limit=5, window_seconds=3600)
        hit_rate_limit("sms-phone", phone, limit=3, window_seconds=3600)
    except RateLimitExceeded as exc:
        raise TencentSmsError(str(exc)) from exc

    if not all(
        [
            settings.TENCENT_SMS_APP_ID,
            settings.TENCENT_SMS_APP_KEY,
            settings.TENCENT_SMS_SIGN,
            settings.TENCENT_SMS_TEMPLATE_CODE,
        ]
    ):
        raise TencentSmsError("短信服务尚未完成配置，请联系管理员")

    r = _redis_client()
    key = f"{settings.SMS_CODE_REDIS_PREFIX}{hashlib.sha256(phone.encode()).hexdigest()}"
    try:
        # 同一手机号 60 秒内不能重复发送。
        ttl = r.ttl(key)
        total_ttl = settings.SMS_CODE_EXPIRE_MINUTES * 60
        if ttl > max(0, total_ttl - 60):
            raise TencentSmsError(f"请 {ttl - (total_ttl - 60)} 秒后再试")

        code = _generate_code()
        try:
            from tencentcloud.common import credential
            from tencentcloud.sms.v20210111 import sms_client, models

            cred = credential.Credential(
                settings.TENCENT_SMS_APP_ID,
                settings.TENCENT_SMS_APP_KEY,
            )
            client = sms_client.SmsClient(cred, "ap-guangzhou")
            req = models.SendSmsRequest()
            req.SmsSdkAppId = settings.TENCENT_SMS_APP_ID
            req.SignName = settings.TENCENT_SMS_SIGN
            req.TemplateId = settings.TENCENT_SMS_TEMPLATE_CODE
            req.TemplateParamSet = [code, str(settings.SMS_CODE_EXPIRE_MINUTES)]
            req.PhoneNumberSet = [f"+86{phone}"]

            resp = client.SendSms(req)
            if resp.SendStatusSet[0].Code != "Ok":
                raise TencentSmsError("短信发送失败，请稍后重试")

            logger.info("短信验证码发送成功")
        except TencentSmsError:
            raise
        except Exception as e:
            logger.exception("腾讯云短信 SDK 调用异常")
            raise TencentSmsError("短信服务暂时不可用，请稍后重试") from e

        r.setex(
            key,
            timedelta(minutes=settings.SMS_CODE_EXPIRE_MINUTES),
            _code_digest(phone, code),
        )
        return {"success": True, "message": "验证码已发送"}
    finally:
        r.close()


def verify_sms_code(phone: str, code: str) -> bool:
    """校验手机验证码。

    校验成功后立即删除 Redis 中的验证码（一次性使用）。
    """
    try:
        hit_rate_limit("sms-verify", phone, limit=5, window_seconds=600)
    except RateLimitExceeded:
        return False

    r = _redis_client()
    key = f"{settings.SMS_CODE_REDIS_PREFIX}{hashlib.sha256(phone.encode()).hexdigest()}"
    expected = _code_digest(phone, code)
    try:
        # Lua 脚本让“比较成功并删除”成为一个原子动作，同一验证码只能成功一次。
        matched = r.eval(
            """
            local stored = redis.call('GET', KEYS[1])
            if stored and stored == ARGV[1] then
                redis.call('DEL', KEYS[1])
                return 1
            end
            return 0
            """,
            1,
            key,
            expected,
        )
        if int(matched or 0) == 1:
            clear_rate_limit("sms-verify", phone)
            return True
        return False
    finally:
        r.close()
