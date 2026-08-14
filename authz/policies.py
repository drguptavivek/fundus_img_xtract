"""Static central policies keyed by explicit application action names."""

from __future__ import annotations

from dataclasses import dataclass

from authz.types import GrantSource


@dataclass(frozen=True)
class ActionPolicy:
    """Policy contract for one explicit application action."""

    roles: frozenset[str]
    grant_sources: frozenset[GrantSource]
    capabilities: frozenset[str] = frozenset()


GENERAL_SCOPE_GRANTS = frozenset(
    {
        GrantSource.ADMIN_GLOBAL,
        GrantSource.HOSPITAL_SCOPE,
        GrantSource.LAB_UNIT_ASSIGNMENT,
    }
)

VERIFICATION_ROLES = frozenset({"admin", "local_admin", "fileUploader", "optometrist", "data_manager"})

MEDIA_IMAGE_ROLES = frozenset({
    "admin", "local_admin", "fileUploader", "optometrist", "data_manager",
    "ophthalmologist", "resident", "resident2", "arbitrator", "collaborator",
    "analytics_viewer", "dataset_creator", "data_exporter",
    "discrepancy_reviewer", "regrade_adjudicator",
})
MEDIA_DOCUMENT_ROLES = frozenset({
    "admin", "local_admin", "fileUploader", "optometrist", "data_manager",
    "ophthalmologist", "resident", "data_exporter",
})
MEDIA_PROJECT_GRANTS = frozenset({
    GrantSource.PROJECT_ROLE,
    GrantSource.LEGACY_PROJECT_CAPABILITY,
    GrantSource.PROJECT_COLLABORATOR,
    GrantSource.TASK_ELIGIBILITY,
    GrantSource.MEDIA_UPLOADER,
})
MEDIA_SESSION_GRANTS = GENERAL_SCOPE_GRANTS | MEDIA_PROJECT_GRANTS
MEDIA_SIGNED_GRANTS = MEDIA_SESSION_GRANTS | frozenset({GrantSource.SIGNED_MEDIA_TOKEN})
MEDIA_IMAGE_CAPABILITIES = frozenset({
    "browse", "verify", "upload", "discrepancy_review", "data_export",
    "analytics_view", "dataset_creation", "regrade_adjudication",
})
MEDIA_DOCUMENT_CAPABILITIES = frozenset({"browse", "verify", "upload", "data_export"})

POLICIES: dict[str, ActionPolicy] = {
    "media.image.view": ActionPolicy(
        roles=MEDIA_IMAGE_ROLES,
        grant_sources=MEDIA_SIGNED_GRANTS,
        capabilities=MEDIA_IMAGE_CAPABILITIES,
    ),
    "media.thumbnail.view": ActionPolicy(
        roles=MEDIA_IMAGE_ROLES,
        grant_sources=MEDIA_SIGNED_GRANTS,
        capabilities=MEDIA_IMAGE_CAPABILITIES,
    ),
    "media.pdf.view": ActionPolicy(
        roles=MEDIA_DOCUMENT_ROLES,
        grant_sources=MEDIA_SIGNED_GRANTS,
        capabilities=MEDIA_DOCUMENT_CAPABILITIES,
    ),
    "media.metadata.read": ActionPolicy(
        roles=MEDIA_IMAGE_ROLES,
        grant_sources=MEDIA_SESSION_GRANTS,
        capabilities=MEDIA_IMAGE_CAPABILITIES,
    ),
    "media.metadata.process": ActionPolicy(
        roles=MEDIA_IMAGE_ROLES,
        grant_sources=MEDIA_SESSION_GRANTS,
        capabilities=MEDIA_IMAGE_CAPABILITIES,
    ),
    "media.ocr_pii.read": ActionPolicy(
        roles=MEDIA_IMAGE_ROLES,
        grant_sources=MEDIA_SESSION_GRANTS,
        capabilities=MEDIA_IMAGE_CAPABILITIES,
    ),
    "media.ocr_pii.process": ActionPolicy(
        roles=MEDIA_IMAGE_ROLES,
        grant_sources=MEDIA_SESSION_GRANTS,
        capabilities=MEDIA_IMAGE_CAPABILITIES,
    ),
    "upload.direct.create": ActionPolicy(
        roles=frozenset({"fileUploader"}),
        grant_sources=frozenset({GrantSource.UPLOAD_PROFILE}),
    ),
    "grading.resident.submit": ActionPolicy(
        roles=frozenset({"resident", "ophthalmologist"}),
        grant_sources=frozenset({GrantSource.GRADING_SLOT}),
    ),
    "analytics.encounters.view": ActionPolicy(
        roles=frozenset({"admin", "local_admin", "data_manager", "analytics_viewer", "ophthalmologist"}),
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.direct.view": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.direct.update": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.remidio.view": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.remidio.update": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.pregraded.view": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
    "verification.pregraded.update": ActionPolicy(
        roles=VERIFICATION_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
    ),
}


def get_policy(action: str) -> ActionPolicy | None:
    """Return the registered static policy for an action, if one exists."""
    return POLICIES.get(action)
