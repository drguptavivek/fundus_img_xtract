"""Static central policies keyed by explicit application action names."""

from __future__ import annotations

from dataclasses import dataclass

from authz.types import GrantSource


# Two different things are called "resident" in this system, and conflating
# them has produced dead policy conditions more than once.
#
#   ROLE  - a user-level qualification held on the User record: what kind of
#           work this person is licensed to do. `ophthalmologist`,
#           `data_manager`, `fileUploader` are roles.
#   SLOT  - a position in the dual-grading workflow for one task: `resident`,
#           `resident2`, `arbitrator`. A slot is conferred per disease and lab
#           by UserDiseaseUnitRole, or per project by ProjectGraderAllocation.
#
# `resident` happens to exist as both a role name and a slot name; `resident2`
# and `arbitrator` are slot names only and are not roles at all. A policy's
# `roles` set may therefore never contain a slot name - it would never match.
GRADING_SLOT_NAMES = frozenset({"resident", "resident2", "arbitrator"})
SLOT_ONLY_NAMES = frozenset({"resident2", "arbitrator"})

# The user-level qualification required to grade, whichever slot is being filled.
CLINICIAN_ROLE = "ophthalmologist"

PROJECT_SCOPE = "project"
HOSPITAL_SCOPE = "hospital"
LAB_UNIT_SCOPE = "lab_unit"

_SCOPE_RANK = {LAB_UNIT_SCOPE: 1, HOSPITAL_SCOPE: 2, PROJECT_SCOPE: 3}


def _scope_rank(hospital_id, lab_unit_id) -> int:
    """Rank one grant's breadth: a lab grant is narrower than a whole project."""
    if lab_unit_id is not None:
        return _SCOPE_RANK[LAB_UNIT_SCOPE]
    if hospital_id is not None:
        return _SCOPE_RANK[HOSPITAL_SCOPE]
    return _SCOPE_RANK[PROJECT_SCOPE]


@dataclass(frozen=True)
class ActionPolicy:
    """Policy contract for one explicit application action."""

    roles: frozenset[str]
    grant_sources: frozenset[GrantSource]
    capabilities: frozenset[str] = frozenset()
    public: bool = False
    """Deliberately unauthenticated action; no role or relationship is required."""

    project_roles: frozenset[str] = frozenset()
    """Roles accepted on the project branch, when they differ from ``roles``.

    Some actions are deliberately narrower over project data than over
    classical data: dataset curation, for example, is open to several roles
    on lab-scoped rows but only to a project dataset_creator on project rows.
    Empty means the project branch accepts the same roles as ``roles``.
    """

    project_gated: bool = True
    """Whether the project boundary applies to this action at all.

    Almost every action is project-gated: a row owned by a project is
    reachable only through a project relationship, never through hospital or
    lab-unit scope. Set this False only for aggregate operational reporting,
    where a count of what a lab captured is a fact about that lab's own
    throughput rather than a disclosure of project data. Such an action must
    return counts and distributions only - never rows, identifiers or an
    export - because those are disclosures and stay project-gated.
    """

    min_project_scope: str = LAB_UNIT_SCOPE
    """Narrowest project grant that confers authority for this action.

    The grant's scope must match the breadth of the action's effect.

    * ``lab_unit`` (default) - the effect is confined to the rows touched, so
      any grant covering those rows qualifies and the scope acts as a
      *filter*: a lab-scoped grantee simply reaches fewer rows.
    * ``hospital`` - site-level standing is required; a single-lab grant does
      not qualify.
    * ``project`` - the effect spans the project, so the scope acts as a
      *gate*: partial authority confers nothing. Dataset curation is the
      clearest case, since a dataset drawn from part of a project is not a
      legitimate project dataset.

    A grant broader than the minimum always qualifies.
    """

    def roles_for_project(self) -> frozenset[str]:
        """Roles that authorize this action on a project-owned resource."""
        return self.project_roles or self.roles

    def accepts_project_scope(self, *, hospital_id, lab_unit_id) -> bool:
        """Whether a grant at this scope is broad enough for the action."""
        return _scope_rank(hospital_id, lab_unit_id) >= _SCOPE_RANK[self.min_project_scope]


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
    "ophthalmologist", "collaborator",
    "analytics_viewer", "dataset_creator", "data_exporter",
    "discrepancy_reviewer", "regrade_adjudicator",
})
MEDIA_DOCUMENT_ROLES = frozenset({
    "admin", "local_admin", "fileUploader", "optometrist", "data_manager",
    "ophthalmologist", "data_exporter",
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


# The two roles that may occupy a grading slot. `admin` is a grader role in
# its own right; every other role must come by way of `ophthalmologist`.
GRADER_ROLES = frozenset({CLINICIAN_ROLE, "admin"})


def _grading_slot() -> ActionPolicy:
    """Grading policy: a grader role plus a matching grading slot.

    The engine requires the actor's roles to intersect ``roles`` *and* a
    grant from ``grant_sources`` to match the task, so both conditions hold:
    a slot without a grader role does not authorize grading, and a grader
    role without a slot for that disease and lab does not either.

    Project-owned tasks are additionally governed by grader allocation in
    ``grading_allocation.eligibility``.
    """
    return ActionPolicy(
        roles=GRADER_ROLES,
        grant_sources=frozenset({GrantSource.GRADING_SLOT}),
    )


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
    # Grading needs both halves: the clinician role at user level, and an
    # allocated slot for that disease and lab. The slot alone is not enough,
    # and the role alone is not enough. The `resident` role is not used here
    # because ophthalmologists fill resident slots; no user holds it.
    "grading.resident.submit": _grading_slot(),
    "grading.resident2.submit": _grading_slot(),
    "grading.arbitrator.submit": _grading_slot(),
    # Row-level analytics: classical scope for rows outside every project,
    # an explicit project relationship for rows inside one. Without the
    # project branch a project analytics_viewer could not see their own
    # project's rows at all.
    "analytics.encounters.view": ActionPolicy(
        roles=frozenset({"admin", "local_admin", "data_manager", "analytics_viewer", "ophthalmologist"}),
        grant_sources=GENERAL_SCOPE_GRANTS | {
            GrantSource.PROJECT_ROLE,
            GrantSource.LEGACY_PROJECT_CAPABILITY,
        },
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
    "ophthalmologist", "optometrist",
})
# Upload and verification operators.
UPLOAD_OPERATOR_ROLES = frozenset({
    "admin", "local_admin", "data_manager", "fileUploader", "optometrist",
})
GRADING_READ_ROLES = frozenset({"admin", "data_manager", "ophthalmologist"})
GRADING_SUBMIT_ROLES = frozenset({"admin", "ophthalmologist"})
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


def _project(
    roles: frozenset[str],
    grants: frozenset[GrantSource] = PROJECT_GRANTS,
    *,
    min_scope: str = LAB_UNIT_SCOPE,
) -> ActionPolicy:
    """Policy authorized only by an explicit project relationship."""
    return ActionPolicy(roles=roles, grant_sources=grants, min_project_scope=min_scope)


def _self_only() -> ActionPolicy:
    """Policy authorized by the actor owning the record."""
    return ActionPolicy(roles=frozenset(), grant_sources=SELF_GRANT)


def _public() -> ActionPolicy:
    """Deliberately unauthenticated action."""
    return ActionPolicy(roles=frozenset(), grant_sources=frozenset(), public=True)


def _curation(classical_roles: frozenset[str]) -> ActionPolicy:
    """Dataset policy: classical scope for unowned rows, project-wide for owned ones."""
    return ActionPolicy(
        roles=classical_roles,
        grant_sources=GENERAL_SCOPE_GRANTS | {GrantSource.PROJECT_ROLE},
        project_roles=frozenset({"dataset_creator"}),
        min_project_scope=PROJECT_SCOPE,
    )


ANALYTICS_ROLES = frozenset({
    "admin", "local_admin", "data_manager", "analytics_viewer", "ophthalmologist",
})


def _universal(roles: frozenset[str]) -> ActionPolicy:
    """The standard dual-branch policy.

    Rows outside every project follow classical hospital/lab scope; rows
    owned by a project require an explicit project relationship. This is the
    shape most data-bearing actions want.
    """
    return ActionPolicy(
        roles=roles,
        grant_sources=GENERAL_SCOPE_GRANTS | {
            GrantSource.PROJECT_ROLE,
            GrantSource.LEGACY_PROJECT_CAPABILITY,
        },
    )

def _aggregate_kpi() -> ActionPolicy:
    """Aggregate operational reporting: lab scope reaches every row.

    Deliberately not project-gated. Only ever attach this to an endpoint that
    returns counts or distributions; a row listing or export must use the
    matching `.rows` action instead.
    """
    return ActionPolicy(
        roles=ANALYTICS_ROLES,
        grant_sources=GENERAL_SCOPE_GRANTS,
        project_gated=False,
    )


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
    # User records are hospital-shaped and have no lab unit, so they use the
    # own-hospital grant rather than lab assignment. Creating and changing
    # users is an admin power, exercised globally by `admin` and within their
    # own hospital by `local_admin`. `data_manager` may read user allocations
    # and activity for their hospital but never edit them.
    "admin.users.view": ActionPolicy(
        roles=ADMIN_SITE | {"data_manager"},
        grant_sources=frozenset({GrantSource.ADMIN_GLOBAL, GrantSource.OWN_HOSPITAL}),
    ),
    "admin.users.manage": ActionPolicy(
        roles=ADMIN_SITE,
        grant_sources=frozenset({GrantSource.ADMIN_GLOBAL, GrantSource.OWN_HOSPITAL}),
    ),
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
    # Adjudicating a regrade needs either the dedicated role or admin; there
    # is no per-disease or per-lab slot for it, unlike the grading slots.
    "review.regrade.adjudicate": _general(frozenset({"regrade_adjudicator", "admin"})),

    # --- intra-rater ---------------------------------------------------------
    "intra_rater.batch.view": _general(ADMIN_DATA),
    "intra_rater.batch.create": _general(ADMIN_DATA),
    "intra_rater.task.view": _general(GRADING_READ_ROLES),
    "intra_rater.task.submit": _general(GRADING_SUBMIT_ROLES),
    "intra_rater.kpi.view": _general(GRADING_READ_ROLES),


    # --- KPI reporting -------------------------------------------------------
    # Aggregates answer "what passed through my lab", so they are not
    # project-gated: a count of a lab's own throughput is a fact about that
    # lab, not a disclosure of project data. Anything returning rows or an
    # export is a disclosure and follows the universal project rule.
    "analytics.kpi.encounter_files.view": _aggregate_kpi(),
    "analytics.kpi.direct_files.view": _aggregate_kpi(),
    "analytics.upload_stats.view": _aggregate_kpi(),
    "analytics.hospital_dashboard.view": _aggregate_kpi(),
    "analytics.kpi.encounter_files.rows": _universal(ANALYTICS_ROLES),
    "analytics.kpi.direct_files.rows": _universal(ANALYTICS_ROLES),

    # --- datasets ------------------------------------------------------------
    # Curation reads differently on either side of the project boundary.
    # Rows with no project keep the classical rule: any dataset role, scoped
    # by lab-unit assignment or hospital. Rows owned by a project are open
    # only to a project dataset_creator holding a project-wide grant, and
    # only within that project - a grant covering one lab of the project does
    # not confer authority over the project's data as a whole.
    "dataset.curation.view": _curation(DATASET_ROLES),
    "dataset.curation.update": _curation(frozenset({"admin", "dataset_creator"})),
    "dataset.finalize": _curation(frozenset({"admin", "dataset_creator"})),
    "dataset.delete": _curation(frozenset({"admin", "dataset_creator"})),
    "dataset.export.create": _curation(frozenset({"admin", "dataset_creator", "data_exporter"})),
    "dataset.export.download": _curation(frozenset({"admin", "dataset_creator", "data_exporter"})),
    "dataset.share.manage": _curation(frozenset({"admin", "dataset_creator"})),
    # Share recipients authenticate with a hashed share token, not a session.
    "dataset.public_download": _public(),

    # --- glaucoma AI ---------------------------------------------------------
    "glaucoma_ai.workspace.view": _general(UPLOAD_OPERATOR_ROLES | {"ophthalmologist"}),
    "glaucoma_ai.result.view": _general(UPLOAD_OPERATOR_ROLES | {"ophthalmologist"}),
    "glaucoma_ai.upload.create": _general(UPLOAD_OPERATOR_ROLES | {"ophthalmologist"}),

    # --- projects ------------------------------------------------------------
    # Gate actions: the effect spans the project, so partial authority confers
    # nothing and only a project-wide grant qualifies.
    "project.view": _project(PROJECT_ASSIGNABLE_ROLES, min_scope=PROJECT_SCOPE),
    "project.access.manage": _project(frozenset({"project_admin"}), min_scope=PROJECT_SCOPE),
    "project.uploaders.manage": _project(frozenset({"project_admin"}), min_scope=PROJECT_SCOPE),
    "project.wai.run": _project(frozenset({"verifier", "optometrist"}), min_scope=PROJECT_SCOPE),
    "project.wai.results": _project(frozenset({
        "project_pi", "site_pi", "project_admin", "optometrist",
    }), min_scope=PROJECT_SCOPE),

    # Filter actions: the effect is confined to the rows touched, so a
    # narrower grant simply reaches fewer rows.
    "project.encountersets.browse": _project(PROJECT_ASSIGNABLE_ROLES),
    "project.encountersets.browse_pii": _project(PROJECT_ASSIGNABLE_ROLES - {"collaborator"}),
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
