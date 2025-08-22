from __future__ import annotations

from typing import Optional

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore

from .settings import settings


_cipher: Optional["Fernet"] = None


def _get_cipher() -> Optional["Fernet"]:
    global _cipher
    if not settings.enable_encryption:
        return None
    if Fernet is None:
        return None
    if _cipher is not None:
        return _cipher
    key = settings.encryption_key
    if not key:
        return None
    try:
        _cipher = Fernet(key.encode("utf-8") if isinstance(key, str) else key)
        return _cipher
    except Exception:
        return None


def encrypt_text(value: Optional[str]) -> Optional[bytes]:
    if value is None:
        return None
    c = _get_cipher()
    if c is None:
        return value.encode("utf-8")  # store as bytes for symmetry when flag toggles later
    return c.encrypt(value.encode("utf-8"))


def decrypt_text(value: Optional[bytes | str]) -> Optional[str]:
    if value is None:
        return None
    # If already plain text
    if isinstance(value, str):
        return value
    c = _get_cipher()
    if c is None:
        try:
            return value.decode("utf-8")
        except Exception:
            return None
    try:
        return c.decrypt(value).decode("utf-8")
    except InvalidToken:
        # Wrong key or not encrypted; fallback best-effort
        try:
            return value.decode("utf-8")
        except Exception:
            return None
    except Exception:
        return None
