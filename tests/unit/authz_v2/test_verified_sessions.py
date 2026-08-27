from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest

from authz_v2.core.actions import Action
from authz_v2.core.principals import PrincipalDTO, SessionChannel, SessionContextDTO
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import ScopeType
from authz_v2.domain.exceptions import AuthorizationError
from authz_v2.domain.models import PasswordResetCredential
from authz_v2.resources.registry import (
    ResourceAdapter,
    ResourceRegistry,
    ResourceTarget,
)
from authz_v2.resources.relationships import signed_credential_facts
from authz_v2.services.credentials import consume_password_reset_credential
from authz_v2.services.decision import AuthorizationDecisionService


class Repository:
    def principal(self, user_id):
        return PrincipalDTO(user_id, True, True)

    def grants_for(self, _user_id):
        return ()


class Result:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class DB:
    def __init__(self, value):
        self.value = value
        self.flushed = False

    def execute(self, statement):
        assert "FOR UPDATE" in str(statement)
        return Result(self.value)

    def flush(self):
        self.flushed = True


def test_password_reset_token_is_verified_and_consumed_under_lock():
    raw = "one-use-secret"
    credential = PasswordResetCredential(
        id=7,
        user_id=1,
        token_hash=sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    db = DB(credential)
    assert consume_password_reset_credential(db, 7, raw) is credential
    assert credential.consumed_at is not None and db.flushed
    with pytest.raises(AuthorizationError):
        consume_password_reset_credential(db, 7, raw)


def test_mobile_and_automation_claims_require_server_attestation():
    session = SessionContextDTO(
        "request", SessionChannel.MOBILE, datetime.now(UTC), session_id="session-1"
    )
    principal = PrincipalDTO(1, True, True, session)
    denied = AuthorizationDecisionService(Repository(), ResourceRegistry())
    with pytest.raises(AuthorizationError):
        denied.authoritative_principal(principal)
    allowed = AuthorizationDecisionService(
        Repository(),
        ResourceRegistry(),
        session_attestor=lambda _db, current, supplied: (
            current.user_id == 1 and supplied.session_id == "session-1"
        ),
    )
    assert allowed.authoritative_principal(principal).user_id == 1


def test_anonymous_signed_principal_is_allowed_only_with_exact_raw_proof():
    raw = "signed-reset-secret"
    credential = PasswordResetCredential(
        id=7,
        user_id=1,
        token_hash=sha256(raw.encode()).hexdigest(),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    scope = ScopeDTO(ScopeType.SYSTEM)
    registry = ResourceRegistry()
    registry.register(
        ResourceAdapter(
            "password_reset_credential",
            lambda _db, resource_id: ResourceTarget(
                credential,
                ResourceContextDTO(
                    "password_reset_credential",
                    resource_id,
                    scope,
                    state={"target_active": True},
                ),
            ),
            lambda _db, _principal, _action, _grants, query: query,
            signed_credential_facts,
        )
    )
    session = SessionContextDTO(
        "request",
        SessionChannel.SIGNED,
        datetime.min.replace(tzinfo=UTC),
        credential_id="7",
        credential_proof=raw,
    )
    principal = PrincipalDTO(None, False, False, session)
    service = AuthorizationDecisionService(Repository(), registry)
    assert service.check(
        None, principal, Action.AUTH_PASSWORD_RESET_COMPLETE, 7
    ).allowed
    forged = PrincipalDTO(
        None, False, False, replace(session, credential_proof="wrong")
    )
    assert not service.check(
        None, forged, Action.AUTH_PASSWORD_RESET_COMPLETE, 7
    ).allowed
