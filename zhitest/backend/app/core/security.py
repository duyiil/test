from __future__ import annotations

import hashlib
import hmac
import re
import secrets

import bcrypt

_USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{3,64}")


def validate_username(username: str) -> str:
    value = username.strip()
    if not _USERNAME_RE.fullmatch(value):
        raise ValueError("用户名需为 3 到 64 位字母、数字、点、下划线或中划线")
    return value


def validate_password_strength(password: str) -> None:
    size = len(password.encode("utf-8"))
    if size < 8 or size > 72:
        raise ValueError("密码长度需为 8 到 72 字节")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("ascii")


_dummy_hash: str | None = None


def dummy_verify(password: str) -> None:
    """用户不存在时仍做一次哈希比较，缩小响应时间差异。"""

    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = bcrypt.hashpw(b"timing-equalization", bcrypt.gensalt(rounds=12)).decode("ascii")
    verify_password(password, _dummy_hash)


def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """没有密钥时保持原来的 SHA-256。配置了 ZHITEST_SECRET_KEY 时改为 HMAC。"""

    from app.core.config import get_settings

    secret = get_settings().secret_key
    raw = token.encode("utf-8")
    if secret:
        return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return hashlib.sha256(raw).hexdigest()
