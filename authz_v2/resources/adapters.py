"""Authoritative adapters for every exact resource used by the catalogue."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import hmac

from sqlalchemy import false, select

from authz_v2.core.principals import GrantSource, RelationshipEvidenceDTO
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
    DirectImageUuidRef,
    GradingConfigRef,
    GradingSchemeGradeRef,
    GradingRepairBatchRef,
    LookupRecordRef,
    JobTokenRef,
    IntraRaterBatchTargetRef,
    IITKConfigurationTargetRef,
    ProjectAllocationTargetRef,
    UploadLabUnitRef,
    RemoteInferenceBatchRef,
    RemidioConfigRef,
    RemidioEncounterMigrationRef,
    RemidioProjectSyncRef,
    S3SyncQueryRef,
    SystemOperationRef,
    TaskBackfillTargetRef,
    WorkbenchSessionRef,
    WorkbenchAcquisitionRef,
    is_positive_int,
    is_stable_resource_id,
)
from authz_v2.resources.registry import ResourceAdapter, ResourceTarget
from authz_v2.resources.relationships import (
    automation_rule_facts,
    compose_facts,
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
from encounter_sets.models import EncounterSetAttachment
from grading.workbench.models import GradingWorkbenchSession
from models import (
    AIInferenceRun,
    AIModel,
    AIModelIntegration,
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
    EncounterSetGradingPackage,
    EncounterFile,
    EncounterFilePDF,
    EncounterSetImage,
    GlaucomaReport,
    GradingTask,
    Grade,
    Hospital,
    IntraRaterTask,
    Job,
    LabUnit,
    LinkedDiseaseGrading,
    MobileAuthSession,
    PatientEncounters,
    Project,
    ProjectGraderAllocation,
    RemidioConnection,
    RemidioRoutingRule,
    RemidioSite,
    S3Config,
    S3SyncStatus,
    SensitiveOperationAudit,
    User,
    UserDiseaseUnitRole,
)
from project_configuration.models import ProjectLabUnit
from iitk_api_integration.models import IITKApiProjectConfig
from remidio_api_integration.models import (
    ProjectUploadProfileRemidioApiBinding,
    RemidioApiRoutingProfile,
    RemidioApiSourceRule,
)
from upload_profiles.models import ProjectUploadProfileAssignment, UploadProfile
from upload_metadata.models import UploadMetadataFieldDefinition


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
                "target_active": bool(share.is_active and dataset.is_active),
                "domain_valid": bool(share.is_active and dataset.is_active),
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
                "domain_valid": bool(binding.active and binding.domain_valid),
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
_DIRECT_IMAGE_ID_RESOLVER = DIRECT_IMAGE_ADAPTER.resolver


def resolve_direct_image(db, reference: object) -> ResourceTarget | None:
    if isinstance(reference, DirectImageUuidRef):
        if not is_stable_resource_id(reference.uuid):
            return None
        image_id = db.execute(
            select(DirectImageUpload.id).where(
                DirectImageUpload.uuid == reference.uuid
            )
        ).scalar_one_or_none()
        if image_id is None:
            return None
        reference = image_id
    return _DIRECT_IMAGE_ID_RESOLVER(db, reference)


DIRECT_IMAGE_ADAPTER = replace(
    DIRECT_IMAGE_ADAPTER,
    resolver=resolve_direct_image,
    facts_provider=compose_facts(
        DIRECT_IMAGE_ADAPTER.facts_provider, ownership_facts
    ),
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


def resolve_remote_inference_batch(db, reference: object) -> ResourceTarget | None:
    """Resolve only a bounded, one-scope set of persisted project encounters."""
    if not isinstance(reference, RemoteInferenceBatchRef):
        return None
    ids = reference.encounter_ids
    if (
        not is_positive_int(reference.project_id)
        or not ids
        or len(ids) > 100
        or len(set(ids)) != len(ids)
        or any(not is_positive_int(value) for value in ids)
    ):
        return None
    rows = tuple(
        db.execute(select(PatientEncounters).where(PatientEncounters.id.in_(ids)))
        .scalars()
        .all()
    )
    if len(rows) != len(ids) or any(
        row.project_id != reference.project_id for row in rows
    ):
        return None
    lab_unit_ids = {row.lab_unit_id for row in rows}
    if len(lab_unit_ids) != 1:
        return None
    scope = resolve_scope(
        db,
        project_id=reference.project_id,
        lab_unit_id=next(iter(lab_unit_ids)),
    )
    if scope is None:
        return None
    identity = hashlib.sha256(
        f"{reference.project_id}:".encode()
        + ",".join(str(value) for value in sorted(ids)).encode()
    ).hexdigest()
    return ResourceTarget(
        rows,
        ResourceContextDTO(
            "remote_inference_batch",
            identity,
            scope,
            state={"target_active": True, "domain_valid": True},
            resolved=True,
        ),
    )


def resolve_upload_lab_unit(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, UploadLabUnitRef) or not is_positive_int(
        reference.lab_unit_id
    ):
        return None
    if reference.project_id is not None and not is_positive_int(
        reference.project_id
    ):
        return None
    scope = resolve_scope(
        db,
        project_id=reference.project_id,
        lab_unit_id=reference.lab_unit_id,
    )
    if scope is None:
        return None
    lab_unit = db.get(LabUnit, reference.lab_unit_id)
    if lab_unit is None:
        return None
    return ResourceTarget(
        lab_unit,
        ResourceContextDTO(
            "upload_lab_unit",
            (
                f"project:{reference.project_id}:lab:{reference.lab_unit_id}"
                if reference.project_id is not None
                else f"lab:{reference.lab_unit_id}"
            ),
            scope,
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
REMOTE_INFERENCE_BATCH_ADAPTER = ResourceAdapter(
    "remote_inference_batch",
    resolve_remote_inference_batch,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
)
UPLOAD_LAB_UNIT_ADAPTER = ResourceAdapter(
    "upload_lab_unit",
    resolve_upload_lab_unit,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
)
GRADING_TASK_ADAPTER = _model_adapter("grading_task", GradingTask)
JOB_ADAPTER = _model_adapter(
    "job",
    Job,
    owner_attr="uploader_user_id",
    requester_attr="uploader_user_id",
    allow_system_scope=True,
)
_JOB_ID_RESOLVER = JOB_ADAPTER.resolver


def resolve_job(db, reference: object) -> ResourceTarget | None:
    if isinstance(reference, JobTokenRef):
        if not is_stable_resource_id(reference.token):
            return None
        job_id = db.execute(
            select(Job.id).where(Job.token == reference.token)
        ).scalar_one_or_none()
        if job_id is None:
            return None
        reference = job_id
    return _JOB_ID_RESOLVER(db, reference)


JOB_ADAPTER = replace(JOB_ADAPTER, resolver=resolve_job)
UPLOAD_JOB_ADAPTER = _model_adapter(
    "upload_job", Job, owner_attr="uploader_user_id", requester_attr="uploader_user_id"
)
UPLOAD_PROFILE_ADAPTER = _model_adapter(
    "upload_profile", UploadProfile, allow_system_scope=True
)
UPLOAD_METADATA_FIELD_DEFINITION_ADAPTER = _model_adapter(
    "upload_metadata_field_definition",
    UploadMetadataFieldDefinition,
    allow_system_scope=True,
)
def resolve_intra_rater_batch_target(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, IntraRaterBatchTargetRef) or not is_positive_int(
        reference.lab_unit_id
    ):
        return None
    scope = resolve_scope(db, lab_unit_id=reference.lab_unit_id)
    if scope is None:
        return None
    return ResourceTarget(
        reference,
        ResourceContextDTO(
            "intra_rater_batch_target",
            f"lab:{reference.lab_unit_id}",
            scope,
            resolved=True,
        ),
    )


INTRA_RATER_BATCH_TARGET_ADAPTER = ResourceAdapter(
    "intra_rater_batch_target",
    resolve_intra_rater_batch_target,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
)
INTRA_RATER_TASK_ADAPTER = _model_adapter(
    "intra_rater_task", IntraRaterTask, owner_attr="grader_user_id"
)


def resolve_iitk_configuration_target(
    db, reference: object
) -> ResourceTarget | None:
    if not isinstance(reference, IITKConfigurationTargetRef):
        return None
    if not is_positive_int(reference.project_id) or not is_positive_int(
        reference.lab_unit_id
    ):
        return None
    scope = resolve_scope(
        db,
        project_id=reference.project_id,
        lab_unit_id=reference.lab_unit_id,
    )
    if scope is None:
        return None
    return ResourceTarget(
        reference,
        ResourceContextDTO(
            "iitk_configuration_target",
            f"{reference.project_id}:{reference.lab_unit_id}",
            scope,
            state={"target_active": True, "domain_valid": True},
            resolved=True,
        ),
    )


IITK_CONFIGURATION_TARGET_ADAPTER = ResourceAdapter(
    "iitk_configuration_target",
    resolve_iitk_configuration_target,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)
IITK_CONFIGURATION_ADAPTER = _model_adapter(
    "iitk_configuration", IITKApiProjectConfig
)
AD_HOC_TASK_ADAPTER = _bound_adapter("ad_hoc_task")
_DATASET_BASE_ADAPTER = _bound_adapter("dataset")
DATASET_ADAPTER = replace(
    _DATASET_BASE_ADAPTER,
    resolver=resolve_dataset,
    facts_provider=compose_facts(
        _DATASET_BASE_ADAPTER.facts_provider,
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
        "notification_broadcast",
        "notification_system_send",
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
        "grading_scheme_create",
        "encounter_set_type_create",
        "linked_grading_create",
        "linked_grading_hierarchy_update",
        "remidio_stuck_upload_cleanup",
        "ai_model_create",
        "celery_schedule_create",
        "rate_limit_clear_one",
        "rate_limit_clear_all",
        "remidio_connection_create",
        "remidio_routing_rule_upsert",
        "remidio_api_source_rule_upsert",
        "remidio_api_binding_upsert",
        "remidio_api_routing_profile_upsert",
        "remidio_api_routing_profile_route_create",
        "remidio_api_routing_rule_upsert",
        "upload_metadata_field_definition_create",
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
            # Retry eligibility is an S3 workflow rule enforced by its service.
            # Authorization owns only the persisted record and hospital scope.
            state={"domain_valid": True},
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

_REMIDIO_CONFIG_MODELS = {
    "connection": RemidioConnection,
    "site": RemidioSite,
    "routing_rule": RemidioRoutingRule,
    "source_rule": RemidioApiSourceRule,
    "binding": ProjectUploadProfileRemidioApiBinding,
    "routing_profile": RemidioApiRoutingProfile,
}


def resolve_remidio_config(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, RemidioConfigRef):
        return None
    model = _REMIDIO_CONFIG_MODELS.get(reference.kind)
    if model is None or not is_positive_int(reference.record_id):
        return None
    value = db.get(model, reference.record_id)
    if value is None:
        return None

    project_id = getattr(value, "project_id", None)
    if isinstance(value, RemidioSite):
        connection = db.get(RemidioConnection, value.remidio_connection_id)
        if connection is None:
            return None
        project_id = connection.project_id
    elif isinstance(value, RemidioApiSourceRule):
        connection = db.get(RemidioConnection, value.remidio_connection_id)
        if connection is None:
            return None
        project_id = connection.project_id
    elif isinstance(value, ProjectUploadProfileRemidioApiBinding):
        project_profile = value.project_profile
        if project_profile is None:
            return None
        project_id = project_profile.project_id

    scope = (
        resolve_scope(db, project_id=project_id)
        if project_id is not None
        else ScopeDTO(ScopeType.SYSTEM)
    )
    if scope is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "remidio_config_record",
            f"{reference.kind}:{value.id}",
            scope,
            # Active/inactive transitions are configuration-domain validation;
            # authorization owns the persisted record identity and scope.
            state={"domain_valid": True},
            resolved=True,
        ),
    )


REMIDIO_CONFIG_ADAPTER = ResourceAdapter(
    "remidio_config_record",
    resolve_remidio_config,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _admin_domain_facts,
)


def resolve_remidio_attachment(db, reference: object) -> ResourceTarget | None:
    if not is_positive_int(reference):
        return None
    attachment = db.get(EncounterSetAttachment, reference)
    if attachment is None:
        return None
    encounter = db.get(PatientEncounters, attachment.patient_encounter_id)
    if encounter is None:
        return None
    scope = resolve_scope(
        db, project_id=encounter.project_id, lab_unit_id=encounter.lab_unit_id
    )
    if scope is None:
        return None
    return ResourceTarget(
        attachment,
        ResourceContextDTO(
            "remidio_attachment",
            attachment.id,
            scope,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


REMIDIO_ATTACHMENT_ADAPTER = ResourceAdapter(
    "remidio_attachment",
    resolve_remidio_attachment,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    _admin_domain_facts,
)


def resolve_remidio_project_sync(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, RemidioProjectSyncRef):
        return None
    ids = reference.lab_unit_ids
    if (
        not is_positive_int(reference.project_id)
        or not ids
        or len(ids) > 500
        or len(set(ids)) != len(ids)
        or any(not is_positive_int(value) for value in ids)
    ):
        return None
    project = db.get(Project, reference.project_id)
    if project is None or not project.active:
        return None
    bindings = tuple(
        db.execute(
            select(ProjectUploadProfileRemidioApiBinding)
            .join(
                RemidioApiRoutingProfile,
                RemidioApiRoutingProfile.id
                == ProjectUploadProfileRemidioApiBinding.routing_profile_id,
            )
            .where(
                RemidioApiRoutingProfile.project_id == project.id,
                RemidioApiRoutingProfile.active.is_(True),
                ProjectUploadProfileRemidioApiBinding.active.is_(True),
            )
        ).scalars()
    )
    active_lab_ids = {binding.lab_unit_id for binding in bindings}
    if not bindings or active_lab_ids != set(ids):
        return None
    return ResourceTarget(
        bindings,
        ResourceContextDTO(
            "remidio_project_sync_target",
            f"{project.id}:" + ":".join(str(value) for value in sorted(ids)),
            ScopeDTO(ScopeType.PROJECT, project.id, project_id=project.id),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def remidio_project_sync_facts(db, principal, _action, target, facts):
    if principal.user_id is None or not target.value:
        return facts
    assignment_ids: list[int] = []
    for binding in target.value:
        assignment = (
            db.execute(
                select(ProjectUploadProfileAssignment).where(
                    ProjectUploadProfileAssignment.user_id == principal.user_id,
                    ProjectUploadProfileAssignment.project_upload_profile_id
                    == binding.project_upload_profile_id,
                    ProjectUploadProfileAssignment.lab_unit_id == binding.lab_unit_id,
                    ProjectUploadProfileAssignment.active.is_(True),
                )
            )
            .scalars()
            .first()
        )
        if assignment is None:
            return replace(facts, domain_valid=True)
        assignment_ids.append(assignment.id)
    evidence = RelationshipEvidenceDTO(
        GrantSource.UPLOAD_PROFILE,
        ":".join(str(value) for value in sorted(assignment_ids)),
        principal.user_id,
        target.context.resource_type,
        target.context.resource_id,
        True,
        target.context.scope,
        (("target_active", True),),
    )
    return replace(
        facts,
        relationships=(*facts.relationships, evidence),
        upload_profile_matches=True,
        target_active=True,
        domain_valid=True,
    )


REMIDIO_PROJECT_SYNC_ADAPTER = ResourceAdapter(
    "remidio_project_sync_target",
    resolve_remidio_project_sync,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    remidio_project_sync_facts,
)


def resolve_remidio_encounter_migration(
    db, reference: object
) -> ResourceTarget | None:
    if not isinstance(reference, RemidioEncounterMigrationRef):
        return None
    ids = reference.encounter_ids
    if (
        not is_positive_int(reference.source_project_id)
        or not is_positive_int(reference.target_project_id)
        or reference.source_project_id == reference.target_project_id
        or not ids
        or len(ids) > 500
        or len(set(ids)) != len(ids)
        or any(not is_positive_int(value) for value in ids)
    ):
        return None
    source = db.get(Project, reference.source_project_id)
    target = db.get(Project, reference.target_project_id)
    if source is None or target is None or not source.active or not target.active:
        return None
    encounters = tuple(
        db.execute(
            select(PatientEncounters).where(PatientEncounters.id.in_(ids))
        ).scalars()
    )
    if len(encounters) != len(ids) or any(
        encounter.project_id != source.id for encounter in encounters
    ):
        return None
    identity = hashlib.sha256(
        f"{source.id}:{target.id}:".encode()
        + ",".join(str(value) for value in sorted(ids)).encode()
    ).hexdigest()
    return ResourceTarget(
        (source, target, encounters),
        ResourceContextDTO(
            "remidio_encounter_migration_target",
            identity,
            ScopeDTO(ScopeType.SYSTEM),
            state={"domain_valid": True},
            resolved=True,
        ),
    )


REMIDIO_ENCOUNTER_MIGRATION_ADAPTER = ResourceAdapter(
    "remidio_encounter_migration_target",
    resolve_remidio_encounter_migration,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
)


def resolve_workbench_session(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, WorkbenchSessionRef) or not is_stable_resource_id(
        reference.session_uuid
    ):
        return None
    session = db.execute(
        select(GradingWorkbenchSession).where(
            GradingWorkbenchSession.uuid == reference.session_uuid
        )
    ).scalar_one_or_none()
    if session is None or not session.targets:
        return None
    tasks = tuple(db.get(GradingTask, target.task_id) for target in session.targets)
    if any(task is None for task in tasks):
        return None
    scopes = tuple(
        resolve_scope(db, project_id=task.project_id, lab_unit_id=task.lab_unit_id)
        for task in tasks
    )
    if any(scope is None for scope in scopes) or len(set(scopes)) != 1:
        return None
    now = datetime.now(UTC)
    active = bool(
        session.status == "active"
        and session.idle_expires_at > now
        and session.absolute_expires_at > now
    )
    credential_valid = bool(
        reference.raw_token
        and is_positive_int(reference.token_generation)
        and reference.token_generation == session.token_generation
        and hmac.compare_digest(
            session.token_hash,
            hashlib.sha256(reference.raw_token.encode("utf-8")).hexdigest(),
        )
    )
    return ResourceTarget(
        session,
        ResourceContextDTO(
            "workbench_session",
            session.uuid,
            scopes[0],
            owner_id=session.user_id,
            state={
                "domain_valid": active,
                "credential_valid": credential_valid,
            },
            resolved=True,
        ),
    )


def workbench_session_facts(_db, principal, _action, target, facts):
    facts = ownership_facts(_db, principal, _action, target, facts)
    credential_valid = target.context.state["credential_valid"]
    evidence = RelationshipEvidenceDTO(
        GrantSource.SIGNED_CREDENTIAL,
        target.context.resource_id,
        principal.user_id,
        target.context.resource_type,
        target.context.resource_id,
        credential_valid,
        target.context.scope,
    )
    return replace(
        facts,
        relationships=(*facts.relationships, evidence),
        credential_valid=credential_valid,
        domain_valid=target.context.state["domain_valid"],
    )


WORKBENCH_SESSION_ADAPTER = ResourceAdapter(
    "workbench_session",
    resolve_workbench_session,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    workbench_session_facts,
)


@dataclass(frozen=True)
class ResolvedWorkbenchAcquisition:
    kind: str
    role_slot: str
    disease_ids: tuple[int, ...]
    lab_unit_id: int
    tasks: tuple[GradingTask, ...] = ()


def resolve_workbench_acquisition(db, reference: object) -> ResourceTarget | None:
    if not isinstance(reference, WorkbenchAcquisitionRef):
        return None
    if reference.kind not in {"next", "linked", "task", "revision", "package"}:
        return None
    if reference.role_slot is not None and reference.role_slot not in {
        "resident",
        "resident2",
        "arbitrator",
    }:
        return None

    tasks: tuple[GradingTask, ...] = ()
    owner_id = None
    role_slot = reference.role_slot
    if reference.kind == "task":
        if not is_stable_resource_id(reference.identifier) or role_slot is None:
            return None
        task = db.execute(
            select(GradingTask).where(GradingTask.uuid == reference.identifier)
        ).scalar_one_or_none()
        if task is None:
            return None
        tasks = (task,)
    elif reference.kind == "revision":
        if not is_positive_int(reference.identifier):
            return None
        grade = db.get(Grade, reference.identifier)
        if grade is None or grade.role_slot not in {
            "resident",
            "resident2",
            "arbitrator",
        }:
            return None
        if role_slot is not None and role_slot != grade.role_slot:
            return None
        role_slot = grade.role_slot
        task = db.get(GradingTask, grade.task_id)
        if task is None:
            return None
        tasks = (task,)
        owner_id = grade.grader_user_id
    elif reference.kind == "package":
        if not is_stable_resource_id(reference.identifier) or role_slot is None:
            return None
        package = db.execute(
            select(EncounterSetGradingPackage).where(
                EncounterSetGradingPackage.uuid == reference.identifier
            )
        ).scalar_one_or_none()
        if package is None or not package.tasks:
            return None
        tasks = tuple(package.tasks)
    else:
        expected_count = 1 if reference.kind == "next" else 2
        if (
            reference.identifier is not None
            or role_slot is None
            or not is_positive_int(reference.lab_unit_id)
            or len(reference.disease_ids) != expected_count
            or len(set(reference.disease_ids)) != expected_count
            or any(not is_positive_int(value) for value in reference.disease_ids)
        ):
            return None
        if db.get(LabUnit, reference.lab_unit_id) is None:
            return None
        if any(db.get(Disease, disease_id) is None for disease_id in reference.disease_ids):
            return None

    if tasks:
        lab_unit_ids = {task.lab_unit_id for task in tasks}
        project_ids = {task.project_id for task in tasks}
        if len(lab_unit_ids) != 1 or len(project_ids) != 1:
            return None
        lab_unit_id = next(iter(lab_unit_ids))
        project_id = next(iter(project_ids))
        disease_ids = tuple(sorted({task.disease_id for task in tasks}))
        if reference.lab_unit_id is not None and reference.lab_unit_id != lab_unit_id:
            return None
        if reference.disease_ids and set(reference.disease_ids) != set(disease_ids):
            return None
    else:
        lab_unit_id = reference.lab_unit_id
        project_id = None
        disease_ids = tuple(sorted(reference.disease_ids))
    scope = resolve_scope(db, project_id=project_id, lab_unit_id=lab_unit_id)
    if scope is None or role_slot is None:
        return None
    value = ResolvedWorkbenchAcquisition(
        reference.kind, role_slot, disease_ids, lab_unit_id, tasks
    )
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "workbench_acquisition_target",
            f"{reference.kind}:{reference.identifier or '-'}:{role_slot}:{lab_unit_id}",
            scope,
            owner_id=owner_id,
            state={"domain_valid": True},
            resolved=True,
        ),
    )


def workbench_acquisition_facts(db, principal, _action, target, facts):
    value = target.value
    if principal.user_id is None or not isinstance(value, ResolvedWorkbenchAcquisition):
        return facts
    slot_columns = {
        "resident": (UserDiseaseUnitRole.can_grade_resident, UserDiseaseUnitRole.can_grade_resident2),
        "resident2": (UserDiseaseUnitRole.can_grade_resident2,),
        "arbitrator": (UserDiseaseUnitRole.can_arbitrate,),
    }
    eligibility_ids: list[int] = []
    for disease_id in value.disease_ids:
        rows = tuple(
            db.execute(
                select(UserDiseaseUnitRole).where(
                    UserDiseaseUnitRole.user_id == principal.user_id,
                    UserDiseaseUnitRole.disease_id == disease_id,
                    UserDiseaseUnitRole.lab_unit_id == value.lab_unit_id,
                    UserDiseaseUnitRole.active.is_(True),
                )
            ).scalars()
        )
        eligible = next(
            (
                row
                for row in rows
                if any(bool(getattr(row, column.key)) for column in slot_columns[value.role_slot])
            ),
            None,
        )
        if eligible is None:
            return replace(facts, domain_valid=True)
        eligibility_ids.append(eligible.id)
    facts = ownership_facts(db, principal, _action, target, facts)
    evidence = RelationshipEvidenceDTO(
        GrantSource.GRADING_SLOT,
        ":".join(str(value) for value in sorted(eligibility_ids)),
        principal.user_id,
        target.context.resource_type,
        target.context.resource_id,
        True,
        target.context.scope,
    )
    return replace(
        facts,
        relationships=(*facts.relationships, evidence),
        grading_slot_matches=True,
        domain_valid=True,
    )


WORKBENCH_ACQUISITION_ADAPTER = ResourceAdapter(
    "workbench_acquisition_target",
    resolve_workbench_acquisition,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    workbench_acquisition_facts,
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
    if isinstance(reference, GradingSchemeGradeRef):
        if not is_positive_int(reference.scheme_id) or not is_positive_int(
            reference.grade_id
        ):
            return None
        value = db.get(DiseaseGrading, reference.grade_id)
        if value is None or value.disease_id != reference.scheme_id:
            return None
        return ResourceTarget(
            value,
            ResourceContextDTO(
                "grading_config_record",
                f"grading_scheme_grade:{reference.scheme_id}:{value.id}",
                ScopeDTO(ScopeType.SYSTEM),
                state={"domain_valid": True},
                resolved=True,
            ),
        )
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
    "ai_model_integration": AIModelIntegration,
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
    if len(tasks) != len(ids):
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
def resolve_project_allocation_target(
    db, reference: object
) -> ResourceTarget | None:
    if not isinstance(reference, ProjectAllocationTargetRef) or not is_positive_int(
        reference.project_id
    ):
        return None
    if reference.allocation_id is not None:
        if (
            not is_positive_int(reference.allocation_id)
            or reference.lab_unit_id is not None
            or reference.user_id is not None
        ):
            return None
        allocation = db.get(ProjectGraderAllocation, reference.allocation_id)
        if allocation is None or allocation.project_id != reference.project_id:
            return None
        lab_unit_id = allocation.lab_unit_id
        value = allocation
        resource_id = f"existing:{allocation.id}"
    else:
        if not is_positive_int(reference.lab_unit_id) or not is_positive_int(
            reference.user_id
        ):
            return None
        if db.get(User, reference.user_id) is None:
            return None
        lab_unit_id = reference.lab_unit_id
        value = reference
        resource_id = (
            f"proposed:{reference.project_id}:{lab_unit_id}:{reference.user_id}"
        )
    scope = resolve_scope(
        db, project_id=reference.project_id, lab_unit_id=lab_unit_id
    )
    if scope is None:
        return None
    return ResourceTarget(
        value,
        ResourceContextDTO(
            "project_allocation_target",
            resource_id,
            scope,
            state={"target_active": True, "domain_valid": True},
            resolved=True,
        ),
    )


PROJECT_ALLOCATION_TARGET_ADAPTER = ResourceAdapter(
    "project_allocation_target",
    resolve_project_allocation_target,
    lambda _db, _principal, _action, _grants, query: query.where(false()),
    lambda _db, _principal, _action, _target, facts: replace(
        facts, domain_valid=True
    ),
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
    REMOTE_INFERENCE_BATCH_ADAPTER,
    UPLOAD_LAB_UNIT_ADAPTER,
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
    INTRA_RATER_BATCH_TARGET_ADAPTER,
    INTRA_RATER_TASK_ADAPTER,
    IITK_CONFIGURATION_ADAPTER,
    IITK_CONFIGURATION_TARGET_ADAPTER,
    JOB_ADAPTER,
    LOOKUP_RECORD_ADAPTER,
    MOBILE_SESSION_ADAPTER,
    NOTIFICATION_TARGET_ADAPTER,
    PASSWORD_RESET_ADAPTER,
    PROJECT_ALLOCATION_TARGET_ADAPTER,
    PROJECT_SITE_POLICY_ADAPTER,
    REPORT_ADAPTER,
    REMIDIO_CONFIG_ADAPTER,
    REMIDIO_ENCOUNTER_MIGRATION_ADAPTER,
    REMIDIO_ATTACHMENT_ADAPTER,
    REMIDIO_PROJECT_SYNC_ADAPTER,
    S3_CONFIG_ADAPTER,
    S3_SYNC_QUERY_ADAPTER,
    S3_SYNC_RECORD_ADAPTER,
    SENSITIVE_AUDIT_EVENT_ADAPTER,
    SYSTEM_OPERATION_ADAPTER,
    TASK_BACKFILL_TARGET_ADAPTER,
    UPLOAD_JOB_ADAPTER,
    UPLOAD_PROFILE_ADAPTER,
    UPLOAD_METADATA_FIELD_DEFINITION_ADAPTER,
    UPLOAD_TARGET_ADAPTER,
    WORKBENCH_SESSION_ADAPTER,
    WORKBENCH_ACQUISITION_ADAPTER,
)
