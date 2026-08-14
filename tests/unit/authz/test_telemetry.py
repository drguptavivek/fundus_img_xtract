import logging

from authz import GrantSource
from authz.telemetry import (
    record_authorization_cache_error,
    record_authorization_decision,
)


def test_denial_telemetry_does_not_accept_or_emit_resource_details(caplog):
    with caplog.at_level(logging.INFO, logger="authorization"):
        record_authorization_decision(
            action="media.image.view",
            allowed=False,
            actor_id=42,
            grant_source=GrantSource.PROJECT_ROLE,
            cache_hit=True,
        )

    message = caplog.messages[-1]
    assert "outcome=deny" in message
    assert "actor_id=42" in message
    assert "cache_hit" not in message
    assert "grant_source" not in message
    assert "uuid" not in message
    assert "resource" not in message
    assert "reason" not in message


def test_cache_error_telemetry_omits_exception_text_and_cache_keys(caplog):
    with caplog.at_level(logging.WARNING, logger="authorization"):
        record_authorization_cache_error(
            operation="get_decision",
            error=ConnectionError("redis://secret-host/private-key"),
        )

    message = caplog.messages[-1]
    assert "operation=get_decision" in message
    assert "error_type=ConnectionError" in message
    assert "secret-host" not in message
    assert "private-key" not in message
