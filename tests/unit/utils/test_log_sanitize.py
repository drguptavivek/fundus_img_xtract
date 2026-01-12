import pytest
from utils.log_sanitize import sanitize_log_value, mask_email, mask_pii

def test_sanitize_log_value_basics():
    assert sanitize_log_value("hello") == "hello"
    assert sanitize_log_value(123) == "123"
    assert sanitize_log_value(None) == ""
    assert sanitize_log_value("line1\nline2") == "line1\\nline2"
    assert sanitize_log_value("line1\rline2") == "line1\\rline2"

def test_sanitize_log_value_truncation():
    long_str = "a" * 150
    sanitized = sanitize_log_value(long_str, max_len=10)
    assert len(sanitized) == 10
    assert sanitized == "aaaaaaaaaa"

def test_mask_email():
    assert mask_email("john.doe@example.com") == "jo***@example.com"
    assert mask_email("a@b.com") == "***@b.com"
    assert mask_email("ab@c.com") == "***@c.com"
    assert mask_email("invalid-email") == "invalid-email"
    assert mask_email(None) == ""
    assert mask_email("") == ""

def test_mask_pii():
    assert mask_pii("1234567890") == "12***90"
    assert mask_pii("1234") == "***"
    assert mask_pii("12") == "***"
    assert mask_pii(None) == ""
