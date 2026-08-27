from uuid import uuid4

import pytest
from sqlalchemy import select

from authz_v2.core.actions import Action
from authz_v2.core.principals import PrincipalDTO
from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.exceptions import AuthorizationError, DenialCode
from authz_v2.repositories.contracts import GrantRecord
from authz_v2.resources.composition import build_core_registries
from authz_v2.resources.registry import ResourceAdapter, ResourceRegistry
from authz_v2.services.decision import AuthorizationDecisionService
from authz_v2.services.listing import filter_query
from models import GradingTask, Job, UserDiseaseUnitRole
from tests.helpers.factories import ImageFactory, UserFactory


class DecisionService:
    def __init__(self, resources):
        self.resources = resources

    def active_grants(self, _principal, *, db=None):
        return ()


class GrantRepository:
    def __init__(self, grant):
        self.grant = grant

    def principal(self, user_id):
        return PrincipalDTO(user_id, active=True, authenticated=True)

    def grants_for(self, user_id):
        return (self.grant,) if user_id == self.grant.user_id else ()


def test_action_specific_query_policy_precedes_scope_only_fallback():
    registry = ResourceRegistry()
    adapter = ResourceAdapter(
        "upload_target",
        lambda _db, _resource: None,
        lambda _db, _principal, _action, _grants, query: query + ("scope",),
    )
    registry.register(adapter)
    registry.register_query_policy(
        Action.UPLOAD_CREATE,
        "upload_target",
        lambda _db, _principal, _action, _grants, query: query + ("relationship",),
    )
    assert filter_query(
        None,
        object(),
        Action.UPLOAD_CREATE,
        adapter,
        (),
        decision_service=DecisionService(registry),
    ) == ("relationship",)


def test_unregistered_relationship_aware_query_denies_closed():
    registry = ResourceRegistry()
    adapter = ResourceAdapter(
        "upload_target",
        lambda _db, _resource: None,
        lambda _db, _principal, _action, _grants, query: query,
    )
    registry.register(adapter)
    with pytest.raises(AuthorizationError) as error:
        filter_query(
            None,
            object(),
            Action.UPLOAD_CREATE,
            adapter,
            (),
            decision_service=DecisionService(registry),
        )
    assert error.value.code is DenialCode.UNSUPPORTED_QUERY


@pytest.mark.parametrize(
    "action,slot_flag,state,capacity",
    [
        (
            Action.GRADING_RESIDENT_SUBMIT,
            "can_grade_resident",
            "pending",
            "resident",
        ),
        (
            Action.GRADING_RESIDENT2_SUBMIT,
            "can_grade_resident2",
            "resident_done",
            "resident",
        ),
        (
            Action.GRADING_ARBITRATOR_SUBMIT,
            "can_arbitrate",
            "arbitration",
            "arbitrator",
        ),
    ],
)
def test_core_grading_query_policies_encode_all_exact_slot_facts(
    action, slot_flag, state, capacity
):
    resources, _choices = build_core_registries()
    policy = resources.query_policy(action, "grading_task")
    assert policy is not None
    statement = policy(
        None,
        PrincipalDTO(17, active=True, authenticated=True),
        action,
        (
            GrantRecord(
                1,
                17,
                Role.OPHTHALMOLOGIST,
                ScopeDTO(
                    ScopeType.LAB_UNIT,
                    20,
                    hospital_id=10,
                    lab_unit_id=20,
                ),
                True,
            ),
        ),
        select(GradingTask),
    )
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert slot_flag in sql
    assert f"grading_tasks.state = '{state}'" in sql
    assert f"project_grader_allocations.capacity = '{capacity}'" in sql
    assert "user_disease_unit_role.disease_id = grading_tasks.disease_id" in sql
    assert "user_disease_unit_role.lab_unit_id = grading_tasks.lab_unit_id" in sql
    assert "grades.grader_user_id = 17" in sql
    assert "project_grading_allocation_policies.enforcement_enabled IS true" in sql


def test_core_participation_policy_is_registered_and_principal_bound():
    resources, _choices = build_core_registries()
    policy = resources.query_policy(Action.GRADING_GRADES_VIEW, "grading_task")
    assert policy is not None
    principal = PrincipalDTO(17, active=True, authenticated=True)
    statement = policy(
        None, principal, Action.GRADING_GRADES_VIEW, (), select(GradingTask)
    )
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE false" in sql


def test_job_result_policy_keeps_null_lab_jobs_owner_only():
    resources, _choices = build_core_registries()
    policy = resources.query_policy(Action.JOBS_RESULT_VIEW, "job")
    assert policy is not None
    system_role = GrantRecord(
        1,
        17,
        Role.FILE_UPLOADER,
        ScopeDTO(ScopeType.SYSTEM),
        True,
    )
    statement = policy(
        None,
        PrincipalDTO(17, active=True, authenticated=True),
        Action.JOBS_RESULT_VIEW,
        (system_role,),
        select(Job),
    )
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "jobs.uploader_user_id = 17" in sql
    assert "jobs.lab_unit_id IS NULL" not in sql


def test_job_result_policy_adds_containing_lab_scope_without_crossing_projects():
    resources, _choices = build_core_registries()
    policy = resources.query_policy(Action.JOBS_RESULT_VIEW, "job")
    lab_role = GrantRecord(
        1,
        17,
        Role.FILE_UPLOADER,
        ScopeDTO(
            ScopeType.LAB_UNIT,
            20,
            hospital_id=10,
            lab_unit_id=20,
        ),
        True,
    )
    statement = policy(
        None,
        PrincipalDTO(17, active=True, authenticated=True),
        Action.JOBS_RESULT_VIEW,
        (lab_role,),
        select(Job),
    )
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "jobs.uploader_user_id = 17" in sql
    assert "jobs.lab_unit_id IN (20)" in sql
    assert "jobs.project_id IS NULL" in sql


def test_job_exact_and_list_decisions_agree_for_null_lab_ownership(db_session):
    owner_id = 17001
    owned = Job(
        token=f"authz-owned-{uuid4()}",
        uploader_user_id=owner_id,
        upload_type="dataset_export",
    )
    foreign = Job(
        token=f"authz-foreign-{uuid4()}",
        uploader_user_id=owner_id + 1,
        upload_type="dataset_export",
    )
    db_session.add_all((owned, foreign))
    db_session.flush()
    grant = GrantRecord(
        1,
        owner_id,
        Role.FILE_UPLOADER,
        ScopeDTO(ScopeType.SYSTEM),
        True,
    )
    principal = PrincipalDTO(owner_id, active=True, authenticated=True)
    resources, _choices = build_core_registries()
    policy = resources.query_policy(Action.JOBS_RESULT_VIEW, "job")
    listed = tuple(
        db_session.execute(
            policy(
                db_session,
                principal,
                Action.JOBS_RESULT_VIEW,
                (grant,),
                select(Job).where(Job.id.in_((owned.id, foreign.id))),
            )
        ).scalars()
    )
    assert [row.id for row in listed] == [owned.id]

    service = AuthorizationDecisionService(GrantRepository(grant), resources)
    assert service.check(
        db_session, principal, Action.JOBS_RESULT_VIEW, owned.id
    ).allowed
    assert not service.check(
        db_session, principal, Action.JOBS_RESULT_VIEW, foreign.id
    ).allowed


def test_grading_exact_and_list_decisions_agree_on_disease_lab_slot(
    db_session, core_test_data
):
    lab = db_session.merge(core_test_data["lab_unit"])
    disease = db_session.merge(core_test_data["dr"])
    other_disease = db_session.merge(core_test_data["glaucoma"])
    user = UserFactory.create_ophthalmologist(
        db_session,
        username=f"authz-v2-grader-{uuid4()}",
        lab_units=[lab],
    )
    db_session.add(
        UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=disease.id,
            lab_unit_id=lab.id,
            can_grade_resident=True,
            active=True,
        )
    )
    allowed_image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=lab.hospital_id,
        lab_unit_id=lab.id,
        user_id=user.id,
        disease_id=disease.id,
        camera_id=core_test_data["camera"].id,
        area_id=core_test_data["area"].id,
    )
    wrong_disease_image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=lab.hospital_id,
        lab_unit_id=lab.id,
        user_id=user.id,
        disease_id=other_disease.id,
        camera_id=core_test_data["camera"].id,
        area_id=core_test_data["area"].id,
    )
    allowed_task = GradingTask(
        direct_image_upload_id=allowed_image.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="pending",
    )
    wrong_disease_task = GradingTask(
        direct_image_upload_id=wrong_disease_image.id,
        disease_id=other_disease.id,
        lab_unit_id=lab.id,
        state="pending",
    )
    db_session.add_all((allowed_task, wrong_disease_task))
    db_session.flush()
    scope = ScopeDTO(
        ScopeType.LAB_UNIT,
        lab.id,
        hospital_id=lab.hospital_id,
        lab_unit_id=lab.id,
    )
    grant = GrantRecord(1, user.id, Role.OPHTHALMOLOGIST, scope, True)
    principal = PrincipalDTO(user.id, active=True, authenticated=True)
    resources, _choices = build_core_registries()
    policy = resources.query_policy(Action.GRADING_RESIDENT_SUBMIT, "grading_task")
    listed = tuple(
        db_session.execute(
            policy(
                db_session,
                principal,
                Action.GRADING_RESIDENT_SUBMIT,
                (grant,),
                select(GradingTask).where(
                    GradingTask.id.in_((allowed_task.id, wrong_disease_task.id))
                ),
            )
        ).scalars()
    )
    assert [task.id for task in listed] == [allowed_task.id]

    service = AuthorizationDecisionService(GrantRepository(grant), resources)
    assert service.check(
        db_session,
        principal,
        Action.GRADING_RESIDENT_SUBMIT,
        allowed_task.id,
    ).allowed
    assert not service.check(
        db_session,
        principal,
        Action.GRADING_RESIDENT_SUBMIT,
        wrong_disease_task.id,
    ).allowed
