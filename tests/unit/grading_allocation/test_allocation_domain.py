from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event

from grading_allocation import eligibility as eligibility_module
from grading_allocation.constants import AllocationCapacity, AllocationScope
from grading_allocation.dashboard import list_project_encounter_set_queues
from grading_allocation.dtos import AllocationInputDTO, TargetIdentity, TaskAllocationContext
from grading_allocation.eligibility import (
    eligible_enforced_project_task_contexts,
    is_user_eligible_for_task,
)
from grading_allocation.exceptions import AllocationConflictError
from grading_allocation.models import ProjectGraderAllocation, ProjectGradingAllocationPolicy
from grading_allocation.resolver import resolve_task_allocation_context
from grading_allocation.service import (
    create_or_reactivate_allocation,
    get_project_allocation_state,
    set_project_enforcement,
)
from grading_allocation.targets import derive_project_targets
from encounter_set_types.models import EncounterSetType
from models import (
    Disease,
    DiseaseGrading,
    DirectImageUpload,
    EncounterSetImage,
    EncounterSetGradingPackage,
    Grade,
    GradingTask,
    Project,
    UserDiseaseUnitRole,
)
from tests.helpers.factories import ImageFactory, UserFactory
from tests.helpers.test_factories import TestDataFactory
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeGradingPackage,
    UploadProfileEncounterSetTypePackageEncounterScheme,
    UploadProfileEncounterSetTypePackageImageScheme,
    UploadProfileKind,
)
from utils.dualGradingGetNextTasks import get_next_eligible_resident2_task_atomic
from utils.dualGradingKPIs import get_user_kpi_pending_task_count_data
from media.authorization import (
    MediaAccessDenied,
    MediaSourceType,
    authorize_media_source,
)


def _can_view_media(db, user, media_uuid: str) -> bool:
    """Whether a user may view one image through the central media authorizer.

    Replaces utils.utilsImgServe._user_has_grading_access_to_image, removed in
    35f04df3 when media authorization moved behind media.authorization.
    """
    try:
        authorize_media_source(
            db,
            user=user,
            media_uuid=media_uuid,
            action="media.image.view",
            expected_sources=frozenset({MediaSourceType.DIRECT_IMAGE_UPLOAD}),
        )
    except MediaAccessDenied:
        return False
    return True


class _DictCache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, timeout=None):
        self.values[key] = value
        return True

    def delete(self, key):
        self.values.pop(key, None)
        return True


def _project_with_image_target(db_session, disease):
    suffix = uuid4().hex[:8]
    project = Project(title=f"Allocation Project {suffix}", code=f"ALLOC-{suffix}", active=True)
    profile = UploadProfile(name=f"Allocation Profile {suffix}", active=True)
    db_session.add_all([project, profile])
    db_session.flush()
    db_session.add_all(
        [
            ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True),
            UploadProfileDisease(upload_profile_id=profile.id, disease_id=disease.id, is_default=True),
        ]
    )
    db_session.flush()
    return project, profile


def _direct_task(db_session, core_test_data, uploader, disease, *, project=None):
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=core_test_data["hospital"].id,
        lab_unit_id=core_test_data["lab_unit"].id,
        user_id=uploader.id,
        disease_id=disease.id,
        camera_id=core_test_data["camera"].id,
        area_id=core_test_data["area"].id,
    )
    image.project_id = project.id if project else None
    task = GradingTask(
        direct_image_upload_id=image.id,
        disease_id=disease.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        state="pending",
    )
    db_session.add(task)
    db_session.flush()
    return task


def test_targets_are_derived_from_active_project_profiles(db_session, core_test_data):
    disease = db_session.merge(core_test_data["dr"])
    project, profile = _project_with_image_target(db_session, disease)

    targets, warnings = derive_project_targets(db_session, project.id)

    assert warnings == []
    assert len(targets) == 1
    assert targets[0].identity.scope == AllocationScope.DISEASE_IMAGE
    assert targets[0].identity.disease_id == disease.id
    assert targets[0].source_profiles == {profile.id: profile.name}
    assert targets[0].to_dict()["task_family"] == "image_wise_non_set"


def test_unified_encounter_set_target_lists_its_image_diseases(
    db_session,
    core_test_data,
):
    dr = db_session.merge(core_test_data["dr"])
    glaucoma = db_session.merge(core_test_data["glaucoma"])
    suffix = uuid4().hex[:8]
    project = Project(
        title=f"Unified Allocation {suffix}",
        code=f"UNIFIED-{suffix}",
        active=True,
    )
    profile = UploadProfile(name=f"Unified Profile {suffix}", active=True)
    encounter_scheme = Disease(
        name=f"Unified Encounter Scheme {suffix}",
        grading_scope="encounter",
    )
    encounter_set_type = EncounterSetType(
        name=f"Unified EncounterSet {suffix}",
        code=f"unified_{suffix}",
        metadata_schema_json={"fields": []},
        asset_rules_json={},
        active=True,
    )
    db_session.add_all([project, profile, encounter_scheme, encounter_set_type])
    db_session.flush()
    profile.upload_kinds.append(UploadProfileKind(upload_kind="encounter_set"))
    db_session.add(
        ProjectUploadProfile(
            project_id=project.id,
            upload_profile_id=profile.id,
            active=True,
        )
    )
    est_config = UploadProfileEncounterSetType(
        upload_profile_id=profile.id,
        encounter_set_type_id=encounter_set_type.id,
        active=True,
    )
    db_session.add(est_config)
    db_session.flush()
    package = UploadProfileEncounterSetTypeGradingPackage(
        upload_profile_encounter_set_type_id=est_config.id,
        name="Unified Package",
        code="unified",
        applicability="always",
        grading_mode="unified",
        default_image_grading_scheme_id=dr.id,
        active=True,
    )
    db_session.add(package)
    db_session.flush()
    db_session.add_all(
        [
            UploadProfileEncounterSetTypePackageImageScheme(
                package_id=package.id,
                disease_id=dr.id,
                is_default=True,
                active=True,
            ),
            UploadProfileEncounterSetTypePackageImageScheme(
                package_id=package.id,
                disease_id=glaucoma.id,
                active=True,
            ),
            UploadProfileEncounterSetTypePackageEncounterScheme(
                package_id=package.id,
                disease_id=encounter_scheme.id,
                active=True,
            ),
        ]
    )
    db_session.flush()

    targets, warnings = derive_project_targets(db_session, project.id)

    assert warnings == []
    assert len(targets) == 1
    payload = targets[0].to_dict()
    assert payload["task_family"] == "encounter_set_scoped"
    assert {row["name"] for row in payload["diseases"]} == {dr.name, glaucoma.name}


def test_disease_encounter_set_target_covers_package_image_and_encounter_tasks(
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, profile = _project_with_image_target(db_session, disease)
    profile.upload_kinds.append(UploadProfileKind(upload_kind="encounter_set"))
    suffix = uuid4().hex[:8]
    encounter_scheme = Disease(
        name=f"DR Encounter Status {suffix}",
        grading_scope="encounter",
    )
    encounter_set_type = EncounterSetType(
        name=f"Retinal Encounter {suffix}",
        code=f"retinal_{suffix}",
        metadata_schema_json={"fields": []},
        asset_rules_json={},
        active=True,
    )
    db_session.add_all([encounter_scheme, encounter_set_type])
    db_session.flush()
    est_config = UploadProfileEncounterSetType(
        upload_profile_id=profile.id,
        encounter_set_type_id=encounter_set_type.id,
        active=True,
    )
    db_session.add(est_config)
    db_session.flush()
    package_config = UploadProfileEncounterSetTypeGradingPackage(
        upload_profile_encounter_set_type_id=est_config.id,
        name="DR Package",
        code="dr",
        applicability="always",
        grading_mode="disease_specific",
        default_image_grading_scheme_id=disease.id,
        active=True,
    )
    db_session.add(package_config)
    db_session.flush()
    db_session.add_all(
        [
            UploadProfileEncounterSetTypePackageImageScheme(
                package_id=package_config.id,
                disease_id=disease.id,
                is_default=True,
                auto_create_policy="always",
                active=True,
            ),
            UploadProfileEncounterSetTypePackageEncounterScheme(
                package_id=package_config.id,
                disease_id=encounter_scheme.id,
                active=True,
            ),
        ]
    )
    encounter = TestDataFactory.create_patient_encounter(db_session, lab_unit_id=lab.id)
    encounter.project_id = project.id
    encounter.upload_profile_id = profile.id
    runtime_package = EncounterSetGradingPackage(
        patient_encounter_id=encounter.id,
        upload_profile_est_grading_package_id=package_config.id,
        encounter_set_type_id=encounter_set_type.id,
        name=package_config.name,
        code=package_config.code,
        grading_mode="disease_specific",
        root_scope_disease_id=disease.id,
        state="pending",
    )
    db_session.add(runtime_package)
    db_session.flush()
    task = GradingTask(
        patient_encounter_id=encounter.id,
        encounter_set_package_id=runtime_package.id,
        disease_id=encounter_scheme.id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        state="pending",
    )
    db_session.add(task)
    db_session.flush()
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename=f"allocation_{suffix}.jpg",
        folder_rel="tests/grading_allocation",
        project_id=project.id,
    )
    db_session.add(image)
    db_session.flush()
    image_task = GradingTask(
        encounter_set_image_id=image.id,
        encounter_set_package_id=runtime_package.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        grading_target_level="image",
        state="pending",
    )
    db_session.add(image_task)
    db_session.flush()
    unconfigured_encounter_task = GradingTask(
        patient_encounter_id=encounter.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        grading_target_level="encounter",
        state="pending",
    )
    db_session.add(unconfigured_encounter_task)
    db_session.flush()

    targets, warnings = derive_project_targets(db_session, project.id)
    package_config.active = False
    db_session.flush()
    context = resolve_task_allocation_context(db_session, task)
    image_context = resolve_task_allocation_context(db_session, image_task)

    assert warnings == []
    assert any(
        target.identity.scope == AllocationScope.DISEASE_ENCOUNTER
        and target.identity.disease_id == disease.id
        and target.identity.encounter_set_type_id == encounter_set_type.id
        for target in targets
    )
    assert not any(
        target.identity.scope == AllocationScope.DISEASE_IMAGE
        for target in targets
    )
    assert context.target is not None
    assert context.target.scope == AllocationScope.DISEASE_ENCOUNTER
    assert context.target.disease_id == disease.id
    assert context.target.encounter_set_type_id == encounter_set_type.id
    assert image_context.target == context.target
    disease_target = next(
        target
        for target in targets
        if target.identity.scope == AllocationScope.DISEASE_ENCOUNTER
    )
    assert disease_target.to_dict()["task_family"] == "image_scoped_encounter_set"
    assert disease_target.to_dict()["diseases"] == [
        {"id": disease.id, "name": disease.name}
    ]

    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"encounter_set_resident_{suffix}",
        lab_units=[lab],
    )
    db_session.add_all(
        [
            ProjectGradingAllocationPolicy(
                project_id=project.id,
                enforcement_enabled=True,
            ),
            ProjectGraderAllocation(
                project_id=project.id,
                user_id=resident.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_ENCOUNTER.value,
                disease_id=disease.id,
                encounter_set_type_id=encounter_set_type.id,
                capacity=AllocationCapacity.RESIDENT.value,
                active=True,
            ),
            UserDiseaseUnitRole(
                user_id=resident.id,
                disease_id=disease.id,
                lab_unit_id=lab.id,
                can_grade_resident=True,
                active=True,
            ),
        ]
    )
    db_session.flush()
    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=task,
        role_slot="resident",
    ) is True
    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=image_task,
        role_slot="resident",
    ) is True
    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=unconfigured_encounter_task,
        role_slot="resident",
    ) is False

    queues = list_project_encounter_set_queues(db_session, user_id=resident.id)
    assert len(queues) == 1
    assert queues[0].project_id == project.id
    assert queues[0].target_key == (
        f"disease_encounter:{disease.id}:{encounter_set_type.id}"
    )
    assert queues[0].slots[0].slot == "resident"
    assert queues[0].slots[0].package_count == 1
    assert queues[0].slots[0].task_count == 2

    mixed_kpis = get_user_kpi_pending_task_count_data(db_session, resident.id)
    separated_kpis = get_user_kpi_pending_task_count_data(
        db_session,
        resident.id,
        exclude_enforced_project_encounter_sets=True,
    )
    assert mixed_kpis[disease.name]["resident_pending"] == 2
    assert separated_kpis[disease.name]["resident_pending"] == 0


def test_bulk_eligibility_queries_are_bounded_and_warm_cache_keeps_conflicts_live(
    db_session,
    core_test_data,
    monkeypatch,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"bulk_eligibility_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    db_session.add(
        ProjectGraderAllocation(
            project_id=project.id,
            user_id=resident.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_IMAGE.value,
            disease_id=disease.id,
            capacity=AllocationCapacity.RESIDENT.value,
            active=True,
        )
    )
    db_session.flush()
    project_id = project.id
    lab_id = lab.id
    disease_id = disease.id

    monkeypatch.setattr(eligibility_module, "cache", _DictCache())
    tasks = [SimpleNamespace(id=100_000 + index) for index in range(100)]

    def context_for_task(_db, task):
        return TaskAllocationContext(
            task_id=task.id,
            project_id=project_id,
            lab_unit_id=lab_id,
            target=TargetIdentity(
                scope=AllocationScope.DISEASE_IMAGE,
                disease_id=disease_id,
            ),
            source_project_ids=(project_id,),
        )

    monkeypatch.setattr(
        eligibility_module,
        "resolve_task_allocation_context",
        context_for_task,
    )
    bind = db_session.get_bind()

    def run_and_count_queries():
        statements = []

        def count_query(_conn, _cursor, statement, *_args, **_kwargs):
            statements.append(statement)

        event.listen(bind, "before_cursor_execute", count_query)
        try:
            contexts = eligible_enforced_project_task_contexts(
                db_session,
                user_id=resident.id,
                task_slots=[(task, "resident") for task in tasks],
                enforced_project_ids={project_id},
            )
        finally:
            event.remove(bind, "before_cursor_execute", count_query)
        return contexts, statements

    cold_contexts, cold_statements = run_and_count_queries()
    warm_contexts, warm_statements = run_and_count_queries()

    assert len(cold_contexts) == 100
    assert warm_contexts == cold_contexts
    assert len(cold_statements) == 3, [
        "FROM " + statement.replace("\n", " ").split(" FROM ", 1)[-1][:120]
        for statement in cold_statements
    ]
    assert len(warm_statements) == 1, [
        statement.splitlines()[0] for statement in warm_statements
    ]


def test_eligibility_snapshot_is_cached_and_invalidatable(
    db_session,
    core_test_data,
    monkeypatch,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"cached_eligibility_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    db_session.add(
        ProjectGraderAllocation(
            project_id=project.id,
            user_id=resident.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_IMAGE.value,
            disease_id=disease.id,
            capacity=AllocationCapacity.RESIDENT.value,
            active=True,
        )
    )
    db_session.flush()

    fake_cache = _DictCache()
    monkeypatch.setattr(eligibility_module, "cache", fake_cache)

    first = eligibility_module._cached_user_eligibility_snapshot(
        db_session,
        user_id=resident.id,
    )
    second = eligibility_module._cached_user_eligibility_snapshot(
        db_session,
        user_id=resident.id,
    )

    assert first == second
    assert len(fake_cache.values) == 1
    eligibility_module.invalidate_user_eligibility_cache(resident.id)
    assert fake_cache.values == {}


def test_projectless_resident_can_fill_resident2_slot(db_session, core_test_data):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"resident_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    db_session.add(
        UserDiseaseUnitRole(
            user_id=resident.id,
            disease_id=disease.id,
            lab_unit_id=lab.id,
            can_grade_resident=True,
            can_grade_resident2=False,
            can_arbitrate=False,
            active=True,
        )
    )
    task = _direct_task(db_session, core_test_data, resident, disease)

    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=task,
        role_slot="resident2",
    ) is True


def test_enabled_project_policy_uses_exact_project_allocation(db_session, core_test_data):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"project_resident_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    task = _direct_task(db_session, core_test_data, resident, disease, project=project)
    db_session.add_all(
        [
            ProjectGradingAllocationPolicy(project_id=project.id, enforcement_enabled=True),
            ProjectGraderAllocation(
                project_id=project.id,
                user_id=resident.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_IMAGE.value,
                disease_id=disease.id,
                encounter_set_type_id=None,
                capacity=AllocationCapacity.RESIDENT.value,
                active=True,
            ),
        ]
    )
    db_session.flush()

    context = resolve_task_allocation_context(db_session, task)
    assert context.project_id == project.id
    assert context.target is not None
    assert context.target.scope == AllocationScope.DISEASE_IMAGE
    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=task,
        role_slot="resident2",
    ) is True
    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=task,
        role_slot="arbitrator",
    ) is False


def test_next_task_queue_uses_project_resident_allocation_for_resident2(
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"queue_project_resident_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    task = _direct_task(db_session, core_test_data, resident, disease, project=project)
    task.state = "resident_done"
    db_session.add_all(
        [
            ProjectGradingAllocationPolicy(project_id=project.id, enforcement_enabled=True),
            ProjectGraderAllocation(
                project_id=project.id,
                user_id=resident.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_IMAGE.value,
                disease_id=disease.id,
                capacity=AllocationCapacity.RESIDENT.value,
                active=True,
            ),
        ]
    )
    db_session.flush()

    selected = get_next_eligible_resident2_task_atomic(
        resident.id,
        disease.id,
        lab.id,
        db=db_session,
    )

    assert selected.id == task.id


def test_prior_resident_grade_blocks_resident2_and_arbitrator_for_same_user(
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    grader = UserFactory.create_ophthalmologist(
        db_session,
        username=f"independent_grader_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    task = _direct_task(db_session, core_test_data, grader, disease, project=project)
    grading = (
        db_session.query(DiseaseGrading)
        .filter(DiseaseGrading.disease_id == disease.id)
        .first()
    )
    assert grading is not None
    db_session.add_all(
        [
            ProjectGradingAllocationPolicy(project_id=project.id, enforcement_enabled=True),
            ProjectGraderAllocation(
                project_id=project.id,
                user_id=grader.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_IMAGE.value,
                disease_id=disease.id,
                capacity=AllocationCapacity.RESIDENT.value,
                active=True,
            ),
            ProjectGraderAllocation(
                project_id=project.id,
                user_id=grader.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_IMAGE.value,
                disease_id=disease.id,
                capacity=AllocationCapacity.ARBITRATOR.value,
                active=True,
            ),
            Grade(
                task_id=task.id,
                grader_user_id=grader.id,
                role_slot="resident",
                disease_grading_id=grading.id,
            ),
        ]
    )
    db_session.flush()

    assert is_user_eligible_for_task(
        db_session,
        user_id=grader.id,
        task=task,
        role_slot="resident2",
    ) is False
    assert is_user_eligible_for_task(
        db_session,
        user_id=grader.id,
        task=task,
        role_slot="arbitrator",
    ) is False


def test_disabled_project_policy_preserves_legacy_eligibility(db_session, core_test_data):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"legacy_project_resident_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    db_session.add(
        UserDiseaseUnitRole(
            user_id=resident.id,
            disease_id=disease.id,
            lab_unit_id=lab.id,
            can_grade_resident=True,
            active=True,
        )
    )
    db_session.add(ProjectGradingAllocationPolicy(project_id=project.id, enforcement_enabled=False))
    task = _direct_task(db_session, core_test_data, resident, disease, project=project)

    assert is_user_eligible_for_task(
        db_session,
        user_id=resident.id,
        task=task,
        role_slot="resident",
    ) is True


def test_service_creates_normalized_allocation_and_treats_arbitrator_as_optional(
    app,
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    admin_user = UserFactory.create_admin(
        db_session,
        username=f"allocation_admin_{uuid4().hex[:8]}",
    )
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"service_resident_{uuid4().hex[:8]}",
        lab_units=[lab],
    )
    allocation = create_or_reactivate_allocation(
        admin_user.id,
        project.id,
        AllocationInputDTO(
            user_id=resident.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_IMAGE,
            disease_id=disease.id,
            capacity=AllocationCapacity.RESIDENT,
        ),
    )

    state = get_project_allocation_state(admin_user.id, project.id)

    assert allocation.capacity == "resident"
    assert state.policy.enforcement_enabled is False
    assert state.targets[0]["coverage"] == {"resident": 1, "arbitrator": 0}
    assert state.warnings == ()


def test_project_allocation_grants_cross_lab_grading_media_access(
    app,
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    suffix = uuid4().hex[:8]
    admin = UserFactory.create_admin(db_session, username=f"media_admin_{suffix}")
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"media_resident_{suffix}",
        lab_units=[],
    )
    task = _direct_task(db_session, core_test_data, admin, disease, project=project)
    create_or_reactivate_allocation(
        admin.id,
        project.id,
        AllocationInputDTO(
            user_id=resident.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_IMAGE,
            disease_id=disease.id,
            capacity=AllocationCapacity.RESIDENT,
        ),
    )
    db_session.add(
        ProjectGradingAllocationPolicy(
            project_id=project.id,
            enforcement_enabled=True,
        )
    )
    db_session.flush()

    assert resident.lab_units == []
    assert _can_view_media(
        db_session,
        resident,
        db_session.get(DirectImageUpload, task.direct_image_upload_id).uuid,
    ) is True


def test_service_enables_enforcement_with_resident_coverage_only(
    app,
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    project, _profile = _project_with_image_target(db_session, disease)
    suffix = uuid4().hex[:8]
    admin = UserFactory.create_admin(db_session, username=f"policy_admin_{suffix}")
    resident = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"policy_resident_{suffix}",
        lab_units=[lab],
    )
    create_or_reactivate_allocation(
        admin.id,
        project.id,
        AllocationInputDTO(
            user_id=resident.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_IMAGE,
            disease_id=disease.id,
            capacity=AllocationCapacity.RESIDENT,
        ),
    )

    policy = set_project_enforcement(admin.id, project.id, enabled=True)

    assert policy.enforcement_enabled is True


def test_service_rejects_enforcement_without_project_targets(
    app,
    db_session,
):
    suffix = uuid4().hex[:8]
    project = Project(
        title=f"Empty Allocation Project {suffix}",
        code=f"EMPTY-ALLOC-{suffix}",
        active=True,
    )
    db_session.add(project)
    admin = UserFactory.create_admin(
        db_session,
        username=f"empty_allocation_admin_{suffix}",
    )
    db_session.flush()

    with pytest.raises(AllocationConflictError, match="without an active grading target"):
        set_project_enforcement(admin.id, project.id, enabled=True)


def test_service_rejects_enforcement_with_arbitrator_but_no_resident(
    app,
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_a2"])
    project, _profile = _project_with_image_target(db_session, disease)
    suffix = uuid4().hex[:8]
    admin = UserFactory.create_admin(db_session, username=f"split_lab_admin_{suffix}")
    arbitrator = UserFactory.create_ophthalmologist(
        db_session,
        username=f"split_lab_arbitrator_{suffix}",
        lab_units=[lab],
    )
    create_or_reactivate_allocation(
        admin.id,
        project.id,
        AllocationInputDTO(
            user_id=arbitrator.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_IMAGE,
            disease_id=disease.id,
            capacity=AllocationCapacity.ARBITRATOR,
        ),
    )

    with pytest.raises(AllocationConflictError) as exc_info:
        set_project_enforcement(admin.id, project.id, enabled=True)

    assert exc_info.value.details["warnings"] == [
        {
            "code": "grading_target_capacity_missing",
            "target_key": f"disease_image:{disease.id}:none",
            "missing_capacities": ["resident"],
            "message": (
                f"Target 'disease_image:{disease.id}:none' has no active "
                "resident allocation."
            ),
        }
    ]
