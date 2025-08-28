# auth/security.py — Argon2id helpers
from datetime import date, datetime
import os
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import re


_ph = PasswordHasher(  # sensible defaults; tune if needed
    time_cost=2,       # iterations
    memory_cost=102400,# ~100 MiB
    parallelism=8,
    hash_len=32,
    salt_len=16
)

def _pepper() -> str:
    # Optional server-side secret added to password before hashing/verifying
    # Set in .env as AUTH_PEPPER or leave empty string.
    return os.getenv("AUTH_PEPPER", "")

def hash_password(plain: str) -> str:
    return _ph.hash(plain + _pepper())

def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        return _ph.verify(stored_hash, plain + _pepper())
    except VerifyMismatchError:
        return False
    

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9]+$")
PASSWORD_ALLOWED_REGEX = re.compile(r"^[A-Za-z0-9@#!&]+$")
COMMON_WEAK_SUBSTRINGS = ("123", "qwerty", "abcd", "xyz", "password", "aiims")

def validate_username(name: str, min_len: int = 3, max_len: int = 150) -> tuple[bool, str]:
    """
    ASCII-only username: letters and digits.
    """
    if not name:
        return False, "Username is required."
    if not (min_len <= len(name) <= max_len):
        return False, f"Username length should be {min_len}–{max_len} characters."
    if not USERNAME_REGEX.fullmatch(name):
        return False, "Username may contain only English letters (A–Z, a–z) and digits (0–9)."
    return True, ""

def check_password_strength(pw: str, min_len: int = 10) -> tuple[bool, str]:
    """
    Length ≥ min_len, at least one uppercase, one lowercase, one of @#!&,
    only allowed characters, and no common weak patterns.
    """
    if not pw:
        return False, "Password is required."
    if len(pw) < min_len:
        return False, f"Password should be at least {min_len} characters."
    if not PASSWORD_ALLOWED_REGEX.fullmatch(pw):
        return False, "Password may contain only English letters, digits, and @ # ! &."
    lower = pw.lower()
    if any(s in lower for s in COMMON_WEAK_SUBSTRINGS):
        return False, "Password contains a common/weak pattern (e.g., 123, qwerty, abcd, xyz, password, aiims)."
    if not re.search(r"[A-Z]", pw):
        return False, "Include at least one uppercase letter."
    if not re.search(r"[a-z]", pw):
        return False, "Include at least one lowercase letter."
    if not re.search(r"[@#!&]", pw):
        return False, "Include at least one special character: @ # ! &."
    return True, ""



EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
PHONE_ALLOWED_RE = re.compile(r"^[0-9+\-\s()]+$")

def validate_email(s: str | None) -> tuple[bool, str]:
    if not s: return True, ""  # optional
    if not EMAIL_RE.fullmatch(s): return False, "Enter a valid email address."
    return True, ""

def validate_phone(s: str | None) -> tuple[bool, str]:
    if not s: return True, ""  # optional
    if not PHONE_ALLOWED_RE.fullmatch(s): return False, "Phone may contain digits, + - ( ) and spaces."
    digits = ''.join(ch for ch in s if ch.isdigit())
    if not (7 <= len(digits) <= 15): return False, "Phone should have 7–15 digits."
    return True, ""

def parse_iso_date(s: str | None) -> tuple[bool, str, date | None]:
    if not s: return True, "", None
    try:
        return True, "", datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return False, "Last date of service must be YYYY-MM-DD.", None
    


    