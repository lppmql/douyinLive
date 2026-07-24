"""腾讯云短信验证码服务。

流程：
1. 发送验证码 → 腾讯云 API → 用户手机
2. 验证码以 phone:code 形式存入 Redis，有效期 5 分钟
3. 登录时从 Redis 取出校验
"""

import logging
import random
from datetime import timedelta

from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)


class TencentSmsError(Exception):
    """腾讯云短信服务异常"""


def _redis_client() -> Redis:
    """创建 Redis 连接。"""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)


def _generate_code(length: int = 6) -> str:
    """生成纯数字验证码。"""
    return str(random.randint(10 ** (length - 1), 10**length - 1))


async def send_sms_code(phone: str) -> dict:
    """向指定手机号发送验证码。

    步骤：
    1. 检查 Redis 中是否已有未过期的验证码（防止频繁发送）
    2. 生成 6 位随机验证码
    3. 调用腾讯云 SDK 发送短信
    4. 验证码存入 Redis（key = sms_code:{phone}, TTL = 5min）

    Returns:
        {"success": True, "message": "验证码已发送"}
    """
    r = _redis_client()
    key = f"{settings.SMS_CODE_REDIS_PREFIX}{phone}"

    # 检查是否 60 秒内重复发送
    ttl = r.ttl(key)
    if ttl > 240:  # 还有 4 分钟以上有效期，说明刚发过
        remaining = ttl - 240
        raise TencentSmsError(f"请 {remaining} 秒后再试")

    code = _generate_code()

    # 如果 APP_ID 为空，进入开发/测试模式（不真正发短信）
    if not settings.TENCENT_SMS_APP_ID:
        logger.warning("短信 SDK_APP_ID 未配置，验证码 %s 不发送（开发模式）", code)
    else:
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
                raise TencentSmsError(f"短信发送失败: {resp.SendStatusSet[0].Message}")

            logger.info("验证码已发送至 %s, code=%s", phone, code)
        except TencentSmsError:
            raise
        except Exception as e:
            logger.exception("腾讯云短信 SDK 调用异常")
            raise TencentSmsError(f"短信服务异常: {e}") from e

    # 存入 Redis，有效期 5 分钟
    r.setex(key, timedelta(minutes=settings.SMS_CODE_EXPIRE_MINUTES), code)
    r.close()

    return {"success": True, "message": "验证码已发送"}


def verify_sms_code(phone: str, code: str) -> bool:
    """校验手机验证码。

    校验成功后立即删除 Redis 中的验证码（一次性使用）。
    """
    r = _redis_client()
    key = f"{settings.SMS_CODE_REDIS_PREFIX}{phone}"

    stored = r.get(key)
    if stored is None:
        r.close()
        return False

    if stored != code:
        r.close()
        return False

    # 校验成功，立即删除（一次性使用）
    r.delete(key)
    r.close()
    return True
