"""Single executable authorization catalogue with named conjunctive paths."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .actions import ACTION_MANIFEST, Action, action_from_name
from .decisions import DecisionDTO
from .expressions import (
    BooleanFact,
    Expression,
    IdentifierReleaseRequirement,
    active_principal,
    all_of,
    any_of,
    channels_any,
    evaluate,
    fact,
    grants_any,
    public,
    relationship,
    roles_any,
    scoped_roles,
    supporting_grant_ids,
    supporting_relationships,
)
from .principals import EvaluationFactsDTO, GrantSource, SessionChannel
from .resources import DisclosureClass
from .roles import BreakGlassMode, Role


@dataclass(frozen=True)
class ActionDefinition:
    action: Action
    label: str
    description: str
    resource_type: str
    requires_resource: bool
    authorization_paths: tuple[tuple[str, Expression], ...]
    disclosure_class: DisclosureClass
    break_glass: BreakGlassMode
    audit_required: bool


CATALOGUE: dict[Action, ActionDefinition] = {}

AUTH = GrantSource.AUTHORIZATION_GRANT
UPLOAD_PROFILE = GrantSource.UPLOAD_PROFILE
GRADING_SLOT = GrantSource.GRADING_SLOT
PARTICIPATION = GrantSource.PARTICIPATION
SIGNED = GrantSource.SIGNED_CREDENTIAL
AUTOMATION = GrantSource.AUTOMATION_RULE

ADMIN = frozenset({Role.ADMIN})
ADMIN_SITE = frozenset({Role.ADMIN, Role.LOCAL_ADMIN})
USER_ADMIN = frozenset({Role.ADMIN, Role.USER_MANAGER})
ADMIN_DATA = frozenset({Role.ADMIN, Role.DATA_MANAGER})
AUDIT_READ = frozenset({Role.ADMIN, Role.LOCAL_ADMIN, Role.DATA_MANAGER})
CLINICAL_READ = frozenset(
    {
        Role.ADMIN,
        Role.LOCAL_ADMIN,
        Role.DATA_MANAGER,
        Role.FILE_UPLOADER,
        Role.OPHTHALMOLOGIST,
        Role.OPTOMETRIST,
    }
)
CAPTURE_UPLOADERS = frozenset({Role.FILE_UPLOADER, Role.OPTOMETRIST})
PREGRADING_UPLOADERS = frozenset({Role.PREGRADED_UPLOADER})
MOBILE_UPLOADERS = frozenset(
    {
        Role.FIELD_OPHTHALMOLOGIST,
        Role.FIELD_OPTOMETRIST,
        Role.OPHTHALMOLOGIST,
        Role.OPTOMETRIST,
    }
)
MOBILE_FIELD_OPERATORS = MOBILE_UPLOADERS | frozenset({Role.ADMIN})
VERIFIERS = frozenset({Role.ADMIN, Role.VERIFIER})
GRADING_QUALIFICATIONS = frozenset({Role.OPHTHALMOLOGIST, Role.FIELD_OPHTHALMOLOGIST})
INFERENCE_ROW_ROLES = frozenset(
    {
        Role.ADMIN,
        Role.FILE_UPLOADER,
        Role.VERIFIER,
        Role.DATA_MANAGER,
        Role.FIELD_OPTOMETRIST,
        Role.FIELD_OPHTHALMOLOGIST,
    }
)
PDF_READERS = frozenset(
    {
        Role.ADMIN,
        Role.VERIFIER,
        Role.OPTOMETRIST,
        Role.FIELD_OPTOMETRIST,
        Role.FIELD_OPHTHALMOLOGIST,
    }
)
RAW_METADATA_READERS = frozenset(
    {
        Role.ADMIN,
        Role.DATA_MANAGER,
        Role.FILE_UPLOADER,
        Role.PREGRADED_UPLOADER,
        Role.LOCAL_ADMIN,
        Role.OPTOMETRIST,
        Role.VERIFIER,
    }
)
PROJECT_OVERSIGHT = frozenset(
    {Role.PROJECT_PI, Role.SITE_PI, Role.PROJECT_ADMIN, Role.COLLABORATOR}
)
PROJECT_OPERATORS = frozenset(
    {
        Role.VERIFIER,
        Role.OPHTHALMOLOGIST,
        Role.OPTOMETRIST,
        Role.ANALYTICS_VIEWER,
        Role.DATASET_CREATOR,
        Role.DATA_EXPORTER,
        Role.DISCREPANCY_REVIEWER,
        Role.REGRADE_ADJUDICATOR,
        Role.FIELD_OPTOMETRIST,
        Role.FIELD_OPHTHALMOLOGIST,
    }
)
PROJECT_READ = frozenset({Role.ADMIN}) | PROJECT_OVERSIGHT | PROJECT_OPERATORS
GRANT_MANAGERS = frozenset(
    {
        Role.ADMIN,
        Role.USER_MANAGER,
        Role.LOCAL_ADMIN,
        Role.PROJECT_PI,
        Role.SITE_PI,
        Role.PROJECT_ADMIN,
    }
)
DATASET_READ = frozenset(
    {
        Role.ADMIN,
        Role.LOCAL_ADMIN,
        Role.DATA_MANAGER,
        Role.DATASET_CREATOR,
        Role.DATA_EXPORTER,
        Role.ANALYTICS_VIEWER,
    }
)
ANALYTICS = (
    frozenset(
        {
            Role.ADMIN,
            Role.LOCAL_ADMIN,
            Role.DATA_MANAGER,
            Role.ANALYTICS_VIEWER,
            Role.OPHTHALMOLOGIST,
        }
    )
    | PROJECT_OVERSIGHT
)
JOBS = frozenset(
    {
        Role.ADMIN,
        Role.LOCAL_ADMIN,
        Role.DATA_MANAGER,
        Role.DATA_EXPORTER,
        Role.FILE_UPLOADER,
        Role.OPTOMETRIST,
        Role.DISCREPANCY_REVIEWER,
        Role.DATASET_CREATOR,
    }
)


MANDATORY_AUDIT = frozenset(
    {
        "account.password.change",
        "account.profile.update",
        "account.notifications.update",
        "account.mobile_sessions.revoke",
        "auth.password_reset.complete",
        "admin.users.create",
        "admin.users.manage",
        "admin.system.operation",
        "admin.storage.operation",
        "admin.metadata.operation",
        "admin.email_settings.manage",
        "admin.s3_config.manage",
        "admin.database.export",
        "admin.database.restore",
        "admin.upload_quota.manage",
        "admin.lookup_record.manage",
        "admin.grading_config.manage",
        "admin.grading_eligibility.user.manage",
        "admin.executable_config.manage",
        "admin.grading_repair.apply_review",
        "admin.grading_repair.reset_batch",
        "admin.s3_sync.retry",
        "admin.task_backfill.run",
        "admin.remidio_api_config.manage",
        "remidio.attachment_ocr.process",
        "project.remidio.attachment_ocr.process",
        "project.remidio.sync",
        "project.remidio.sync_job.manage",
        "grading.workbench.session.resume",
        "grading.workbench.session.heartbeat",
        "grading.workbench.session.release",
        "grading.workbench.session.draft",
        "grading.workbench.session.submit",
        "grading.workbench.acquire",
        "grading.workbench.revision.acquire",
        "authorization.grants.manage",
        "api.mobile.session.manage",
        "project.access.manage",
        "project.uploaders.manage",
        "dataset.finalize",
        "dataset.delete",
        "dataset.export.create",
        "dataset.export.download_identifiers",
        "dataset.share.manage",
        "review.discrepancy.export",
        "review.discrepancy.export_identifiers",
        "jobs.regenerate",
        "inference.wai.retry",
    }
)


def _title(name: str) -> str:
    return name.replace(".", " ").replace("_", " ").title()


def _store(
    name: str,
    *,
    resource_type: str,
    requires_resource: bool,
    paths: tuple[tuple[str, Expression], ...],
    disclosure: DisclosureClass = DisclosureClass.MASKED,
    break_glass: BreakGlassMode = BreakGlassMode.NEVER,
    description: str | None = None,
) -> None:
    action = Action(name)
    if action in CATALOGUE:
        raise ValueError(f"duplicate action definition: {name}")
    CATALOGUE[action] = ActionDefinition(
        action=action,
        label=_title(name),
        description=description or f"Authorize {name}.",
        resource_type=resource_type,
        requires_resource=requires_resource,
        authorization_paths=paths,
        disclosure_class=disclosure,
        break_glass=break_glass,
        audit_required=name in MANDATORY_AUDIT,
    )


def _screen(
    name: str,
    roles: frozenset[Role],
    *,
    channels: tuple[SessionChannel, ...] = (),
) -> None:
    channel_requirements = (channels_any(*channels),) if channels else ()
    normal = roles - ADMIN
    paths: list[tuple[str, Expression]] = []
    if normal:
        paths.append(
            (
                "authenticated_screen",
                all_of(
                    active_principal(),
                    *channel_requirements,
                    roles_any(*normal),
                    grants_any(AUTH),
                    name="authenticated_screen",
                ),
            )
        )
    if Role.ADMIN in roles:
        paths.append(
            (
                "admin_break_glass",
                all_of(
                    active_principal(),
                    *channel_requirements,
                    roles_any(Role.ADMIN),
                    grants_any(AUTH),
                    name="admin_break_glass",
                ),
            )
        )
    _store(
        name,
        resource_type="screen",
        requires_resource=False,
        paths=tuple(paths),
        break_glass=BreakGlassMode.ADMIN
        if Role.ADMIN in roles
        else BreakGlassMode.NEVER,
    )


def _resource(
    name: str,
    resource_type: str,
    roles: frozenset[Role],
    *,
    disclosure: DisclosureClass = DisclosureClass.MASKED,
    domain_condition: bool = False,
    admin_break_glass: bool = True,
    channels: tuple[SessionChannel, ...] = (),
) -> None:
    common = [
        active_principal(),
        *((channels_any(*channels),) if channels else ()),
        fact(BooleanFact.EXACT_RESOURCE),
        IdentifierReleaseRequirement(),
    ]
    if domain_condition:
        common.append(fact(BooleanFact.DOMAIN_VALID))
    normal = roles - ADMIN
    paths: list[tuple[str, Expression]] = []
    if normal:
        paths.append(
            ("scoped_role", all_of(*common, scoped_roles(*normal), name="scoped_role"))
        )
    if Role.ADMIN in roles:
        paths.append(
            (
                "admin_break_glass",
                all_of(
                    *common,
                    scoped_roles(Role.ADMIN, allow_system=True),
                    name="admin_break_glass",
                ),
            )
        )
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=tuple(paths),
        disclosure=disclosure,
        break_glass=BreakGlassMode.ADMIN
        if Role.ADMIN in roles and admin_break_glass
        else BreakGlassMode.NEVER,
    )


def _owned_resource(
    name: str,
    resource_type: str,
    roles: frozenset[Role],
    *,
    disclosure: DisclosureClass = DisclosureClass.MASKED,
) -> None:
    common = (
        active_principal(),
        fact(BooleanFact.EXACT_RESOURCE),
        IdentifierReleaseRequirement(),
    )
    normal = roles - ADMIN
    paths: list[tuple[str, Expression]] = [
        (
            "owner",
            all_of(
                *common,
                roles_any(*roles),
                relationship(GrantSource.OWNERSHIP, require_scope=False),
                name="owner",
            ),
        )
    ]
    if normal:
        paths.append(
            (
                "scoped_role",
                all_of(*common, scoped_roles(*normal), name="scoped_role"),
            )
        )
    if Role.ADMIN in roles:
        paths.append(
            (
                "admin_break_glass",
                all_of(
                    *common,
                    scoped_roles(Role.ADMIN, allow_system=True),
                    name="admin_break_glass",
                ),
            )
        )
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=tuple(paths),
        disclosure=disclosure,
        break_glass=BreakGlassMode.ADMIN,
    )


def _self(
    name: str,
    resource_type: str,
    *,
    channels: tuple[SessionChannel, ...] = (),
) -> None:
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=(
            (
                "self",
                all_of(
                    active_principal(),
                    *((channels_any(*channels),) if channels else ()),
                    fact(BooleanFact.EXACT_RESOURCE),
                    fact(BooleanFact.SELF_IDENTITY),
                    name="self",
                ),
            ),
        ),
    )


def _mobile_owned(
    name: str, resource_type: str, *, domain_condition: bool = False
) -> None:
    common = [
        active_principal(),
        channels_any(SessionChannel.MOBILE),
        fact(BooleanFact.EXACT_RESOURCE),
        relationship(GrantSource.OWNERSHIP, require_scope=False),
    ]
    if domain_condition:
        common.append(fact(BooleanFact.DOMAIN_VALID))
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=(
            (
                "mobile_owner",
                all_of(
                    *common,
                    scoped_roles(*MOBILE_UPLOADERS),
                    name="mobile_owner",
                ),
            ),
            (
                "admin_owner",
                all_of(
                    *common,
                    scoped_roles(Role.ADMIN, allow_system=True),
                    name="admin_owner",
                ),
            ),
        ),
        break_glass=BreakGlassMode.ADMIN,
    )


def _upload(
    name: str,
    resource_type: str = "upload_target",
    *,
    roles: frozenset[Role] = CAPTURE_UPLOADERS,
    channels: tuple[SessionChannel, ...] = (),
) -> None:
    channel_requirements = (channels_any(*channels),) if channels else ()
    ordinary = all_of(
        active_principal(),
        *channel_requirements,
        scoped_roles(*roles),
        fact(BooleanFact.EXACT_RESOURCE),
        relationship(
            UPLOAD_PROFILE,
            attributes=(("target_active", True),),
        ),
        name="scoped_upload_profile",
    )
    admin = all_of(
        active_principal(),
        *channel_requirements,
        scoped_roles(Role.ADMIN, allow_system=True),
        fact(BooleanFact.EXACT_RESOURCE),
        relationship(
            UPLOAD_PROFILE,
            attributes=(("target_active", True),),
        ),
        name="admin_break_glass",
    )
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=(("scoped_upload_profile", ordinary), ("admin_break_glass", admin)),
        disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
        break_glass=BreakGlassMode.ADMIN,
    )


def _grading(name: str) -> None:
    no_allocation = relationship(
        GRADING_SLOT,
        attributes=(("allocation_enforced", False),),
    )
    allocation = all_of(
        relationship(
            GRADING_SLOT,
            attributes=(("allocation_enforced", True),),
        ),
        relationship(GrantSource.PROJECT_ALLOCATION),
        name="allocation_enforced",
    )
    _store(
        name,
        resource_type="grading_task",
        requires_resource=True,
        paths=(
            (
                "qualified_slot",
                all_of(
                    active_principal(),
                    scoped_roles(*GRADING_QUALIFICATIONS),
                    fact(BooleanFact.EXACT_RESOURCE),
                    any_of(no_allocation, allocation, name="allocation_rule"),
                    name="qualified_slot",
                ),
            ),
        ),
        break_glass=BreakGlassMode.NEVER,
    )


def _participation(
    name: str,
    resource_type: str,
    roles: frozenset[Role],
    *,
    admin_break_glass: bool = False,
) -> None:
    paths = [
        (
            "participant",
            all_of(
                active_principal(),
                roles_any(*roles),
                fact(BooleanFact.EXACT_RESOURCE),
                relationship(PARTICIPATION),
                name="participant",
            ),
        )
    ]
    if admin_break_glass:
        paths.append(
            (
                "admin_break_glass",
                all_of(
                    active_principal(),
                    scoped_roles(Role.ADMIN, allow_system=True),
                    fact(BooleanFact.EXACT_RESOURCE),
                    name="admin_break_glass",
                ),
            )
        )
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=tuple(paths),
        break_glass=BreakGlassMode.ADMIN if admin_break_glass else BreakGlassMode.NEVER,
    )


def _public(name: str) -> None:
    _store(
        name,
        resource_type="public",
        requires_resource=False,
        paths=(("public", all_of(public(), name="public")),),
    )


def _credential(name: str, resource_type: str) -> None:
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=(
            (
                "signed_credential",
                all_of(
                    channels_any(SessionChannel.SIGNED),
                    fact(BooleanFact.EXACT_RESOURCE),
                    fact(BooleanFact.TARGET_ACTIVE),
                    relationship(
                        SIGNED,
                        require_subject=False,
                        require_scope=False,
                    ),
                    name="signed_credential",
                ),
            ),
        ),
    )


def _add_signed_credential_path(name: str) -> None:
    """Add an exact signed-resource alternative to an existing action."""
    action = Action(name)
    definition = CATALOGUE[action]
    signed_path = (
        "signed_credential",
        all_of(
            channels_any(SessionChannel.SIGNED),
            fact(BooleanFact.EXACT_RESOURCE),
            fact(BooleanFact.TARGET_ACTIVE),
            relationship(SIGNED, require_subject=False, require_scope=False),
            name="signed_credential",
        ),
    )
    CATALOGUE[action] = replace(
        definition,
        authorization_paths=definition.authorization_paths + (signed_path,),
    )


def _automation(
    name: str, resource_type: str, interactive_roles: frozenset[Role]
) -> None:
    _resource(name, resource_type, interactive_roles, domain_condition=True)
    definition = CATALOGUE.pop(Action(name))
    worker = (
        "stored_automation_rule",
        all_of(
            channels_any(SessionChannel.AUTOMATION),
            fact(BooleanFact.EXACT_RESOURCE),
            relationship(
                AUTOMATION,
                attributes=(("target_matches", True),),
                require_subject=False,
            ),
            fact(BooleanFact.DOMAIN_VALID),
            name="stored_automation_rule",
        ),
    )
    _store(
        name,
        resource_type=resource_type,
        requires_resource=True,
        paths=definition.authorization_paths + (worker,),
        disclosure=definition.disclosure_class,
        break_glass=definition.break_glass,
    )


# Exact public actions.
for _name in (
    "auth.login",
    "auth.password_reset.request",
    "public.view",
    "public.analytics.view",
    "help.view",
    "docs.api.view",
):
    _public(_name)
_credential("auth.password_reset.complete", "password_reset_credential")
_credential("auth.password_reset.status", "password_reset_credential")
_credential("dataset.public_download", "dataset_share")
_credential("auth.mobile.refresh", "mobile_session")
_credential("auth.mobile.logout", "mobile_session")

# Dynamic self relationships; admin never substitutes for the actor.
for _name, _type in (
    ("account.profile.view", "user"),
    ("account.profile.update", "user"),
    ("account.password.change", "user"),
    ("account.notifications.view", "user"),
    ("account.notifications.update", "user"),
    ("grading.dashboard.view", "user"),
    ("review.discrepancy.history", "user"),
    ("account.mobile_sessions.view", "user"),
    ("account.mobile_sessions.revoke", "mobile_session"),
    ("account.viewer_preferences.manage", "user"),
    ("auth.logout", "user"),
    ("auth.reauth", "user"),
    ("auth.session.keepalive", "user"),
    ("authorization.me.capabilities.view", "user"),
    ("authorization.me.workspaces.view", "user"),
    ("authorization.me.upload_options.view", "user"),
):
    _self(_name, _type)
_self("mobile.context.view", "user", channels=(SessionChannel.MOBILE,))
_self("mobile.upload.options.view", "user", channels=(SessionChannel.MOBILE,))
_self("mobile.session.list", "user", channels=(SessionChannel.MOBILE,))
_self("mobile.session.detail.view", "mobile_session", channels=(SessionChannel.MOBILE,))
_self("mobile.session.revoke", "mobile_session", channels=(SessionChannel.MOBILE,))

# Screen admission only. Panels, rows, and mutations use exact actions below.
for _name, _roles in (
    ("admin.ai_models.view", ADMIN),
    ("admin.dashboard.view", ADMIN_SITE),
    ("admin.security.view", ADMIN),
    ("admin.system.manage", ADMIN),
    ("admin.system.status.view", frozenset({Role.ADMIN, Role.DATA_MANAGER})),
    ("admin.s3.manage", ADMIN),
    ("admin.lookup.manage", ADMIN),
    ("admin.grading_eligibility.manage", ADMIN_DATA),
    ("admin.upload_profiles.manage", ADMIN),
    ("admin.users.workspace.view", ADMIN_SITE),
    ("admin.sensitive_audit.view", AUDIT_READ),
    ("admin.s3_sync.view", ADMIN_SITE),
    ("admin.task_backfill.view", ADMIN_SITE),
    ("authorization.catalogue.view", ADMIN),
    (
        "authorization.grants.view",
        GRANT_MANAGERS,
    ),
    ("audit.data_quality.view", ADMIN),
    ("api.lookups.view", CLINICAL_READ),
    ("api.lookups.manage", ADMIN),
    ("api.ocr.manage", VERIFIERS),
    ("dashboard.view", CLINICAL_READ),
    ("search.view", CLINICAL_READ),
    ("tasks.view", CLINICAL_READ | PROJECT_OVERSIGHT),
    ("preprocess.dashboard.view", VERIFIERS),
    (
        "review.discrepancy.list",
        frozenset({Role.ADMIN, Role.DISCREPANCY_REVIEWER, Role.DATA_EXPORTER}),
    ),
    ("review.regrade_creator.view", frozenset({Role.ADMIN, Role.DATA_MANAGER})),
    ("jobs.view", JOBS),
    ("analytics.encounters.view", ANALYTICS),
    ("analytics.hospital_dashboard.view", ANALYTICS),
    ("analytics.upload_stats.view", ANALYTICS),
    ("analytics.kpi.view", ANALYTICS),
    ("inference.wai.summary", PROJECT_READ),
    ("intra_rater.batch.view", ADMIN_DATA),
    ("project.review.list", PROJECT_READ),
    ("screenings.list", VERIFIERS),
    ("reports.list", VERIFIERS),
    ("intra_rater.kpi.view", ADMIN_DATA | frozenset({Role.OPHTHALMOLOGIST})),
    (
        "intra_rater.tasks.list",
        frozenset({Role.OPHTHALMOLOGIST, Role.ADMIN, Role.DATA_MANAGER}),
    ),
    ("project.encountersets.workspace.view", PROJECT_READ),
    (
        "project.encountersets.workspace.view_pii",
        PROJECT_READ - frozenset({Role.COLLABORATOR, Role.ANALYTICS_VIEWER}),
    ),
    ("project.upload.workspace.view", PROJECT_READ),
    ("upload.workspace.view", CAPTURE_UPLOADERS | ADMIN_DATA | frozenset({Role.LOCAL_ADMIN, Role.OPHTHALMOLOGIST})),
    ("upload.pregraded.workspace.view", PREGRADING_UPLOADERS | ADMIN),
    ("grading.workbench.sessions.list", GRADING_QUALIFICATIONS),
    ("grading.workbench.submissions.list", GRADING_QUALIFICATIONS),
):
    _screen(_name, _roles)
_screen(
    "mobile.field.projects.list",
    MOBILE_FIELD_OPERATORS,
    channels=(SessionChannel.MOBILE,),
)
_screen(
    "glaucoma_ai.uploads.list",
    MOBILE_UPLOADERS,
    channels=(SessionChannel.MOBILE,),
)

# Exact user administration.
_resource(
    "admin.grading_repair.apply_review",
    "grading_repair_target",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.grading_repair.reset_batch",
    "grading_repair_batch",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.sensitive_audit.detail.view",
    "sensitive_audit_event",
    AUDIT_READ,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.s3_sync.query",
    "s3_sync_query",
    ADMIN_SITE,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.s3_sync.retry",
    "s3_sync_record",
    ADMIN_SITE,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.task_backfill.run",
    "task_backfill_target",
    ADMIN_SITE,
    domain_condition=True,
)
_resource(
    "admin.remidio_api_config.view",
    "remidio_config_record",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.remidio_api_config.manage",
    "remidio_config_record",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.remidio_encounter_migration.view",
    "project",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
for _remidio_migration_action in (
    "admin.remidio_encounter_migration.preview",
    "admin.remidio_encounter_migration.apply",
):
    _resource(
        _remidio_migration_action,
        "remidio_encounter_migration_target",
        ADMIN,
        disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    )
_resource(
    "remidio.attachment_ocr.view",
    "remidio_attachment",
    CLINICAL_READ,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "remidio.attachment_ocr.process",
    "remidio_attachment",
    CLINICAL_READ,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "project.remidio.attachment_ocr.view",
    "project",
    CLINICAL_READ,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "project.remidio.attachment_ocr.process",
    "project",
    CLINICAL_READ,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_store(
    "project.remidio.sync",
    resource_type="remidio_project_sync_target",
    requires_resource=True,
    paths=(
        (
            "scoped_upload_profile",
            all_of(
                active_principal(),
                scoped_roles(*CAPTURE_UPLOADERS),
                fact(BooleanFact.EXACT_RESOURCE),
                relationship(
                    UPLOAD_PROFILE,
                    attributes=(("target_active", True),),
                ),
                fact(BooleanFact.DOMAIN_VALID),
                name="scoped_upload_profile",
            ),
        ),
        (
            "admin_break_glass",
            all_of(
                active_principal(),
                scoped_roles(Role.ADMIN, allow_system=True),
                fact(BooleanFact.EXACT_RESOURCE),
                fact(BooleanFact.DOMAIN_VALID),
                name="admin_break_glass",
            ),
        ),
    ),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    break_glass=BreakGlassMode.ADMIN,
)
_owned_resource(
    "project.remidio.sync_job.manage",
    "job",
    CAPTURE_UPLOADERS | ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "project.remote_inference_config.view",
    "project",
    frozenset({Role.ADMIN, Role.PROJECT_ADMIN}),
    disclosure=DisclosureClass.MASKED,
)
_resource(
    "project.remote_inference_config.manage",
    "project",
    frozenset({Role.ADMIN, Role.PROJECT_ADMIN}),
    disclosure=DisclosureClass.MASKED,
)
_resource(
    "project.remote_inference_batch.run",
    "remote_inference_batch",
    frozenset(
        {
            Role.ADMIN,
            Role.VERIFIER,
            Role.OPTOMETRIST,
            Role.FIELD_OPTOMETRIST,
            Role.FIELD_OPHTHALMOLOGIST,
        }
    ),
)
_resource(
    "project.remote_inference_job.resume",
    "job",
    frozenset({Role.ADMIN, Role.PROJECT_ADMIN}),
)
_store(
    "grading.workbench.session.resume",
    resource_type="workbench_session",
    requires_resource=True,
    paths=(
        (
            "owned_active_session",
            all_of(
                active_principal(),
                scoped_roles(*GRADING_QUALIFICATIONS),
                fact(BooleanFact.EXACT_RESOURCE),
                relationship(GrantSource.OWNERSHIP),
                fact(BooleanFact.DOMAIN_VALID),
                name="owned_active_session",
            ),
        ),
    ),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    break_glass=BreakGlassMode.NEVER,
)
for _name in (
    "grading.workbench.session.view",
    "grading.workbench.session.heartbeat",
    "grading.workbench.session.release",
    "grading.workbench.session.draft",
    "grading.workbench.session.submit",
):
    _store(
        _name,
        resource_type="workbench_session",
        requires_resource=True,
        paths=(
            (
                "owned_credentialed_session",
                all_of(
                    active_principal(),
                    scoped_roles(*GRADING_QUALIFICATIONS),
                    fact(BooleanFact.EXACT_RESOURCE),
                    relationship(GrantSource.OWNERSHIP),
                    relationship(SIGNED),
                    fact(BooleanFact.DOMAIN_VALID),
                    name="owned_credentialed_session",
                ),
            ),
        ),
        disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
        break_glass=BreakGlassMode.NEVER,
    )
_store(
    "grading.workbench.acquire",
    resource_type="workbench_acquisition_target",
    requires_resource=True,
    paths=(
        (
            "qualified_exact_acquisition",
            all_of(
                active_principal(),
                scoped_roles(*GRADING_QUALIFICATIONS),
                fact(BooleanFact.EXACT_RESOURCE),
                relationship(GRADING_SLOT),
                fact(BooleanFact.DOMAIN_VALID),
                name="qualified_exact_acquisition",
            ),
        ),
    ),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    break_glass=BreakGlassMode.NEVER,
)
_store(
    "grading.workbench.revision.acquire",
    resource_type="workbench_acquisition_target",
    requires_resource=True,
    paths=(
        (
            "owned_qualified_revision",
            all_of(
                active_principal(),
                scoped_roles(*GRADING_QUALIFICATIONS),
                fact(BooleanFact.EXACT_RESOURCE),
                relationship(GRADING_SLOT),
                relationship(GrantSource.OWNERSHIP),
                fact(BooleanFact.DOMAIN_VALID),
                name="owned_qualified_revision",
            ),
        ),
    ),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    break_glass=BreakGlassMode.NEVER,
)
_resource(
    "admin.executable_config.view",
    "executable_config_record",
    ADMIN,
)
_resource(
    "admin.executable_config.manage",
    "executable_config_record",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.grading_config.view",
    "grading_config_record",
    ADMIN,
)
_resource(
    "admin.grading_config.manage",
    "grading_config_record",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.grading_eligibility.user.manage",
    "user",
    ADMIN_SITE,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.lookup_record.view",
    "lookup_record",
    ADMIN,
)
_resource(
    "admin.lookup_record.manage",
    "lookup_record",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.upload_quota.manage",
    "user",
    frozenset({Role.ADMIN, Role.DATA_MANAGER}),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.database.export",
    "system_operation",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.database.restore",
    "system_operation",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.email_settings.view",
    "email_settings_config",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.email_settings.manage",
    "email_settings_config",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.s3_config.view",
    "s3_config",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.s3_config.manage",
    "s3_config",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.system.operation",
    "system_operation",
    ADMIN,
    domain_condition=True,
)
_resource(
    "admin.storage.operation",
    "system_operation",
    frozenset({Role.ADMIN, Role.DATA_MANAGER}),
    domain_condition=True,
)
_resource(
    "admin.metadata.operation",
    "system_operation",
    ADMIN_SITE,
    domain_condition=True,
)
_resource(
    "admin.users.create",
    "user_creation_target",
    USER_ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.users.view",
    "user",
    USER_ADMIN | frozenset({Role.DATA_MANAGER}),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.users.manage",
    "user",
    USER_ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "admin.upload_profiles.update",
    "upload_profile",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_screen("admin.upload_metadata_fields.view", ADMIN)
_resource(
    "admin.upload_metadata_fields.create",
    "system_operation",
    ADMIN,
)
_resource(
    "admin.upload_metadata_fields.manage",
    "upload_metadata_field_definition",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_screen("admin.iitk.view", ADMIN)
_resource(
    "admin.iitk.project_configuration.view",
    "project",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "admin.iitk.project_configuration.manage",
    "project",
    ADMIN,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource("admin.iitk.configuration.create", "iitk_configuration_target", ADMIN)
for _iitk_action in (
    "admin.iitk.configuration.view",
    "admin.iitk.configuration.manage",
    "admin.iitk.configuration.sync",
):
    _resource(
        _iitk_action,
        "iitk_configuration",
        ADMIN,
        disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    )
_resource(
    "api.mobile.session.manage", "mobile_session", USER_ADMIN, domain_condition=True
)
_resource(
    "authorization.grants.manage",
    "grant_target",
    GRANT_MANAGERS,
    domain_condition=True,
)

# Exact read and workflow resources.
for _name, _type, _roles, _disclosure in (
    (
        "tasks.viewer.view",
        "image",
        CLINICAL_READ | PROJECT_OVERSIGHT,
        DisclosureClass.MASKED,
    ),
    ("screenings.view", "encounter", VERIFIERS, DisclosureClass.IDENTIFIER_IN_PLACE),
    ("screenings.delete", "encounter", ADMIN_DATA, DisclosureClass.IDENTIFIER_IN_PLACE),
    (
        "screenings.reprocess",
        "encounter",
        ADMIN_DATA,
        DisclosureClass.IDENTIFIER_IN_PLACE,
    ),
    (
        "upload.direct.view",
        "direct_image_upload",
        CAPTURE_UPLOADERS | ADMIN,
        DisclosureClass.IDENTIFIER_IN_PLACE,
    ),
    (
        "upload.direct.edit_image",
        "image",
        CAPTURE_UPLOADERS | ADMIN,
        DisclosureClass.IDENTIFIER_IN_PLACE,
    ),
    (
        "upload.zip.view",
        "upload_job",
        CAPTURE_UPLOADERS | ADMIN,
        DisclosureClass.IDENTIFIER_IN_PLACE,
    ),
    (
        "preprocess.image.update",
        "image",
        VERIFIERS,
        DisclosureClass.IDENTIFIER_IN_PLACE,
    ),
    ("reports.view", "report", VERIFIERS, DisclosureClass.MASKED),
    ("ad_hoc_task.view", "ad_hoc_task", ADMIN_DATA, DisclosureClass.MASKED),
    ("ad_hoc_task.create", "ad_hoc_task", ADMIN_DATA, DisclosureClass.MASKED),
    ("ad_hoc_task.delete", "ad_hoc_task", ADMIN_DATA, DisclosureClass.MASKED),
    ("glaucoma_ai.workspace.view", "project", PROJECT_READ, DisclosureClass.MASKED),
    (
        "glaucoma_ai.result.view",
        "inference_result",
        PROJECT_READ,
        DisclosureClass.MASKED,
    ),
):
    _resource(
        _name,
        _type,
        _roles,
        disclosure=_disclosure,
        domain_condition=_name.endswith(("delete", "update", "create")),
    )
_owned_resource("jobs.result.view", "job", JOBS)
_resource(
    "upload.direct.batch.update",
    "direct_upload_batch",
    CAPTURE_UPLOADERS | ADMIN_DATA | frozenset({Role.LOCAL_ADMIN}),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)
_resource(
    "upload.lab_unit.view",
    "upload_lab_unit",
    CAPTURE_UPLOADERS | ADMIN_DATA | frozenset({Role.LOCAL_ADMIN}),
    disclosure=DisclosureClass.MASKED,
)
_resource(
    "upload.direct.update",
    "direct_image_upload",
    CAPTURE_UPLOADERS | ADMIN_DATA | frozenset({Role.LOCAL_ADMIN}),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)

# Upload submissions always require both a grant role and an exact profile.
for _name, _type in (
    ("upload.create", "upload_target"),
    ("project.upload.create", "project_upload_target"),
    ("glaucoma_ai.upload.create", "project_upload_target"),
):
    _upload(_name, _type)
_upload(
    "upload.pregraded.create",
    "upload_target",
    roles=PREGRADING_UPLOADERS,
)
_mobile_owned("mobile.upload.view", "job")
_mobile_owned("mobile.upload.inference.retry", "job", domain_condition=True)
_upload(
    "project.upload.pregraded",
    "project_upload_target",
    roles=PREGRADING_UPLOADERS,
)
_upload(
    "mobile.upload.create",
    "project_upload_target",
    roles=MOBILE_UPLOADERS,
    channels=(SessionChannel.MOBILE,),
)
_upload(
    "glaucoma_ai.mobile_upload.create",
    "project_upload_target",
    roles=MOBILE_UPLOADERS,
    channels=(SessionChannel.MOBILE,),
)
_store(
    "glaucoma_ai.upload.view",
    resource_type="direct_image_upload",
    requires_resource=True,
    paths=(
        (
            "mobile_owner",
            all_of(
                active_principal(),
                channels_any(SessionChannel.MOBILE),
                scoped_roles(*MOBILE_UPLOADERS),
                fact(BooleanFact.EXACT_RESOURCE),
                relationship(GrantSource.OWNERSHIP, require_scope=False),
                name="mobile_owner",
            ),
        ),
    ),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    break_glass=BreakGlassMode.NEVER,
)

# Verification is identifier-in-place and uses exact current state.
for _name, _type in (
    ("verification.direct.view", "direct_image_upload"),
    ("verification.direct.update", "direct_image_upload"),
    ("verification.remidio.view", "encounter"),
    ("verification.remidio.update", "encounter"),
    ("verification.encounter_set.update", "encounter"),
    ("verification.encounter_set.view", "encounter"),
):
    _resource(
        _name,
        _type,
        VERIFIERS,
        disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
        domain_condition="update" in _name,
    )

# Clinical grading is never an admin break-glass action.
for _name in (
    "grading.resident.submit",
    "grading.resident2.submit",
    "grading.arbitrator.submit",
):
    _grading(_name)
_participation(
    "grading.grades.view",
    "grading_task",
    GRADING_QUALIFICATIONS,
    admin_break_glass=True,
)

# Project access and data reads.
for _name, _type, _roles, _disclosure, _domain in (
    ("project.view", "project", PROJECT_READ, DisclosureClass.MASKED, False),
    (
        "project.annotation_policy.view",
        "project",
        ADMIN,
        DisclosureClass.MASKED,
        False,
    ),
    (
        "project.annotation_policy.manage",
        "project",
        ADMIN,
        DisclosureClass.MASKED,
        False,
    ),
    (
        "project.annotation_policy.export",
        "project",
        ADMIN,
        DisclosureClass.MASKED,
        False,
    ),
    (
        "project.grader_allocations.view",
        "project_allocation_plan",
        frozenset(
            {
                Role.ADMIN,
                Role.PROJECT_PI,
                Role.SITE_PI,
                Role.PROJECT_ADMIN,
                Role.DATA_MANAGER,
            }
        ),
        DisclosureClass.MASKED,
        False,
    ),
    (
        "project.grants.view",
        "project",
        GRANT_MANAGERS,
        DisclosureClass.MASKED,
        False,
    ),
    (
        "project.grader_allocations.manage",
        "project_allocation_target",
        frozenset({Role.ADMIN, Role.PROJECT_ADMIN, Role.DATA_MANAGER}),
        DisclosureClass.MASKED,
        True,
    ),
    (
        "project.grader_allocations.enforcement.manage",
        "project",
        frozenset({Role.ADMIN, Role.PROJECT_ADMIN}),
        DisclosureClass.MASKED,
        True,
    ),
    (
        "project.site_policy.manage",
        "project_site_policy",
        frozenset({Role.ADMIN, Role.PROJECT_ADMIN}),
        DisclosureClass.MASKED,
        True,
    ),
    (
        "project.access.manage",
        "project",
        frozenset({Role.ADMIN, Role.PROJECT_ADMIN}),
        DisclosureClass.MASKED,
        True,
    ),
    (
        "project.uploaders.manage",
        "project",
        frozenset(
            {Role.ADMIN, Role.PROJECT_PI, Role.SITE_PI, Role.PROJECT_ADMIN}
        ),
        DisclosureClass.MASKED,
        True,
    ),
    ("project.wai.results", "project", PROJECT_READ, DisclosureClass.MASKED, False),
    (
        "project.encountersets.browse",
        "encounter_set",
        PROJECT_READ,
        DisclosureClass.MASKED,
        False,
    ),
    (
        "project.encountersets.browse_pii",
        "encounter_set",
        PROJECT_READ - frozenset({Role.COLLABORATOR, Role.ANALYTICS_VIEWER}),
        DisclosureClass.IDENTIFIER_IN_PLACE,
        False,
    ),
    (
        "analytics.kpi.encounter_files.rows",
        "encounter_file",
        ANALYTICS,
        DisclosureClass.MASKED,
        False,
    ),
    (
        "analytics.kpi.direct_files.rows",
        "direct_image_upload",
        ANALYTICS,
        DisclosureClass.MASKED,
        False,
    ),
):
    _resource(_name, _type, _roles, disclosure=_disclosure, domain_condition=_domain)

# Datasets and exports. Curation and release are deliberately separate.
for _name, _roles, _domain in (
    ("dataset.curation.view", DATASET_READ, False),
    ("dataset.curation.update", frozenset({Role.ADMIN, Role.DATASET_CREATOR}), True),
    ("dataset.finalize", frozenset({Role.ADMIN, Role.DATASET_CREATOR}), True),
    ("dataset.delete", frozenset({Role.ADMIN, Role.DATASET_CREATOR}), True),
    (
        "dataset.export.create",
        frozenset({Role.ADMIN, Role.DATA_EXPORTER}),
        True,
    ),
    (
        "dataset.export.download",
        frozenset({Role.ADMIN, Role.DATA_EXPORTER}),
        True,
    ),
    ("dataset.share.manage", frozenset({Role.ADMIN, Role.DATA_EXPORTER}), True),
    ("dataset.export.grades", frozenset({Role.ADMIN, Role.DATA_EXPORTER}), True),
):
    _resource(_name, "dataset", _roles, domain_condition=_domain)

_resource(
    "dataset.export.download_identifiers",
    "dataset",
    frozenset({Role.ADMIN, Role.DATA_EXPORTER}),
    disclosure=DisclosureClass.IDENTIFIER_RELEASE,
    domain_condition=True,
)
_resource(
    "dataset.curation.image.update",
    "image",
    frozenset({Role.ADMIN, Role.DATASET_CREATOR}),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
    domain_condition=True,
)

# Review and intra-rater stages.
for _name, _type, _roles, _domain in (
    (
        "review.discrepancy.view",
        "discrepancy",
        frozenset({Role.ADMIN, Role.DISCREPANCY_REVIEWER}),
        False,
    ),
    (
        "review.discrepancy.export",
        "discrepancy",
        frozenset({Role.ADMIN, Role.DATA_MANAGER, Role.DATA_EXPORTER}),
        True,
    ),
    (
        "review.task.view",
        "grading_task",
        frozenset({Role.ADMIN, Role.DISCREPANCY_REVIEWER}),
        False,
    ),
    (
        "review.task.submit",
        "grading_task",
        frozenset({Role.ADMIN, Role.DISCREPANCY_REVIEWER}),
        True,
    ),
    ("review.regrade_creator.manage", "grading_task", ADMIN_DATA, True),
    (
        "review.regrade.adjudicate",
        "grading_task",
        frozenset({Role.ADMIN, Role.REGRADE_ADJUDICATOR}),
        True,
    ),
    ("intra_rater.batch.create", "intra_rater_batch_target", ADMIN_DATA, False),
    (
        "intra_rater.task.view",
        "intra_rater_task",
        frozenset({Role.ADMIN, Role.DATA_MANAGER, Role.OPHTHALMOLOGIST}),
        False,
    ),
    (
        "intra_rater.task.submit",
        "intra_rater_task",
        frozenset({Role.OPHTHALMOLOGIST}),
        True,
    ),
):
    _resource(
        _name,
        _type,
        _roles,
        domain_condition=_domain,
        admin_break_glass=_name != "intra_rater.task.submit",
    )

_resource(
    "review.discrepancy.export_identifiers",
    "discrepancy",
    frozenset({Role.ADMIN, Role.DATA_MANAGER, Role.DATA_EXPORTER}),
    disclosure=DisclosureClass.IDENTIFIER_RELEASE,
    domain_condition=True,
)

# Media has exact-resource scope; identifier release remains additive.
for _name, _type, _roles, _disclosure in (
    (
        "media.image.view",
        "image",
        CLINICAL_READ | PROJECT_READ | DATASET_READ,
        DisclosureClass.MASKED,
    ),
    (
        "media.pdf.view",
        "encounter_file",
        PDF_READERS,
        DisclosureClass.IDENTIFIER_IN_PLACE,
    ),
    (
        "media.metadata.read",
        "image",
        CLINICAL_READ | PROJECT_READ | DATASET_READ,
        DisclosureClass.MASKED,
    ),
    ("media.metadata.process", "image", VERIFIERS, DisclosureClass.MASKED),
    ("media.ocr_pii.read", "image", VERIFIERS, DisclosureClass.IDENTIFIER_IN_PLACE),
    ("media.ocr_pii.process", "image", VERIFIERS, DisclosureClass.IDENTIFIER_IN_PLACE),
):
    _resource(
        _name,
        _type,
        _roles,
        disclosure=_disclosure,
        domain_condition=_name.endswith("process") or _name == "media.image.view",
    )
_resource(
    "media.metadata.raw.read",
    "image",
    RAW_METADATA_READERS,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_add_signed_credential_path("media.image.view")
_add_signed_credential_path("media.pdf.view")

# Interactive job controls and stored automation rules are separate named paths.
_resource("jobs.regenerate", "job", JOBS, domain_condition=True)
_automation(
    "inference.wai.retry",
    "job",
    frozenset({Role.ADMIN, Role.LOCAL_ADMIN, Role.DATA_MANAGER}),
)
_automation(
    "inference.wai.run",
    "inference_target",
    frozenset(
        {
            Role.ADMIN,
            Role.VERIFIER,
            Role.OPTOMETRIST,
            Role.FIELD_OPTOMETRIST,
            Role.FIELD_OPHTHALMOLOGIST,
        }
    ),
)
_automation(
    "inference.wai.retrospective.run",
    "inference_target",
    frozenset({Role.ADMIN, Role.DATA_MANAGER}),
)
_automation(
    "project.wai.run",
    "project",
    frozenset(
        {
            Role.ADMIN,
            Role.VERIFIER,
            Role.OPTOMETRIST,
            Role.FIELD_OPTOMETRIST,
            Role.FIELD_OPHTHALMOLOGIST,
        }
    ),
)
_resource(
    "inference.wai.rows",
    "inference_result",
    INFERENCE_ROW_ROLES,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "project.review.view",
    "project",
    PROJECT_READ,
    disclosure=DisclosureClass.MASKED,
)
_resource(
    "dashboard.hospital.view",
    "lookup_record",
    CLINICAL_READ,
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)
_resource(
    "encounter.viewer.view",
    "encounter",
    CLINICAL_READ | PROJECT_OVERSIGHT,
    disclosure=DisclosureClass.MASKED,
)
_resource(
    "inference.wai.run.retry",
    "inference_result",
    frozenset({Role.ADMIN, Role.LOCAL_ADMIN, Role.DATA_MANAGER}),
    disclosure=DisclosureClass.IDENTIFIER_IN_PLACE,
)

_resource(
    "notifications.send",
    "notification_target",
    ADMIN,
    domain_condition=True,
)

# Mobile field actions are exact project-derived resources.
_resource(
    "mobile.field.project.view",
    "project",
    MOBILE_FIELD_OPERATORS,
    channels=(SessionChannel.MOBILE,),
)
_resource(
    "mobile.field.project.sync",
    "project",
    MOBILE_FIELD_OPERATORS,
    domain_condition=True,
    channels=(SessionChannel.MOBILE,),
)
for _name, _type in (
    ("mobile.field.encounter.view", "encounter"),
    ("mobile.field.encounter.capture", "encounter"),
    ("mobile.field.inference.run", "encounter"),
):
    _resource(
        _name,
        _type,
        frozenset(
            {
                Role.ADMIN,
                Role.FIELD_OPTOMETRIST,
                Role.FIELD_OPHTHALMOLOGIST,
                Role.OPTOMETRIST,
                Role.OPHTHALMOLOGIST,
            }
        ),
        domain_condition=_name != "mobile.field.encounter.view",
        channels=(SessionChannel.MOBILE,),
    )


if {action.value for action in CATALOGUE} != ACTION_MANIFEST:
    missing = sorted(ACTION_MANIFEST - {action.value for action in CATALOGUE})
    extra = sorted({action.value for action in CATALOGUE} - ACTION_MANIFEST)
    raise RuntimeError(
        f"authorization catalogue mismatch: missing={missing}, extra={extra}"
    )


def check_action(
    action: str | Action,
    facts: EvaluationFactsDTO,
    *,
    resource_type: str | None = None,
    resource_resolved: bool = True,
) -> DecisionDTO:
    try:
        canonical = action_from_name(action)
    except ValueError:
        return DecisionDTO(False, str(action), "unknown_action")
    definition = CATALOGUE.get(canonical)
    if definition is None:
        return DecisionDTO(False, canonical.value, "unknown_action")
    if definition.requires_resource and (
        not resource_resolved
        or facts.resource is None
        or not facts.resource.resolved
        or not facts.resource.has_stable_identity()
        or facts.resource.resource_type != definition.resource_type
        or resource_type != definition.resource_type
    ):
        return DecisionDTO(False, canonical.value, "unresolved_resource")
    if definition.requires_resource and facts.resource.scope is None:
        return DecisionDTO(False, canonical.value, "missing_scope")
    for path_name, expression in definition.authorization_paths:
        if evaluate(expression, facts):
            return DecisionDTO(
                True,
                canonical.value,
                "allowed",
                path_name,
                supporting_grant_ids(expression, facts),
                supporting_relationships(expression, facts),
            )
    if not facts.principal.active and definition.authorization_paths[0][0] != "public":
        return DecisionDTO(False, canonical.value, "inactive_principal")
    return DecisionDTO(False, canonical.value, "not_authorized")
