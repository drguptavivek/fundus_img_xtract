"""Helpers for dataset share token and OTP handling."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Tuple

from auth.security import hash_password, verify_password

TOKEN_BYTES = 32
TOKEN_MIN_LEN = 32
TOKEN_MAX_LEN = 128
OTP_LENGTH = 8

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]+$")
OTP_RE = re.compile(r"^[A-Z0-9]+$")


def _share_secret() -> str:
    secret = os.getenv("DATASET_SHARE_HMAC_SECRET")
    if secret and secret.strip():
        return secret.strip()
    fallback = os.getenv("FLASK_SECRET_KEY") or os.getenv("AUTH_PEPPER") or ""
    return fallback.strip()


def generate_share_token() -> str:
    """Generate a URL-safe share token."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_share_token(token: str) -> str:
    """Hash share token for storage."""
    secret = _share_secret().encode("utf-8")
    token_bytes = token.encode("utf-8")
    if secret:
        return hmac.new(secret, token_bytes, hashlib.sha256).hexdigest()
    return hashlib.sha256(token_bytes).hexdigest()


def generate_share_otp() -> str:
    """Generate an 8-character OTP (A-Z, 0-9)."""
    characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(characters) for _ in range(OTP_LENGTH))


def hash_share_otp(otp: str) -> str:
    return hash_password(otp.upper())


def verify_share_otp(otp_hash: str, otp: str) -> bool:
    return verify_password(otp_hash, otp.upper())


def normalize_dataset_name(name: str) -> str:
    return (name or "").strip().lower()


def validate_share_token(token: str) -> bool:
    token = token or ""
    if not (TOKEN_MIN_LEN <= len(token) <= TOKEN_MAX_LEN):
        return False
    return bool(TOKEN_RE.fullmatch(token))


def validate_share_otp(otp: str) -> bool:
    otp = (otp or "").strip().upper()
    if len(otp) != OTP_LENGTH:
        return False
    return bool(OTP_RE.fullmatch(otp))


def format_expiry_delta(seconds: int) -> Tuple[int, int]:
    hours = max(0, seconds) // 3600
    minutes = (max(0, seconds) % 3600) // 60
    return hours, minutes
