"""Round-trip tests for the at-rest encryption helper."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet

from app.services import crypto


@pytest.fixture(autouse=True)
def _set_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ACCOUNT_ENCRYPTION_KEY", key)
    crypto.reset_cache_for_tests()
    yield
    crypto.reset_cache_for_tests()


def test_round_trip_simple():
    plaintext = "hunter2"
    cipher = crypto.encrypt(plaintext)
    assert cipher != plaintext
    assert crypto.decrypt(cipher) == plaintext


def test_round_trip_unicode_and_long():
    plaintext = ("password 🔐 with 中文 characters " * 200).strip()
    cipher = crypto.encrypt(plaintext)
    assert crypto.decrypt(cipher) == plaintext


def test_each_encrypt_yields_different_ciphertext():
    """Fernet uses a random IV — same plaintext encrypts to different bytes."""
    a = crypto.encrypt("same input")
    b = crypto.encrypt("same input")
    assert a != b
    assert crypto.decrypt(a) == crypto.decrypt(b) == "same input"


def test_decrypt_with_wrong_key_raises(monkeypatch):
    cipher = crypto.encrypt("payload")
    other_key = Fernet.generate_key().decode()
    monkeypatch.setenv("ACCOUNT_ENCRYPTION_KEY", other_key)
    crypto.reset_cache_for_tests()
    with pytest.raises(RuntimeError, match="Failed to decrypt"):
        crypto.decrypt(cipher)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ACCOUNT_ENCRYPTION_KEY", raising=False)
    crypto.reset_cache_for_tests()
    with pytest.raises(RuntimeError, match="ACCOUNT_ENCRYPTION_KEY is not set"):
        crypto.encrypt("anything")


def test_invalid_key_format_raises(monkeypatch):
    monkeypatch.setenv("ACCOUNT_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    crypto.reset_cache_for_tests()
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        crypto.encrypt("anything")
