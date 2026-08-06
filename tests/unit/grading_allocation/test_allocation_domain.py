from uuid import uuid4

import pytest

from grading_allocation.constants import AllocationCapacity, AllocationScope
from grading_allocation.dtos import AllocationInputDTO
from grading_allocation.eligibility import is_user_eligible_for_task
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
        name=package_config.name,
        code=package_config.code,
        grading_mode="disease_specific",
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

    targets, warnings = derive_project_targets(db_session, project.id)
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
        "resident",
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


def test_projectless_resident_can_fill_resident2_slot(db_session, core_test_data):
    disease = db_session.merge(core_test_data["dr"])
    lab = db_session.merge(core_test_data["lab_unit"])
    resident = UserFactory.create_by_role(
        db_session,
        "resident",
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
        "resident",
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
        "resident",
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
        "resident",
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


def test_service_creates_normalized_allocation_and_reports_coverage(
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
        "resident",
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
    assert state.warnings[0]["missing_capacities"] == ["arbitrator"]


def test_service_enables_enforcement_after_both_capacities_are_covered(
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
        "resident",
        username=f"policy_resident_{suffix}",
        lab_units=[lab],
    )
    arbitrator = UserFactory.create_ophthalmologist(
        db_session,
        username=f"policy_arbitrator_{suffix}",
        lab_units=[lab],
    )
    for user, capacity in (
        (resident, AllocationCapacity.RESIDENT),
        (arbitrator, AllocationCapacity.ARBITRATOR),
    ):
        create_or_reactivate_allocation(
            admin.id,
            project.id,
            AllocationInputDTO(
                user_id=user.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_IMAGE,
                disease_id=disease.id,
                capacity=capacity,
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


def test_service_rejects_split_lab_capacity_coverage(
    app,
    db_session,
    core_test_data,
):
    disease = db_session.merge(core_test_data["dr"])
    resident_lab = db_session.merge(core_test_data["lab_a1"])
    arbitrator_lab = db_session.merge(core_test_data["lab_a2"])
    project, _profile = _project_with_image_target(db_session, disease)
    suffix = uuid4().hex[:8]
    admin = UserFactory.create_admin(db_session, username=f"split_lab_admin_{suffix}")
    resident = UserFactory.create_by_role(
        db_session,
        "resident",
        username=f"split_lab_resident_{suffix}",
        lab_units=[resident_lab],
    )
    arbitrator = UserFactory.create_ophthalmologist(
        db_session,
        username=f"split_lab_arbitrator_{suffix}",
        lab_units=[arbitrator_lab],
    )
    for user, lab, capacity in (
        (resident, resident_lab, AllocationCapacity.RESIDENT),
        (arbitrator, arbitrator_lab, AllocationCapacity.ARBITRATOR),
    ):
        create_or_reactivate_allocation(
            admin.id,
            project.id,
            AllocationInputDTO(
                user_id=user.id,
                lab_unit_id=lab.id,
                scope=AllocationScope.DISEASE_IMAGE,
                disease_id=disease.id,
                capacity=capacity,
            ),
        )

    with pytest.raises(AllocationConflictError) as exc_info:
        set_project_enforcement(admin.id, project.id, enabled=True)

    warning_codes = {
        warning["code"] for warning in exc_info.value.details["warnings"]
    }
    assert warning_codes == {"grading_target_lab_capacity_missing"}
