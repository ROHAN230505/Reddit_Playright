"""Symmetric encryption for at-rest secrets (Reddit passwords, TOTP seeds).

Reads ACCOUNT_ENCRYPTION_KEY from the environment. The key MUST be a
URL-safe base64 32-byte Fernet key. Generate one with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

If the env var is not set we raise on first use rather than silently
storing plaintext.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


_FERNET: Fernet | None = None


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is not None:
        return _FERNET
    key = os.getenv("ACCOUNT_ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ACCOUNT_ENCRYPTION_KEY is not set. Generate one with "
            "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"` "
            "and set it in the environment before storing account secrets."
        )
    try:
        _FERNET = Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "ACCOUNT_ENCRYPTION_KEY is not a valid Fernet key (must be URL-safe base64, 32 bytes)."
        ) from exc
    return _FERNET


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        raise ValueError("Cannot encrypt None")
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    if ciphertext is None:
        raise ValueError("Cannot decrypt None")
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError(
            "Failed to decrypt secret — wrong ACCOUNT_ENCRYPTION_KEY or corrupted ciphertext."
        ) from exc


def reset_cache_for_tests() -> None:
    """Test hook — let pytest swap the env key between tests."""
    global _FERNET
    _FERNET = None
