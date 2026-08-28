"""Authoritative adapters for every exact resource used by the catalogue."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import false, select

from authz_v2.core.resources import DisclosureClass, ResourceContextDTO, ScopeDTO
from authz_v2.core.roles import ScopeType
from authz_v2.domain.models import (
    AuthorizationResourceScope,
    PasswordResetCredential,
)
from authz_v2.resources.references import (
    ActiveConfigurationRef,
    AdminMobileSessionTargetRef,
    AutomationTargetRef,
    ExecutableConfigRef,
    GradingConfigRef,
    GradingRepairBatchRef,
    LookupRecordRef,
    S3SyncQueryRef,
    SystemOperationRef,
    TaskBackfillTargetRef,
    is_positive_int,
    is_stable_resource_id,
)
from authz_v2.resources.registry import ResourceAdapter, ResourceTarget
from authz_v2.resources.relationships import (
    automation_rule_facts,
    compose_facts,
    dataset_state_facts,
    grading_slot_facts,
    ownership_facts,
    participation_facts,
    pii_image_facts,
    signed_credential_facts,
    site_policy_facts,
    upload_profile_facts,
)
from authz_v2.resources.scoping import resolve_scope, scope_model_query
from authz_v2.resources.upload_targets import resolve_classical_upload_target
from encounter_set_types.models import EncounterSetType
from models import (
    AIInferenceRun,
    AIModel,
    AMDReport,
    Area,
    Camera,
    CeleryBeatSchedule,
    CuratedDataset,
    DatasetShare,
    DiabeticRetinopathyReport,
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    EmailSettings,
    EncounterFile,
    EncounterFilePDF,
    EncounterSetImage,
    GlaucomaReport,
    GradingTask,
    Hospital,
    IntraRaterBatch,
    IntraRaterTask,
    Job,
    LabUnit,
    LinkedDiseaseGrading,
    MobileAuthSession,
    PatientEncounters,
    ProjectGraderAllocation,
    S3Config,
    S3SyncStatus,
    SensitiveOperationAudit,
    User,
)
from project_configuration.models import ProjectLabUnit
from upload_profiles.models import UploadProfile


@dataclass(frozen=True)
class TypedResourceRef:
    """Disambiguated reference for polymorphic resource families."""

    kind: str
    resource_id: int


def _state(value) -> dict[str, bool]:
    active = bool(getattr(value, "active", getattr(value, "is_active", True)))
    domain_valid = active and not bool(getattr(value, "is_revoked", False))
    return {"target_active": active, "domain_valid": domain_valid}


def _model_adapter(
    resource_type: str,
    model,
    *,
    owner_attr: str | None = None,
    requester_attr: str | None = None,
    allow_system_scope: bool = False,
) -> ResourceAdapter:
    def resolver(db, resource_id: object) -> ResourceTarget | None:
        automation_rule_id = None
        if isinstance(resource_id, AutomationTargetRef):
            if not is_positive_int(resource_id.automation_rule_id):
                return None
            automation_rule_id = resource_id.automation_rule_id
            resource_id = resource_id.target
        if not is_positive_int(resource_id):
            return None
        value = db.get(model, resource_id)
        if value is None:
            return None
        scope = resolve_scope(
            db,
            project_id=getattr(value, "project_id", None),
            lab_unit_id=getattr(value, "lab_unit_id", None),
            hospital_id=getattr(value, "hospital_id", None),
            allow_system=allow_system_scope,
        )
        if scope is None:
            return None
        return ResourceTarget(
            value,
            ResourceContextDTO(
                resource_type,
                value.id,
                scope,
                owner_id=getattr(value, owner_attr, None) if owner_attr else None,
                requester_id=(
                    getattr(value, requester_attr, None) if requester_attr else None
                ),
                state={
                    **_state(value),
                    **(
                        {"automation_rule_id": automation_rule_id}
                        if automation_rule_id is not None
                        else {}
                    ),
                },
                resolved=True,
            ),
        )

    def scoper(_db, _principal, _action, grants, query):
        return scope_model_query(model, grants, query)

    def facts(_db, _principal, _action, target, current):
        return replace(current, domain_valid=target.context.state["domain_valid"])

    return ResourceAdapter(resource_type, resolver, scoper, facts)


def resolve_bound_resource(
    db, resource_type: str, resource_id: object
) -> ResourceTarget | None:
    if not is_stable_resource_id(resource_id):
        return None
    binding = db.execute(
        select(AuthorizationResourceScope).where(
            AuthorizationResourceScope.resource_type == resource_type,
            AuthorizationResourceScope.resource_id == str(resource_id),
            AuthorizationResourceScope.active.is_(True),
        )
    ).scalar_one_or_none()
    if binding is None:
        return None
    scope = resolve_scope(
        db,
        project_id=binding.project_id,
        lab_unit_id=binding.lab_unit_id,
        hospital_id=binding.hospital_id,
    )
    if scope is None or scope.scope_type.value != binding.scope_type:
        return None
    return ResourceTarget(
        binding,
        ResourceContextDTO(
            resource_type,
            resource_id,
            scope,
            owner_id=binding.owner_user_id,
            requester_id=binding.requester_user_id,
            state={
                "target_active": binding.active,
                "domain_valid": binding.active and binding.domain_valid,
                "automation_rule_id": binding.automation_rule_id,
            },
            resolved=True,
        ),
    )


def _bound_adapter(resource_type: str) -> ResourceAdapter:
    def resolver(db, resource_id):
        return resolve_bound_resource(db, resource_type, resource_id)

    def scoper(_db, _principal, _action, grants, query):
        # Binding-backed resources are listed from this authoritative table.
        return scope_model_query(AuthorizationResourceScope, grants, query).where(
            AuthorizationResourceScope.resource_type == resource_type,
            AuthorizationResourceScope.active.is_(True),
        )

    def facts(_db, _principal, _action, target, current):
        return replace(current, domain_valid=target.context.state["domain_valid"])

    return ResourceAdapter(resource_type, resolver, scoper, facts)


def _resolve_polymorphic(
    db,
    reference: object,
    *,
    resource_type: str,
    kinds: dict[str, object],
) -> ResourceTarget | None:
    if not isinstance(reference, TypedResourceRef):
        return None
    if not isinstance(reference.kind, str) or not is_positive_int(
        reference.resource_id
    ):
        return None
    model = kinds.get(reference.kind)
    if model is None:
        return None
    value = db.get(model, reference.resource_id)
    if value is None:
        return None
    encounter = None
    if isinstance(value, PatientEncounters):
        encounter = value
    elif hasattr(value, "patient_encounter_id"):
        encounter = db.get(PatientEncounters, value.patient_encounter_id)
    elif isinstance(value, AIInferenceRun):
        task = db.get(GradingTask, value.task_id)
        if task is None:
            return None
        scope = resolve_scope(
            db, project_id=task.project_id, lab_unit_id=task.lab_unit_id
        )
        if scope is None:
            return None
        return ResourceTarget(
            value,
            ResourceContextDTO(
                resource_type,
                f"{reference.kind}:{value.id}",
                scope,
                requester_id=value.requested_by_user_id,
                state=_state(value),
            ),
        )
    if encounter is not None:
        scope = resolve_scope(
            db,
            project_id=encounter.project_id,
            lab_unit_id=encounter.lab_unit_id,
            hospital_id=getattr(value, "hospital_id", None),
        )
    else:
        scope = resolve_scope(
            db,
            project_id=getattr(value, "project_id", None),
            lab_unit_id=getattr(value, "lab_unit_id", None),
            hospital_id=getattr(value, "hospital_id", None),
        )
    if scope is None:
        return None
    disclosure = (
        DisclosureClass.IDENTIFIER_IN_PLACE
        if bool(getattr(value, "is_pii", False))
        else DisclosureClass.MASKED
    )
    return ResourceTarget(
        value,
        ResourceContextDTO(
            resource_type,
            f"{reference.kind}:{value.id}",
            scope,
            disclosure_class=disclosure,
            state=_state(value),
        ),
    )


def _polymorphic_adapter(
    resource_type: str, kinds: dict[str, object]
) -> ResourceAdapter:
    def resolver(db, reference):
        return _resolve_polymorphic(
            db, reference, resource_type=resource_type, kinds=kinds
        )

    # Cross-table families have no safe single SQL query. Listing must use the
    # typed member adapter or an authorization_resource_scopes projection.
    def deny_listing(_db, _principal, _action, _grants, query):
        return query.where(false())

    def facts(_db, _principal, _action, _target, current):
        return current

    return ResourceAdapter(resource_type, resolver, deny_listing, facts)


def resolve_dataset_share(db, resource_id: object) -> ResourceTarget | None:
    if not is_positive_int(resource_id):
        return None
    share = db.get(DatasetShare, resource_id)
    if share is None:
        return None
    dataset = db.get(CuratedDataset, share.dataset_id)
    if dataset is None:
        return None
    target = resolve_bound_resource(db, "dataset", share.dataset_id)
    if target is None:
        return None
    return ResourceTarget(
        share,
        replace(
            target.context,
            resource_type="dataset_share",
            resource_id=share.id,
            owner_id=share.created_by_user_id,
            state={
                "target_active": bool(
                    share.is_active and dataset.is_active and dataset.is_finalized
                ),
                "domain_valid": bool(
                    share.is_active and dataset.is_active and dataset.is_finalized
                ),
            },
        ),
    )


def resolve_dataset(db, resource_id: object) -> ResourceTarget | None:
    if not is_positive_int(resource_id):
        return None
    dataset = db.get(CuratedDataset, resource_id)
    target = resolve_bound_resource(db, "dataset", resource_id)
    if dataset is None or target is None:
        return None
    binding = target.value
    return ResourceTarget(
        (dataset, binding),
        replace(
            target.context,
            owner_id=dataset.created_by_user_id,
            state={
                **target.context.state,
                "target_active": bool(dataset.is_active and binding.active),
                "domain_valid": bool(
                    dataset.is_active and binding.active and binding.domain_valid
                ),
            },
        ),
    )


def resolve_mobile_session(db, resource_id: object) -> ResourceTarget | None:
    expected_user_id = None
    if isinstance(resource_id, AdminMobileSessionTargetRef):
        if not is_positive_int(resource_id.user_id):
            return None
        expected_user_id = resource_id.user_id
        resource_id = resource_id.session_id
    if not is_stable_resource_id(resource_id):
        return None
    session = db.get(MobileAuthSession, resource_id)
    if session is None:
        return None
    if expected_user_id is not None and session.user_id != expected_user_id:
        return None
    user = db.get(User, session.user_id)
    if user is None:
        return None
    scope = resolve_scope(
        db,
        hospital_id=user.hospital_id,
        allow_system=user.hospital_id is None,
    )
    if scope is None:
        return None
    active = bool(
        not session.is_revoked
        and session.refresh_token_expires_at > datetime.now(UTC)
        and user.is_active
    )
    return ResourceTarget(
        session,
        ResourceContextDTO(
            "mobile_session",
            session.id,
            scope,
            owner_id=session.user_id,
            state={
                "target_active": active,
                "domain_valid": active,
            },
        ),
    )


def resolve_password_reset(db, resource_id: object) -> ResourceTarget | None:
    if not is_positive_int(resource_id):
        return None
    credential = db.get(PasswordResetCredential, resource_id)
    if credential is None:
        return None
    user = db.get(User, credential.user_id)
    if user is None:
        return None
    valid = (
        credential.consumed_at is None
        and credential.expires_at > datetime.now(UTC)
        and bool(user.is_active)
    )
    return ResourceTarget(
        credential,
        ResourceContextDTO(
            "password_reset_credential",
            credential.id,
            resolve_scope(
                db,
                hospital_id=user.hospital_id,
                allow_system=user.hospital_id is None,
            ),
            owner_id=user.id,
            state={"target_active": valid, "domain_valid": valid},
        ),
    )


ENCOUNTER_ADAPTER = _model_adapter("encounter", PatientEncounters)
ENCOUNTER_SET_ADAPTER = _model_adapter("encounter_set", PatientEncounters)
DIRECT_IMAGE_ADAPTER = _model_adapter(
    "direct_image_upload", DirectImageUpload, owner_attr="uploader_id"
)


def _resolve_direct_upload_batch(db, reference: object) -> ResourceTarget | None:
    """Resolve a bounded batch only when it has one authoritative scope."""
    if not isinstance(reference, (tuple, list)) or not reference:
        return None
    if len(reference) > 50 or any(not is_positive_int(value) for value in reference):
        return None
    ids = tuple(dict.fromkeys(reference))
    rows = db.execute(
        select(DirectImageUpload).where(DirectImageUpload.id.in_(ids))
    ).scalars().all()
    if len(rows) != len(ids):
        return None
    lab_units = {row.lab_unit_id for row in rows}
    hospitals = {row.hospital_id for row in rows}
    if len(lab_units) == 1:
        scope = resolve_scope(db, lab_unit_id=next(iter(lab_units)))
    elif len(hospitals) == 1:
        scope = resolve_scope(db, hospital_id=next(iter(hospitals)))
    else:
        return None
    if scope is None:
        return None
    owners = {row.uploader_id for row in rows}
    return ResourceTarget(
        tuple(rows),
        ResourceContextDTO(
            "direct_upload_batch",
            ",".join(str(value) for value in ids),
            scope,
            owner_id=next(iter(owners)) if len(owners) == 1 else None,
            state={"target_active": True, "domain_valid": True},
            resolved=True,
        ),
    )


DIRECT_UPLOAD_BATCH_ADAPTER = ResourceAdapter(
    "direct_upload_batch",
    _resolve_direct_upload_batch,
    lambda _db, _principal, _action, grants, query: scope_model_query(
        DirectImageUpload, grants, query
    ),
)
GRADING_TASK_ADAPTER = _model_adapter("grading_task", GradingTask)
JOB_ADAPTER = _model_adapter(
    "job",
    Job,
    owner_attr="uploader_user_id",
    requester_attr="uploader_user_id",
    allow_system_scope=True,
)
UPLOAD_JOB_ADAPTER = _model_adapter(
    "upload_job", Job, owner_attr="uploader_user_id", requester_attr="uploader_user_id"
)
UPLOAD_PROFILE_ADAPTER = _model_adapter(
    "upload_profile", UploadProfile, allow_system_scope=True
)
INTRA_RATER_BATCH_ADAPTER = _model_adapter(
    "intra_rater_batch", IntraRaterBatch, owner_attr="created_by_user_id"
)
INTRA_RATER_TASK_ADAPTER = _model_adapter(
    "intra_rater_task", IntraRaterTask, owner_attr="grader_user_id"
)
AD_HOC_TASK_ADAPTER = _bound_adapter("ad_hoc_task")
_DATASET_BASE_ADAPTER = _bound_adapter("dataset")
DATASET_ADAPTER = replace(
    _DATASET_BASE_ADAPTER,
    resolver=resolve_dataset,
    facts_provider=compose_facts(
        _DATASET_BASE_ADAPTER.facts_provider,
        dataset_state_facts,
        site_policy_facts,
    ),
)
DISCREPANCY_ADAPTER = _model_adapter("discrepancy", GradingTask)
_UPLOAD_TARGET_LIST_ADAPTER = _bound_adapter("upload_target")
UPLOAD_TARGET_ADAPTER = replace(
    _UPLOAD_TARGET_LIST_ADAPTER,
    resolver=resolve_classical_upload_target,
    facts_provider=upload_profile_facts,
)
INFERENCE_TARGET_ADAPTER = _bound_adapter("inference_target")
NOTIFICATION_TARGET_ADAPTER = _bound_adapter("notification_target")

IMAGE_ADAPTER = _polymorphic_adapter(
    "image",
    {
        "direct": DirectImageUpload,
        "encounter_file": EncounterFile,
        "encounter_set_image": EncounterSetImage,
    },
)
IMAGE_ADAPTER = replace(
    IMAGE_ADAPTER,
    facts_provider=compose_facts(IMAGE_ADAPTER.facts_provider, pii_image_facts),
)
ENCOUNTER_FILE_ADAPTER = _polymorphic_adapter(
    "encounter_file", {"image": EncounterFile, "pdf": EncounterFilePDF}
)
REPORT_ADAPTER = _polymorphic_adapter(
    "report",
    {
        "dr": DiabeticRetinopathyReport,
        "amd": AMDReport,
        "glaucoma": GlaucomaReport,
    },
)
INFERENCE_RESULT_ADAPTER = _polymorphic_adapter(
    "inference_result", {"wai": AIInferenceRun}
)

DATASET_SHARE_ADAPTER = ResourceAdapter(
    "dataset_share",
    resolve_dataset_share,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    signed_credential_facts,
)
MOBILE_SESSION_ADAPTER = ResourceAdapter(
    "mobile_session",
    resolve_mobile_session,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    compose_facts(ownership_facts, signed_credential_facts),
)
PASSWORD_RESET_ADAPTER = ResourceAdapter(
    "password_reset_credential",
    resolve_password_reset,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    signed_credential_facts,
)

_SYSTEM_OPERATIONS = frozenset(
    {
        "cve_refresh",
        "package_updates_refresh",
        "sequences_refresh",
        "thumbnail_manual_maintenance",
        "thumbnail_cleanup_orphaned",
        "thumbnail_regenerate_missing",
        "thumbnail_validate_integrity",
        "thumbnail_full_maintenance",
        "metadata_backfill",
        "metadata_run_pii_queue",
        "metadata_stop_all",
        "metadata_clear_queued",
        "metadata_clear_running",
        "materialized_views_refresh",
        "email_settings_create",
        "s3_config_create",
        "s3_config_test_candidate",
        "app_settings_update",
        "upload_settings_update",
        "database_dump_export",
        "database_excel_export",
        "database_restore_upload",
        "database_restore_execute",
        "database_restore_cancel",
        "disk_delete_duplicates",
        "disk_delete_processed_zips",
        "lookup_create_hospital",
        "lookup_create_lab_unit",
        "lookup_create_disease",
        "lookup_create_camera",
        "lookup_create_area",
        "disease_grading_create",
        "linked_grading_create",
        "linked_grading_hierarchy_update",
        "remidio_stuck_upload_cleanup",
        "ai_model_create",
        "celery_schedule_create",
        "rate_limit_clear_one",
        "rate_limit_clear_all",
    }
)


def resolve_system_operation(_db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, SystemOperationRef):
        return None
    if reference.operation not in _SYSTEM_OPERATIONS:
        return None
    return ResourceTarget(
        reference.operation,
        ResourceContextDTO(
            "system_operation",
            reference.operation,
            ScopeDTO(ScopeType.SYSTEM),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


SYSTEM_OPERATION_ADAPTER = ResourceAdapter(
    "system_operation",
    resolve_system_operation,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)


def resolve_email_settings(db, reference: object) -> ResourceTarget | None:
    if isinstance(reference, ActiveConfigurationRef):
        if reference.kind != "email_settings":
            return None
        value = db.execute(
            select(EmailSettings).where(EmailSettings.is_active.is_(True))
        ).scalar_one_or_none()
    else:
        if not is_positive_int(reference):
            return None
        value = db.get(EmailSettings, reference)
    if value is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "email_settings_config",
            value.id,
            ScopeDTO(ScopeType.SYSTEM),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


EMAIL_SETTINGS_ADAPTER = ResourceAdapter(
    "email_settings_config",
    resolve_email_settings,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)


def resolve_s3_config(db, reference: object) -> ResourceTarget | None:
    if not is_positive_int(reference):
        return None
    value = db.get(S3Config, reference)
    if value is None:
        return None
    scope = resolve_scope(db, hospital_id=value.hospital_id)
    if scope is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "s3_config",
            value.id,
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


S3_CONFIG_ADAPTER = ResourceAdapter(
    "s3_config",
    resolve_s3_config,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)


def resolve_s3_sync_query(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, S3SyncQueryRef) or not is_positive_int(
        reference.hospital_id
    ):
        return None
    hospital = db.get(Hospital, reference.hospital_id)
    if hospital is None:
        return None
    scope = resolve_scope(db, hospital_id=hospital.id)
    if scope is None:
        return None
    return ResourceTarget(
        hospital,
        ResourceContextDTO(
            "s3_sync_query",
            hospital.id,
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def resolve_s3_sync_record(db, reference: object) -> ResourceTarget | None:
    if not is_positive_int(reference):
        return None
    sync = db.get(S3SyncStatus, reference)
    if sync is None:
        return None
    config = db.get(S3Config, sync.s3_config_id)
    if config is None:
        return None
    scope = resolve_scope(db, hospital_id=config.hospital_id)
    if scope is None:
        return None
    return ResourceTarget(
        sync,
        ResourceContextDTO(
            "s3_sync_record",
            sync.id,
            scope,
            state={"domain_valid": sync.status == "failed"},
            resolved=True,
        ),
    )


def resolve_sensitive_audit_event(db, reference: object) -> ResourceTarget | None:
    if not is_positive_int(reference):
        return None
    event = db.get(SensitiveOperationAudit, reference)
    if event is None:
        return None
    user = db.get(User, event.user_id) if event.user_id else None
    hospital_id = getattr(user, "hospital_id", None) if user else None
    scope = (
        resolve_scope(db, hospital_id=hospital_id)
        if hospital_id is not None
        else ScopeDTO(ScopeType.SYSTEM)
    )
    if scope is None:
        return None
    return ResourceTarget(
        event,
        ResourceContextDTO(
            "sensitive_audit_event",
            event.id,
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def resolve_task_backfill_target(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, TaskBackfillTargetRef):
        return None
    ids = reference.lab_unit_ids
    if (
        not is_positive_int(reference.hospital_id)
        or not ids
        or len(ids) > 500
        or len(set(ids)) != len(ids)
        or any(not is_positive_int(value) for value in ids)
    ):
        return None
    lab_units = tuple(
        db.execute(select(LabUnit).where(LabUnit.id.in_(ids))).scalars()
    )
    if len(lab_units) != len(ids) or any(
        unit.hospital_id != reference.hospital_id for unit in lab_units
    ):
        return None
    scope = resolve_scope(db, hospital_id=reference.hospital_id)
    if scope is None:
        return None
    return ResourceTarget(
        lab_units,
        ResourceContextDTO(
            "task_backfill_target",
            f"{reference.hospital_id}:" + ":".join(str(value) for value in sorted(ids)),
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def _admin_domain_facts(_db, _principal, _action, target, facts):
    return replace(facts, domain_valid=target.context.state["domain_valid"])


S3_SYNC_QUERY_ADAPTER = ResourceAdapter(
    "s3_sync_query", resolve_s3_sync_query,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _admin_domain_facts,
)
S3_SYNC_RECORD_ADAPTER = ResourceAdapter(
    "s3_sync_record", resolve_s3_sync_record,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _admin_domain_facts,
)
SENSITIVE_AUDIT_EVENT_ADAPTER = ResourceAdapter(
    "sensitive_audit_event", resolve_sensitive_audit_event,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _admin_domain_facts,
)
TASK_BACKFILL_TARGET_ADAPTER = ResourceAdapter(
    "task_backfill_target", resolve_task_backfill_target,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _admin_domain_facts,
)

_LOOKUP_MODELS = {
    "hospital": Hospital,
    "lab_unit": LabUnit,
    "disease": Disease,
    "camera": Camera,
    "area": Area,
}


def resolve_lookup_record(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, LookupRecordRef):
        return None
    model = _LOOKUP_MODELS.get(reference.kind)
    if model is None or not is_positive_int(reference.record_id):
        return None
    value = db.get(model, reference.record_id)
    if value is None:
        return None
    if reference.kind == "hospital":
        scope = resolve_scope(db, hospital_id=value.id)
    elif reference.kind == "lab_unit":
        scope = resolve_scope(
            db, hospital_id=value.hospital_id, lab_unit_id=value.id
        )
    else:
        scope = ScopeDTO(ScopeType.SYSTEM)
    if scope is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "lookup_record",
            f"{reference.kind}:{value.id}",
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


LOOKUP_RECORD_ADAPTER = ResourceAdapter(
    "lookup_record",
    resolve_lookup_record,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)

_GRADING_CONFIG_MODELS = {
    "disease_grading": DiseaseGrading,
    "linked_grading": LinkedDiseaseGrading,
    "grading_scheme": Disease,
    "encounter_set_type": EncounterSetType,
}


def resolve_grading_config(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, GradingConfigRef):
        return None
    model = _GRADING_CONFIG_MODELS.get(reference.kind)
    if model is None or not is_positive_int(reference.record_id):
        return None
    value = db.get(model, reference.record_id)
    if value is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "grading_config_record",
            f"{reference.kind}:{value.id}",
            ScopeDTO(ScopeType.SYSTEM),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


GRADING_CONFIG_ADAPTER = ResourceAdapter(
    "grading_config_record",
    resolve_grading_config,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)

_EXECUTABLE_CONFIG_MODELS = {
    "ai_model": AIModel,
    "celery_schedule": CeleryBeatSchedule,
}


def resolve_executable_config(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, ExecutableConfigRef):
        return None
    model = _EXECUTABLE_CONFIG_MODELS.get(reference.kind)
    if model is None or not is_positive_int(reference.record_id):
        return None
    value = db.get(model, reference.record_id)
    if value is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "executable_config_record",
            f"{reference.kind}:{value.id}",
            ScopeDTO(ScopeType.SYSTEM),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


EXECUTABLE_CONFIG_ADAPTER = ResourceAdapter(
    "executable_config_record",
    resolve_executable_config,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)


def resolve_grading_repair_target(db, reference: object) -> ResourceTarget | None:
    if not is_positive_int(reference):
        return None
    task = db.get(GradingTask, reference)
    if task is None:
        return None
    scope = resolve_scope(db, lab_unit_id=task.lab_unit_id)
    if scope is None:
        return None
    return ResourceTarget(
        task,
        ResourceContextDTO(
            "grading_repair_target",
            task.id,
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def resolve_grading_repair_batch(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, GradingRepairBatchRef):
        return None
    ids = reference.task_ids
    if not ids or len(ids) > 100 or len(set(ids)) != len(ids):
        return None
    if any(not is_positive_int(task_id) for task_id in ids):
        return None
    tasks = tuple(
        db.execute(select(GradingTask).where(GradingTask.id.in_(ids))).scalars()
    )
    if len(tasks) != len(ids) or any(task.state != "resident2_done" for task in tasks):
        return None
    return ResourceTarget(
        tasks,
        ResourceContextDTO(
            "grading_repair_batch",
            ":".join(str(task_id) for task_id in sorted(ids)),
            ScopeDTO(ScopeType.SYSTEM),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def _repair_facts(_db, _principal, _action, _target, facts):
    return replace(facts, domain_valid=True)


GRADING_REPAIR_TARGET_ADAPTER = ResourceAdapter(
    "grading_repair_target",
    resolve_grading_repair_target,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _repair_facts,
)
GRADING_REPAIR_BATCH_ADAPTER = ResourceAdapter(
    "grading_repair_batch",
    resolve_grading_repair_batch,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _repair_facts,
)
PROJECT_ALLOCATION_TARGET_ADAPTER = _model_adapter(
    "project_allocation_target", ProjectGraderAllocation
)
PROJECT_SITE_POLICY_ADAPTER = _model_adapter("project_site_policy", ProjectLabUnit)

GRADING_TASK_ADAPTER = replace(
    GRADING_TASK_ADAPTER,
    facts_provider=compose_facts(
        GRADING_TASK_ADAPTER.facts_provider,
        grading_slot_facts,
        participation_facts,
    ),
)
PROJECT_UPLOAD_TARGET_FACTS_ADAPTER = upload_profile_facts

for _name in ("inference_target",):
    _adapter = INFERENCE_TARGET_ADAPTER
    INFERENCE_TARGET_ADAPTER = replace(
        _adapter,
        facts_provider=compose_facts(_adapter.facts_provider, automation_rule_facts),
    )
JOB_ADAPTER = replace(
    JOB_ADAPTER,
    facts_provider=compose_facts(
        JOB_ADAPTER.facts_provider,
        ownership_facts,
        automation_rule_facts,
    ),
)


RESOURCE_ADAPTERS = (
    AD_HOC_TASK_ADAPTER,
    DATASET_ADAPTER,
    DATASET_SHARE_ADAPTER,
    DIRECT_IMAGE_ADAPTER,
    DIRECT_UPLOAD_BATCH_ADAPTER,
    DISCREPANCY_ADAPTER,
    EMAIL_SETTINGS_ADAPTER,
    ENCOUNTER_ADAPTER,
    ENCOUNTER_FILE_ADAPTER,
    ENCOUNTER_SET_ADAPTER,
    EXECUTABLE_CONFIG_ADAPTER,
    GRADING_CONFIG_ADAPTER,
    GRADING_REPAIR_BATCH_ADAPTER,
    GRADING_REPAIR_TARGET_ADAPTER,
    GRADING_TASK_ADAPTER,
    IMAGE_ADAPTER,
    INFERENCE_RESULT_ADAPTER,
    INFERENCE_TARGET_ADAPTER,
    INTRA_RATER_BATCH_ADAPTER,
    INTRA_RATER_TASK_ADAPTER,
    JOB_ADAPTER,
    LOOKUP_RECORD_ADAPTER,
    MOBILE_SESSION_ADAPTER,
    NOTIFICATION_TARGET_ADAPTER,
    PASSWORD_RESET_ADAPTER,
    PROJECT_ALLOCATION_TARGET_ADAPTER,
    PROJECT_SITE_POLICY_ADAPTER,
    REPORT_ADAPTER,
    S3_CONFIG_ADAPTER,
    S3_SYNC_QUERY_ADAPTER,
    S3_SYNC_RECORD_ADAPTER,
    SENSITIVE_AUDIT_EVENT_ADAPTER,
    SYSTEM_OPERATION_ADAPTER,
    TASK_BACKFILL_TARGET_ADAPTER,
    UPLOAD_JOB_ADAPTER,
    UPLOAD_PROFILE_ADAPTER,
    UPLOAD_TARGET_ADAPTER,
)
