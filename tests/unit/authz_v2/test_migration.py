from __future__ import annotations

from pathlib import Path

from authz_v2.domain.models import (
    AuthorizationResourceScope,
    AuthorizationUploadProfileAssignment,
    PasswordResetCredential,
)

MIGRATION = Path(
    "migrations/versions/e735238d678b_add_unified_authorization_grants_and_.py"
)


def test_foundation_migration_is_id_only_fail_closed_and_reversible():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision: str | Sequence[str] | None = "0d3edcf7bc3b"' in source
    assert "AUTHZ_CONVERSION_" in source
    assert "AUTHZ_CONVERSION_COUNTS" in source
    assert "AUTHZ_DOWNGRADE_UNREPRESENTABLE_GRANT_IDS" in source
    assert "AUTHZ_DOWNGRADE_RESOURCE_SCOPE_BINDING_IDS" in source
    assert "AUTHZ_DOWNGRADE_PASSWORD_RESET_CREDENTIALS_PRESENT" in source
    assert "AUTHZ_DOWNGRADE_UPLOAD_ASSIGNMENT_IDS" in source
    assert "full_name" not in source and "email" not in source
    assert "def upgrade()" in source and "def downgrade()" in source


def test_new_foundation_tables_have_non_widening_constraints():
    scope_constraints = {
        item.name for item in AuthorizationResourceScope.__table__.constraints
    }
    credential_constraints = {
        item.name for item in PasswordResetCredential.__table__.constraints
    }
    upload_constraints = {
        item.name for item in AuthorizationUploadProfileAssignment.__table__.constraints
    }
    assert "uq_authorization_resource_scope" in scope_constraints
    assert "ck_authorization_resource_scopes_scope_target" in scope_constraints
    assert "ck_password_reset_credentials_hash" in credential_constraints
    assert "uq_authorization_upload_profile_assignment" in upload_constraints
