# auth/security.py — Argon2id helpers
from datetime import date, datetime
import os
import secrets
import string
import random
import logging
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
import re

from utils.env_loader import load_environment
from utils.log_sanitize import sanitize_log_value

load_environment()


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
    """
    Verify a password against a stored hash with timing attack protection.

    Uses constant-time execution (100ms delay) to prevent timing-based
    user enumeration attacks (CWE-208). Logs all attempts with sanitized data.

    Args:
        stored_hash: The Argon2id hash to verify against
        plain: The plaintext password to verify

    Returns:
        True if password matches, False otherwise

    Security:
        - Constant-time delay (100ms) on all verification attempts
        - Sanitized logging of all attempts (no plaintext passwords)
        - Graceful exception handling (InvalidHashError, AttributeError)
    """
    # Use a constant minimum time for all verification attempts to prevent
    # timing attacks that could enumerate valid usernames
    MIN_VERIFY_TIME_MS = 100

    logger = logging.getLogger('security.password_verify')
    result = False
    error_type = None

    start_time = time.perf_counter()

    try:
        if stored_hash is None or plain is None:
            error_type = "null_input"
            return False

        if not isinstance(stored_hash, str) or not isinstance(plain, str):
            error_type = "invalid_type"
            return False

        # Verify password using Argon2id
        verified = _ph.verify(stored_hash, plain + _pepper())
        if verified:
            result = True
        else:
            result = False

    except InvalidHashError:
        # Invalid hash format - possible tampering or corruption
        error_type = "invalid_hash"
        result = False
    except VerifyMismatchError:
        # Password mismatch - expected for invalid passwords
        error_type = "mismatch"
        result = False
    except (AttributeError, TypeError, ValueError) as e:
        # Catch any other unexpected errors gracefully
        error_type = f"unexpected_error:{type(e).__name__}"
        result = False
    except Exception as e:
        # Catch-all for any other exceptions
        error_type = f"unknown_error:{type(e).__name__}"
        result = False
    finally:
        # Ensure constant-time execution to prevent timing attacks
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        remaining_ms = max(0, MIN_VERIFY_TIME_MS - elapsed_ms)
        if remaining_ms > 0:
            time.sleep(remaining_ms / 1000)

        # Log verification attempt with sanitized data (no plaintext passwords)
        # Use a placeholder for the hash to avoid exposing sensitive data
        hash_preview = sanitize_log_value(stored_hash[:16] if stored_hash else "")
        logger.info(
            "password_verify result=%s hash_prefix=%s error=%s time_ms=%.2f",
            result,
            hash_preview,
            error_type or "success",
            elapsed_ms + max(0, remaining_ms)
        )

    return result
    

USERNAME_REGEX = re.compile(r"^[A-Za-z0-9_]+$")
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
        return False, "Username may contain only English letters (A–Z, a–z), digits (0–9), and underscore (_)."
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


def generate_strong_password(length: int = 12) -> str:
    """
    Generate a strong password that satisfies the app policy.
    Format: three words + 4 digits, shuffled, joined by one allowed special char.
    """
    from faker import Faker

    specials = "@#!&"
    separator = secrets.choice(specials)
    faker = Faker()

    def normalize_word(word: str) -> str:
        cleaned = re.sub(r"[^A-Za-z]", "", word or "")
        return cleaned.lower()

    words: list[str] = []
    while len(words) < 3:
        candidate = normalize_word(faker.word())
        if candidate:
            words.append(candidate)

    # Capitalize one word to satisfy uppercase requirement.
    cap_index = secrets.randbelow(len(words))
    words[cap_index] = words[cap_index].capitalize()

    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    parts = words + [digits]
    random.SystemRandom().shuffle(parts)
    return separator.join(parts)



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
    


    
