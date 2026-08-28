from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.principals import EvaluationFactsDTO, PrincipalDTO, RoleGrantDTO
from authz_v2.core.resources import ResourceContextDTO, ScopeDTO, ScopeSetDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.resources import adapters as resource_adapters
from authz_v2.resources.adapters import (
    TypedResourceRef,
    resolve_executable_config,
    resolve_grading_config,
    resolve_grading_repair_batch,
    resolve_lookup_record,
    resolve_job,
    resolve_mobile_session,
    resolve_remidio_config,
    resolve_remidio_attachment,
    resolve_remidio_project_sync,
    resolve_remote_inference_batch,
    resolve_s3_sync_query,
    resolve_s3_sync_record,
    resolve_sensitive_audit_event,
    resolve_system_operation,
    resolve_task_backfill_target,
    resolve_workbench_session,
    resolve_workbench_acquisition,
)
from authz_v2.resources.composition import register_core_adapters
from authz_v2.resources.references import (
    AdminMobileSessionTargetRef,
    AutomationTargetRef,
    ExecutableConfigRef,
    GradingConfigRef,
    GradingSchemeGradeRef,
    GradingRepairBatchRef,
    LookupRecordRef,
    JobTokenRef,
    RemidioConfigRef,
    RemidioProjectSyncRef,
    RemoteInferenceBatchRef,
    S3SyncQueryRef,
    SystemOperationRef,
    TaskBackfillTargetRef,
    WorkbenchSessionRef,
    WorkbenchAcquisitionRef,
)
from authz_v2.resources.registry import ResourceRegistry, ResourceTarget
from authz_v2.resources.scoping import scope_model_query
from authz_v2.resources.upload_targets import UploadTargetRef
from authz_v2.resources.users import user_creation_facts
from models import DirectImageUpload


def test_composition_registers_every_catalogue_resource_exactly_once():
    resources = ResourceRegistry()
    register_core_adapters(resources)
    required = {
        definition.resource_type
        for definition in CATALOGUE.values()
        if definition.requires_resource
    }
    assert resources.types() == required
    register_core_adapters(resources)
    assert resources.types() == required


def test_polymorphic_resource_families_reject_ambiguous_integer_references():
    resources = ResourceRegistry()
    register_core_adapters(resources)

    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError(
                "ambiguous reference must be rejected before DB access"
            )

    for resource_type in ("image", "encounter_file", "report", "inference_result"):
        assert resources.require(resource_type).resolver(NoDatabaseCalls(), 1) is None
    assert isinstance(TypedResourceRef("direct", 1), TypedResourceRef)

    assert (
        resources.require("project_upload_target").resolver(NoDatabaseCalls(), 1)
        is None
    )
    assert resources.require("upload_target").resolver(NoDatabaseCalls(), 1) is None


def test_every_resource_adapter_rejects_missing_or_non_positive_references():
    resources = ResourceRegistry()
    register_core_adapters(resources)

    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError("invalid reference reached the database")

        def execute(self, *_args):
            raise AssertionError("invalid reference reached the database")

    db = NoDatabaseCalls()
    for resource_type in resources.types():
        resolver = resources.require(resource_type).resolver
        for invalid in (None, True, False, 0, -1, "", "   "):
            assert resolver(db, invalid) is None, (resource_type, invalid)

    for resource_type in ("image", "encounter_file", "report", "inference_result"):
        assert (
            resources.require(resource_type).resolver(
                db, TypedResourceRef("direct", True)
            )
            is None
        )
    for resource_type in ("upload_target", "project_upload_target"):
        assert (
            resources.require(resource_type).resolver(db, UploadTargetRef(True, 1))
            is None
        )
    for resource_type in ("job", "project"):
        assert (
            resources.require(resource_type).resolver(db, AutomationTargetRef(1, True))
            is None
        )

    batch = resources.require("direct_upload_batch").resolver
    assert batch(db, []) is None
    assert batch(db, [1, 0]) is None
    assert batch(db, list(range(1, 52))) is None


def test_sql_scoper_never_uses_non_admin_system_grant_as_global_bypass():
    principal = PrincipalDTO(1, True, True)
    system_non_admin = GrantRecord(
        1, 1, Role.DATA_MANAGER, ScopeDTO(ScopeType.SYSTEM), True
    )
    query = scope_model_query(
        DirectImageUpload, (system_non_admin,), select(DirectImageUpload)
    )
    assert "WHERE false" in str(query)

    system_admin = GrantRecord(2, 1, Role.ADMIN, ScopeDTO(ScopeType.SYSTEM), True)
    unfiltered = scope_model_query(
        DirectImageUpload, (system_admin,), select(DirectImageUpload)
    )
    assert "WHERE" not in str(unfiltered)
    assert principal.authenticated


def test_classical_scope_filter_excludes_project_owned_rows():
    hospital = ScopeDTO(ScopeType.HOSPITAL, 10, hospital_id=10)
    grant = GrantRecord(1, 1, Role.DATA_MANAGER, hospital, True)
    query = scope_model_query(DirectImageUpload, (grant,), select(DirectImageUpload))
    sql = str(query)
    assert "direct_image_uploads.project_id IS NULL" in sql
    assert "direct_image_uploads.hospital_id IN" in sql


def test_user_creation_requires_delegable_roles_inside_actor_scope():
    hospital = ScopeDTO(ScopeType.HOSPITAL, 10, hospital_id=10)
    other_hospital = ScopeDTO(ScopeType.HOSPITAL, 11, hospital_id=11)
    target = ResourceTarget(
        ((Role.DATA_MANAGER, hospital),),
        ResourceContextDTO("user_creation_target", "new:hospital:10", hospital),
    )

    def creation_facts(actor_role, actor_scope):
        grant = RoleGrantDTO(1, actor_role, actor_scope)
        return EvaluationFactsDTO(
            PrincipalDTO(1, True, True),
            resource=target.context,
            active_roles=frozenset({actor_role}),
            role_grants=(grant,),
            reachable_scopes=ScopeSetDTO(frozenset({actor_scope})),
            exact_resource=True,
        )

    admin = creation_facts(Role.ADMIN, ScopeDTO(ScopeType.SYSTEM))
    assert user_creation_facts(None, admin.principal, None, target, admin).domain_valid

    user_manager = creation_facts(Role.USER_MANAGER, hospital)
    assert not user_creation_facts(
        None, user_manager.principal, None, target, user_manager
    ).domain_valid

    cross_hospital_target = ResourceTarget(
        ((Role.DATA_MANAGER, other_hospital),), target.context
    )
    assert not user_creation_facts(
        None, user_manager.principal, None, cross_hospital_target, user_manager
    ).domain_valid


def test_user_creation_never_delegates_admin_and_only_admin_delegates_leadership():
    system = ScopeDTO(ScopeType.SYSTEM)
    admin_grant = RoleGrantDTO(1, Role.ADMIN, system)
    base = EvaluationFactsDTO(
        PrincipalDTO(1, True, True),
        active_roles=frozenset({Role.ADMIN}),
        role_grants=(admin_grant,),
        reachable_scopes=ScopeSetDTO(frozenset({system})),
        exact_resource=True,
    )
    for requested_role, requested_scope in (
        (Role.ADMIN, system),
        (Role.PROJECT_PI, ScopeDTO(ScopeType.PROJECT, 40, project_id=40)),
        (
            Role.SITE_PI,
            ScopeDTO(
                ScopeType.PROJECT_LAB_UNIT,
                30,
                hospital_id=10,
                lab_unit_id=20,
                project_id=40,
                project_lab_unit_id=30,
            ),
        ),
    ):
        target = ResourceTarget(
            ((requested_role, requested_scope),),
            ResourceContextDTO("user_creation_target", "new:hospital:10", requested_scope),
        )
        result = user_creation_facts(None, base.principal, None, target, base)
        assert result.domain_valid is (requested_role is not Role.ADMIN)


def test_admin_mobile_session_reference_rejects_path_user_mismatch():
    class SessionOnlyDatabase:
        def get(self, model, resource_id):
            assert resource_id == "session-1"
            return SimpleNamespace(user_id=7)

    reference = AdminMobileSessionTargetRef(user_id=8, session_id="session-1")
    assert resolve_mobile_session(SessionOnlyDatabase(), reference) is None


def test_system_operation_reference_is_closed_and_exact():
    assert resolve_system_operation(None, "sequences_refresh") is None
    assert resolve_system_operation(None, SystemOperationRef("unknown")) is None
    target = resolve_system_operation(None, SystemOperationRef("sequences_refresh"))
    assert target is not None
    assert target.context.resource_type == "system_operation"
    assert target.context.resource_id == "sequences_refresh"
    assert target.context.resolved


def test_lookup_records_require_a_closed_kind_and_typed_identifier():
    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError("invalid lookup reference reached the database")

    db = NoDatabaseCalls()
    assert resolve_lookup_record(db, 1) is None
    assert resolve_lookup_record(db, LookupRecordRef("unknown", 1)) is None
    assert resolve_lookup_record(db, LookupRecordRef("area", 0)) is None


def test_grading_config_records_reject_ambiguous_or_unknown_references():
    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError("invalid grading config reached the database")

    db = NoDatabaseCalls()
    assert resolve_grading_config(db, 1) is None
    assert resolve_grading_config(db, GradingConfigRef("unknown", 1)) is None
    assert resolve_grading_config(db, GradingConfigRef("grading_scheme", 0)) is None
    assert resolve_grading_config(db, GradingSchemeGradeRef(0, 1)) is None
    assert resolve_grading_config(db, GradingSchemeGradeRef(1, 0)) is None


def test_grading_scheme_grade_reference_enforces_path_parent_lineage():
    class Database:
        def get(self, _model, _record_id):
            return SimpleNamespace(id=9, disease_id=4)

    db = Database()
    assert resolve_grading_config(db, GradingSchemeGradeRef(3, 9)) is None
    target = resolve_grading_config(db, GradingSchemeGradeRef(4, 9))
    assert target is not None
    assert target.context.resource_id == "grading_scheme_grade:4:9"


def test_executable_config_records_require_closed_typed_references():
    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError("invalid executable config reached the database")

    db = NoDatabaseCalls()
    assert resolve_executable_config(db, 1) is None
    assert resolve_executable_config(db, ExecutableConfigRef("unknown", 1)) is None
    assert resolve_executable_config(db, ExecutableConfigRef("ai_model", 0)) is None


def test_grading_repair_batch_rejects_missing_duplicate_and_oversized_ids():
    class NoDatabaseCalls:
        def execute(self, *_args):
            raise AssertionError("invalid repair batch reached the database")

    db = NoDatabaseCalls()
    assert resolve_grading_repair_batch(db, ()) is None
    assert resolve_grading_repair_batch(db, GradingRepairBatchRef(())) is None
    assert resolve_grading_repair_batch(db, GradingRepairBatchRef((1, 1))) is None
    assert resolve_grading_repair_batch(
        db, GradingRepairBatchRef(tuple(range(1, 102)))
    ) is None


def test_scope_sensitive_admin_targets_fail_closed_before_database_access():
    class NoDatabaseCalls:
        def get(self, *_args):
            raise AssertionError("invalid authorization reference reached the database")

        def execute(self, *_args):
            raise AssertionError("invalid authorization reference reached the database")

    db = NoDatabaseCalls()
    assert resolve_s3_sync_query(db, None) is None
    assert resolve_s3_sync_query(db, S3SyncQueryRef(0)) is None
    assert resolve_s3_sync_record(db, 0) is None
    assert resolve_sensitive_audit_event(db, "1") is None
    assert resolve_task_backfill_target(db, None) is None
    assert resolve_task_backfill_target(db, TaskBackfillTargetRef(1, ())) is None
    assert resolve_task_backfill_target(
        db, TaskBackfillTargetRef(1, (2, 2))
    ) is None
    assert resolve_remidio_config(db, 1) is None
    assert resolve_remidio_config(db, RemidioConfigRef("unknown", 1)) is None
    assert resolve_remidio_config(db, RemidioConfigRef("connection", 0)) is None
    assert resolve_remidio_attachment(db, 0) is None
    assert resolve_remidio_project_sync(db, None) is None
    assert resolve_remidio_project_sync(db, RemidioProjectSyncRef(1, ())) is None
    assert resolve_remidio_project_sync(
        db, RemidioProjectSyncRef(1, (2, 2))
    ) is None
    assert resolve_workbench_session(db, None) is None
    assert resolve_workbench_session(db, WorkbenchSessionRef("")) is None
    assert resolve_workbench_acquisition(db, None) is None
    assert resolve_workbench_acquisition(
        db, WorkbenchAcquisitionRef("unknown", None, "resident")
    ) is None
    assert resolve_workbench_acquisition(
        db, WorkbenchAcquisitionRef("next", None, "resident", (), 1)
    ) is None
    assert resolve_workbench_acquisition(
        db, WorkbenchAcquisitionRef("linked", None, None, (1, 2), 3)
    ) is None
    assert resolve_remote_inference_batch(db, None) is None
    assert resolve_remote_inference_batch(
        db, RemoteInferenceBatchRef(1, ())
    ) is None
    assert resolve_remote_inference_batch(
        db, RemoteInferenceBatchRef(1, (2, 2))
    ) is None
    assert resolve_remote_inference_batch(
        db, RemoteInferenceBatchRef(1, tuple(range(1, 102)))
    ) is None
    assert resolve_job(db, JobTokenRef("")) is None


def test_remote_inference_batch_requires_one_persisted_project_lab_scope(monkeypatch):
    class Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    class Database:
        def __init__(self, rows):
            self.rows = rows

        def execute(self, _statement):
            return Result(self.rows)

    monkeypatch.setattr(
        resource_adapters,
        "resolve_scope",
        lambda _db, *, project_id, lab_unit_id: ScopeDTO(
            ScopeType.PROJECT_LAB_UNIT,
            99,
            project_id=project_id,
            lab_unit_id=lab_unit_id,
            project_lab_unit_id=99,
        ),
    )
    reference = RemoteInferenceBatchRef(7, (11, 12))
    assert resolve_remote_inference_batch(
        Database(
            (
                SimpleNamespace(id=11, project_id=7, lab_unit_id=3),
                SimpleNamespace(id=12, project_id=8, lab_unit_id=3),
            )
        ),
        reference,
    ) is None
    assert resolve_remote_inference_batch(
        Database(
            (
                SimpleNamespace(id=11, project_id=7, lab_unit_id=3),
                SimpleNamespace(id=12, project_id=7, lab_unit_id=4),
            )
        ),
        reference,
    ) is None
    target = resolve_remote_inference_batch(
        Database(
            (
                SimpleNamespace(id=11, project_id=7, lab_unit_id=3),
                SimpleNamespace(id=12, project_id=7, lab_unit_id=3),
            )
        ),
        reference,
    )
    assert target is not None
    assert target.context.scope.project_id == 7
    assert target.context.scope.lab_unit_id == 3
