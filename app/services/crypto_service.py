"""토큰 암호화 서비스 — CalendarSync 등 민감 토큰 보호

Fernet (AES-128-CBC + HMAC-SHA256) 기반 대칭키 암호화.
secret_key에서 URL-safe base64 키를 파생하여 사용.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """settings.secret_key에서 Fernet 키 파생"""
    if not settings.secret_key:
        raise RuntimeError("SECRET_KEY가 설정되지 않았습니다. 토큰 암호화에 필요합니다.")
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.secret_key.encode()).digest()
    )
    return Fernet(key)


def encrypt_token(plaintext: str) -> str:
    """평문 토큰 → 암호화 문자열"""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """암호화 문자열 → 평문 토큰"""
    if not ciphertext:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("토큰 복호화 실패: 키가 변경되었거나 데이터가 손상되었습니다")
        raise ValueError("토큰 복호화에 실패했습니다")
