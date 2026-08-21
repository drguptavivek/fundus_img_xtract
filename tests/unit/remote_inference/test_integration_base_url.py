"""Base-URL validation for the MadhuNetrAI integration.

A base URL ending in /api produced /api/api/inference/presign/ and every call
404'd at presign, with nothing in the error to suggest the URL was doubled.
"""
import pytest

from remote_inference.encounter_service import (
    _path_segments,
    resolve_enabled,
    resolve_environment,
    save_integration,
)


@pytest.mark.parametrize(
    "path,expected",
    [("/api", ["api"]), ("/api/", ["api"]), ("/", []), ("", []), ("/v2/api", ["v2", "api"])],
)
def test_path_segments(path, expected):
    assert _path_segments(path) == expected


@pytest.mark.parametrize("url", [
    "https://dr-screening.wadhwaniai.org/api",
    "https://dr-screening.wadhwaniai.org/api/",
    "https://dr-screening.wadhwaniai.org/API",
])
def test_a_base_url_carrying_the_api_prefix_is_refused(url):
    """The exact value that caused the live 404, plus its casing variant."""
    result = save_integration({"api_base_url": url, "environment": "production"})

    assert result.success is False
    assert result.status_code == 400
    assert "/api" in result.message


def test_a_bare_host_passes_url_validation():
    """Reaches the integration lookup rather than failing on the URL."""
    result = save_integration(
        {"api_base_url": "https://dr-screening.wadhwaniai.org", "environment": "production"}
    )
    assert "Enter the host only" not in result.message


@pytest.mark.parametrize("url", [
    "http://dr-screening.wadhwaniai.org",
    "https://user:pass@dr-screening.wadhwaniai.org",
    "",
])
def test_existing_url_rules_still_apply(url):
    result = save_integration({"api_base_url": url, "environment": "production"})
    assert result.success is False
    assert "credential-free HTTPS" in result.message


# The enablement/environment decisions are pure, so they are asserted directly.
# save_integration itself opens its own transaction_scope and takes
# SELECT ... FOR UPDATE, which deadlocks against a test transaction holding the
# same row - and calling it for real would write to whatever database is
# configured.


def test_an_absent_is_enabled_keeps_the_current_value():
    """A partial update used to silently disable a working integration."""
    assert resolve_enabled({"api_base_url": "https://x.test"}, current=True) is True
    assert resolve_enabled({"api_base_url": "https://x.test"}, current=False) is False


def test_an_explicit_is_enabled_wins():
    assert resolve_enabled({"is_enabled": True}, current=False) is True
    assert resolve_enabled({"is_enabled": False}, current=True) is False


def test_only_a_real_true_enables():
    """The route normalizes checkbox strings; the service accepts only a bool."""
    for value in ("true", "on", 1, "yes"):
        assert resolve_enabled({"is_enabled": value}, current=True) is False


def test_an_absent_environment_is_empty_not_staging():
    """Defaulting to staging would flip a production integration on a partial update."""
    assert resolve_environment({"api_base_url": "https://x.test"}) == ""


def test_an_explicit_environment_is_normalized():
    assert resolve_environment({"environment": " Production "}) == "production"
    assert resolve_environment({"environment": "STAGING"}) == "staging"
