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
    public: bool = False
    """Deliberately unauthenticated action; no role or relationship is required."""


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


# ---------------------------------------------------------------------------
# Role groups observed on the routes these actions govern.
#
# Each group was derived from the decorators currently enforced in the route
# table, so registering a policy preserves today's behaviour rather than
# inventing a new one.
# ---------------------------------------------------------------------------

ADMIN_ONLY = frozenset({"admin"})
ADMIN_SITE = frozenset({"admin", "local_admin"})
ADMIN_DATA = frozenset({"admin", "data_manager"})
ADMIN_DATA_SITE = frozenset({"admin", "data_manager", "local_admin"})

# Clinical read surface: search, task lists, viewers.
CLINICAL_READ_ROLES = frozenset({
    "admin", "local_admin", "data_manager", "fileUploader",
    "ophthalmologist", "optometrist", "resident",
})
# Upload and verification operators.
UPLOAD_OPERATOR_ROLES = frozenset({
    "admin", "local_admin", "data_manager", "fileUploader", "optometrist",
})
GRADING_READ_ROLES = frozenset({"admin", "data_manager", "ophthalmologist"})
GRADING_SUBMIT_ROLES = frozenset({"admin", "ophthalmologist", "resident"})
DATASET_ROLES = frozenset({
    "admin", "local_admin", "data_manager", "dataset_creator",
    "analytics_viewer", "data_exporter",
})
REVIEW_ROLES = frozenset({"admin", "data_manager", "data_exporter", "discrepancy_reviewer"})
JOBS_ROLES = frozenset({
    "admin", "local_admin", "data_manager", "data_exporter", "fileUploader",
    "optometrist", "discrepancy_reviewer", "dataset_creator",
})

SELF_GRANT = frozenset({GrantSource.SELF})

# Project actions are authorized only by an explicit project relationship.
# Hospital or lab-unit membership never grants project access.
PROJECT_GRANTS = frozenset({
    GrantSource.PROJECT_ROLE,
    GrantSource.LEGACY_PROJECT_CAPABILITY,
    GrantSource.PROJECT_COLLABORATOR,
})
PROJECT_UPLOAD_GRANTS = frozenset({
    GrantSource.PROJECT_ROLE,
    GrantSource.LEGACY_PROJECT_CAPABILITY,
    GrantSource.UPLOAD_PROFILE,
})

# Mirrors data_authorization.policy role groups so the two agree.
PROJECT_GOVERNANCE_ROLES = frozenset({"project_pi", "site_pi", "project_admin"})
PROJECT_OPERATIONAL_ROLES = frozenset({
    "collaborator", "verifier", "ophthalmologist", "optometrist",
    "analytics_viewer", "dataset_creator", "data_exporter",
    "discrepancy_reviewer", "regrade_adjudicator",
})
PROJECT_ASSIGNABLE_ROLES = PROJECT_GOVERNANCE_ROLES | PROJECT_OPERATIONAL_ROLES

FIELD_ROLES = frozenset({"field_optometrist", "field_ophthalmologist"})
MOBILE_FIELD_ROLES = FIELD_ROLES | frozenset({"admin", "optometrist", "ophthalmologist"})


def _general(roles: frozenset[str]) -> ActionPolicy:
    """Policy authorized by admin/hospital/lab-unit scope."""
    return ActionPolicy(roles=roles, grant_sources=GENERAL_SCOPE_GRANTS)


def _project(roles: frozenset[str], grants: frozenset[GrantSource] = PROJECT_GRANTS) -> ActionPolicy:
    """Policy authorized only by an explicit project relationship."""
    return ActionPolicy(roles=roles, grant_sources=grants)


def _self_only() -> ActionPolicy:
    """Policy authorized by the actor owning the record."""
    return ActionPolicy(roles=frozenset(), grant_sources=SELF_GRANT)


def _public() -> ActionPolicy:
    """Deliberately unauthenticated action."""
    return ActionPolicy(roles=frozenset(), grant_sources=frozenset(), public=True)


POLICIES.update({
    # --- account: the actor's own record -----------------------------------
    "account.profile.view": _self_only(),
    "account.profile.update": _self_only(),
    "account.password.change": _self_only(),

    # --- auth: pre-authentication surface -----------------------------------
    "auth.login": _public(),
    "auth.logout": _public(),
    "auth.password_reset": _public(),
    "auth.reauth": _self_only(),

    # --- deliberately public content ----------------------------------------
    "public.view": _public(),
    "help.view": _public(),
    "docs.api.view": _public(),

    # --- admin ---------------------------------------------------------------
    "admin.dashboard.view": _general(ADMIN_SITE),
    "admin.users.view": _general(ADMIN_SITE),
    "admin.users.manage": _general(ADMIN_SITE),
    "admin.security.view": _general(ADMIN_ONLY),
    "admin.system.manage": _general(ADMIN_ONLY),
    "admin.s3.manage": _general(ADMIN_ONLY),
    "admin.lookup.manage": _general(ADMIN_ONLY),
    "admin.grading_eligibility.manage": _general(ADMIN_DATA),
    "admin.upload_profiles.manage": _general(ADMIN_ONLY),

    # --- api -----------------------------------------------------------------
    "api.lookups.view": _general(CLINICAL_READ_ROLES),
    "api.lookups.manage": _general(ADMIN_ONLY),
    "api.viewer_settings.manage": _self_only(),
    "api.ocr.manage": _general(UPLOAD_OPERATOR_ROLES),
    "api.mobile.session.manage": _general(ADMIN_SITE),

    # --- dashboard / home / audit -------------------------------------------
    "dashboard.view": _general(CLINICAL_READ_ROLES),
    "dashboard.home.view": _general(CLINICAL_READ_ROLES | ADMIN_SITE),
    "audit.data_quality.view": _general(ADMIN_ONLY),

    # --- search / tasks ------------------------------------------------------
    "search.view": _general(CLINICAL_READ_ROLES),
    "tasks.view": _general(CLINICAL_READ_ROLES),
    "tasks.viewer.view": _general(CLINICAL_READ_ROLES),

    # --- screenings ----------------------------------------------------------
    "screenings.view": _general(UPLOAD_OPERATOR_ROLES),
    "screenings.delete": _general(ADMIN_DATA),
    "screenings.reprocess": _general(ADMIN_DATA),

    # --- uploads -------------------------------------------------------------
    "upload.direct.view": _general(UPLOAD_OPERATOR_ROLES),
    "upload.direct.edit_image": _general(UPLOAD_OPERATOR_ROLES),
    "upload.pregraded.create": ActionPolicy(
        roles=frozenset({"fileUploader", "pregarded_uploader"}),
        grant_sources=frozenset({GrantSource.UPLOAD_PROFILE}),
    ),
    "upload.zip.create": ActionPolicy(
        roles=frozenset({"fileUploader"}),
        grant_sources=frozenset({GrantSource.UPLOAD_PROFILE}),
    ),
    "upload.zip.view": _general(UPLOAD_OPERATOR_ROLES),

    # --- preprocess ----------------------------------------------------------
    "preprocess.dashboard.view": _general(UPLOAD_OPERATOR_ROLES),
    "preprocess.image.update": _general(UPLOAD_OPERATOR_ROLES),

    # --- jobs / reports / notifications --------------------------------------
    "jobs.view": _general(JOBS_ROLES),
    "jobs.result.view": _general(JOBS_ROLES),
    "jobs.regenerate": _general(JOBS_ROLES),
    "reports.view": _general(UPLOAD_OPERATOR_ROLES),
    "notifications.view": _self_only(),
    "notifications.update": _self_only(),

    # --- ad hoc tasks --------------------------------------------------------
    "ad_hoc_task.view": _general(ADMIN_DATA),
    "ad_hoc_task.create": _general(ADMIN_DATA),
    "ad_hoc_task.delete": _general(ADMIN_DATA),

    # --- discrepancy review --------------------------------------------------
    "review.discrepancy.view": _general(REVIEW_ROLES),
    "review.discrepancy.export": _general(frozenset({"admin", "data_manager", "data_exporter"})),
    "review.task.view": _general(REVIEW_ROLES),
    "review.task.submit": _general(frozenset({"admin", "discrepancy_reviewer"})),
    "review.regrade_creator.manage": _general(ADMIN_SITE),

    # --- intra-rater ---------------------------------------------------------
    "intra_rater.batch.view": _general(ADMIN_DATA),
    "intra_rater.batch.create": _general(ADMIN_DATA),
    "intra_rater.task.view": _general(GRADING_READ_ROLES),
    "intra_rater.task.submit": _general(GRADING_SUBMIT_ROLES),
    "intra_rater.kpi.view": _general(GRADING_READ_ROLES),

    # --- datasets ------------------------------------------------------------
    "dataset.curation.view": _general(DATASET_ROLES),
    "dataset.curation.update": _general(frozenset({"admin", "dataset_creator"})),
    "dataset.finalize": _general(frozenset({"admin", "dataset_creator"})),
    "dataset.delete": _general(frozenset({"admin", "dataset_creator"})),
    "dataset.export.create": _general(frozenset({"admin", "dataset_creator", "data_exporter"})),
    "dataset.export.download": _general(frozenset({"admin", "dataset_creator", "data_exporter"})),
    "dataset.share.manage": _general(frozenset({"admin", "dataset_creator"})),
    # Share recipients authenticate with a hashed share token, not a session.
    "dataset.public_download": _public(),

    # --- glaucoma AI ---------------------------------------------------------
    "glaucoma_ai.workspace.view": _general(UPLOAD_OPERATOR_ROLES | {"ophthalmologist"}),
    "glaucoma_ai.result.view": _general(UPLOAD_OPERATOR_ROLES | {"ophthalmologist"}),
    "glaucoma_ai.upload.create": _general(UPLOAD_OPERATOR_ROLES | {"ophthalmologist"}),

    # --- projects: explicit project relationship only ------------------------
    "project.view": _project(PROJECT_ASSIGNABLE_ROLES),
    "project.encountersets.browse": _project(PROJECT_ASSIGNABLE_ROLES),
    "project.encountersets.browse_pii": _project(PROJECT_ASSIGNABLE_ROLES - {"collaborator"}),
    "project.access.manage": _project(frozenset({"project_admin"})),
    "project.uploaders.manage": _project(frozenset({"project_admin"})),
    "project.wai.run": _project(frozenset({"verifier", "optometrist"})),
    "project.wai.results": _project(frozenset({
        "project_pi", "site_pi", "project_admin", "optometrist",
    })),
    "project.upload.direct_image": _project(PROJECT_ASSIGNABLE_ROLES, PROJECT_UPLOAD_GRANTS),
    "project.upload.pregraded": _project(PROJECT_ASSIGNABLE_ROLES, PROJECT_UPLOAD_GRANTS),
    "project.upload.remidio": _project(PROJECT_ASSIGNABLE_ROLES, PROJECT_UPLOAD_GRANTS),
    "project.upload.encounter_set": _project(PROJECT_ASSIGNABLE_ROLES, PROJECT_UPLOAD_GRANTS),
    "project.upload.remidio_api_sync": _project(PROJECT_ASSIGNABLE_ROLES, PROJECT_UPLOAD_GRANTS),

    # --- mobile / field ------------------------------------------------------
    "mobile.context.view": _self_only(),
    "mobile.session.view": _self_only(),
    "mobile.session.revoke": _self_only(),
    "mobile.field.project.view": _project(MOBILE_FIELD_ROLES),
    "mobile.field.encounter.view": _project(MOBILE_FIELD_ROLES),
    "mobile.field.encounter.capture": _project(MOBILE_FIELD_ROLES),
    "mobile.field.inference.run": _project(MOBILE_FIELD_ROLES),
    "mobile.upload.create": _project(MOBILE_FIELD_ROLES, PROJECT_UPLOAD_GRANTS),
})


def get_policy(action: str) -> ActionPolicy | None:
    """Return the registered static policy for an action, if one exists."""
    return POLICIES.get(action)
