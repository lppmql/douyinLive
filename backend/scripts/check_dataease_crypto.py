"""Validate the DataEase browser encryption key without exposing credentials."""

from __future__ import annotations

import argparse
import base64
import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


KEY_SEPARATOR = base64.urlsafe_b64encode(b"-pk_separator-").decode()
AES_IV = b"0000000000000000"


class DataEaseCryptoError(RuntimeError):
    """Raised when DataEase does not provide a usable browser encryption key."""


@dataclass(frozen=True)
class CryptoCheckResult:
    key_size: int


def decode_public_key(dekey: str) -> rsa.RSAPublicKey:
    """Decode DataEase's AES-wrapped DER RSA public key response."""
    try:
        encrypted_public_key, aes_key = dekey.split(KEY_SEPARATOR, 1)
        if len(aes_key) != 16:
            raise ValueError("AES key must contain 16 characters")

        decryptor = Cipher(algorithms.AES(aes_key.encode()), modes.CBC(AES_IV)).decryptor()
        padded_key = decryptor.update(base64.b64decode(encrypted_public_key)) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        public_key_b64 = unpadder.update(padded_key) + unpadder.finalize()
        public_key = serialization.load_der_public_key(base64.b64decode(public_key_b64))
    except (ValueError, TypeError) as exc:
        raise DataEaseCryptoError("DataEase 返回的 RSA 公钥格式无效") from exc

    if not isinstance(public_key, rsa.RSAPublicKey):
        raise DataEaseCryptoError("DataEase 返回的不是 RSA 公钥")
    if public_key.key_size < 2048:
        raise DataEaseCryptoError("DataEase RSA 公钥长度低于 2048 位")
    return public_key


def fetch_dekey(base_url: str, timeout: float = 15.0) -> str:
    endpoint = f"{base_url.rstrip('/')}/dekey"
    request = Request(endpoint, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise DataEaseCryptoError(f"无法读取 DataEase 公钥接口：{endpoint}") from exc

    if payload.get("code") != 0 or not isinstance(payload.get("data"), str):
        raise DataEaseCryptoError("DataEase 公钥接口返回异常")
    return payload["data"]


def check_dataease_crypto(base_url: str, timeout: float = 15.0) -> CryptoCheckResult:
    public_key = decode_public_key(fetch_dekey(base_url, timeout))
    return CryptoCheckResult(key_size=public_key.key_size)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 DataEase 浏览器 RSA 公钥链路")
    parser.add_argument("--base-url", default="http://127.0.0.1:8100/de2api")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    try:
        result = check_dataease_crypto(args.base_url, args.timeout)
    except DataEaseCryptoError as exc:
        print(f"DataEase 登录加密链路异常：{exc}")
        return 1

    print(f"DataEase 登录加密链路正常：RSA {result.key_size} 位")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
