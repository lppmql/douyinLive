import base64

import pytest
from cryptography.hazmat.primitives import padding, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from scripts.check_dataease_crypto import AES_IV, KEY_SEPARATOR, DataEaseCryptoError, decode_public_key


def build_dekey() -> tuple[str, rsa.RSAPublicKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    public_key_b64 = base64.b64encode(
        public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    padder = padding.PKCS7(128).padder()
    padded = padder.update(public_key_b64) + padder.finalize()
    aes_key = b"0123456789abcdef"
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(AES_IV)).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return f"{base64.b64encode(encrypted).decode()}{KEY_SEPARATOR}{aes_key.decode()}", public_key


def test_decode_public_key_accepts_dataease_payload():
    dekey, expected_key = build_dekey()

    decoded_key = decode_public_key(dekey)

    assert decoded_key.key_size == 2048
    assert decoded_key.public_numbers() == expected_key.public_numbers()


def test_decode_public_key_rejects_stale_or_malformed_payload():
    with pytest.raises(DataEaseCryptoError, match="RSA 公钥格式无效"):
        decode_public_key("stale-browser-key")
