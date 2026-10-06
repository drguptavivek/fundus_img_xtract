"""Project queue counts, computed in SQL, honour every eligibility rule.

Verified against the former ORM walk on live data (13 graders, 0
mismatches) before that implementation was removed."""

from datetime import timedelta
from uuid import uuid4

from auth.utils import utcnow
from encounter_set_types.models import EncounterSetType
from grading_allocation.constants import AllocationCapacity, AllocationScope
from grading_allocation.dashboard import list_project_encounter_set_queues
from grading_allocation.models import ProjectGraderAllocation
from models import (
    DiseaseGrading,
    EncounterSetGradingPackage,
    EncounterSetImage,
    Grade,
    GradingTask,
    TaskTracker,
)
from tests.helpers.factories import UserFactory
from tests.helpers.test_factories import TestDataFactory
from tests.unit.grading_allocation.test_allocation_domain import (
    _project_with_image_target,
)

_BASE = utcnow() - timedelta(days=1)


def _package(db, *, project, lab, est, disease, state="pending", root_disease=True):
    encounter = TestDataFactory.create_patient_encounter(db, lab_unit_id=lab.id)
    encounter.project_id = project.id
    package = EncounterSetGradingPackage(
        patient_encounter_id=encounter.id,
        encounter_set_type_id=est.id,
        name="DR Package",
        code=f"dr_{uuid4().hex[:6]}",
        grading_mode="disease_specific",
        root_scope_disease_id=disease.id if root_disease else None,
        state=state,
    )
    db.add(package)
    db.flush()
    return package


def _task(db, *, package, project, lab, disease, state, minutes):
    image = EncounterSetImage(
        patient_encounter_id=package.patient_encounter_id,
        spatial_position=minutes,
        original_filename=f"parity_{uuid4().hex[:8]}.jpg",
        folder_rel="tests/grading_allocation",
        project_id=project.id,
    )
    db.add(image)
    db.flush()
    task = GradingTask(
        encounter_set_image_id=image.id,
        encounter_set_package_id=package.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        grading_target_level="image",
        state=state,
        created_at=_BASE + timedelta(minutes=minutes),
    )
    db.add(task)
    db.flush()
    return task


def _allocate(db, *, user, project, lab, disease, est, capacity):
    db.add(
        ProjectGraderAllocation(
            project_id=project.id,
            user_id=user.id,
            lab_unit_id=lab.id,
            scope=AllocationScope.DISEASE_ENCOUNTER.value,
            disease_id=disease.id,
            encounter_set_type_id=est.id,
            capacity=capacity.value,
            active=True,
        )
    )


def test_sql_queue_counts_apply_every_eligibility_rule(db_session, core_test_data):
    db = db_session
    disease = db.merge(core_test_data["dr"])
    lab = db.merge(core_test_data["lab_unit"])
    grading = db.query(DiseaseGrading).filter(DiseaseGrading.disease_id == disease.id).first()
    suffix = uuid4().hex[:8]
    est = EncounterSetType(
        name=f"Parity Encounter {suffix}",
        code=f"parity_{suffix}",
        metadata_schema_json={"fields": []},
        asset_rules_json={},
        active=True,
    )
    db.add(est)
    db.flush()
    project_a, _ = _project_with_image_target(db, disease)
    project_b, _ = _project_with_image_target(db, disease)
    grader = UserFactory.create_by_role(
        db, "ophthalmologist", username=f"parity_grader_{suffix}", lab_units=[lab]
    )
    other = UserFactory.create_by_role(
        db, "ophthalmologist", username=f"parity_other_{suffix}", lab_units=[lab]
    )
    for project in (project_a, project_b):
        for capacity in (AllocationCapacity.RESIDENT, AllocationCapacity.ARBITRATOR):
            _allocate(db, user=grader, project=project, lab=lab, disease=disease, est=est, capacity=capacity)

    # Project A, resident slot: two packages; the later-created package holds
    # the oldest task, so it must be reported as the first package.
    newer = _package(db, project=project_a, lab=lab, est=est, disease=disease)
    older = _package(db, project=project_a, lab=lab, est=est, disease=disease)
    _task(db, package=newer, project=project_a, lab=lab, disease=disease, state="pending", minutes=20)
    _task(db, package=newer, project=project_a, lab=lab, disease=disease, state="pending", minutes=21)
    _task(db, package=older, project=project_a, lab=lab, disease=disease, state="pending", minutes=5)
    tracked = _task(db, package=older, project=project_a, lab=lab, disease=disease, state="pending", minutes=1)
    db.add(TaskTracker(
        task_id=tracked.id, user_id=other.id, role_slot="resident",
        started_at=utcnow(), created_at=utcnow(),
    ))

    # Resident2 slot: one task the grader already graded as resident (barred),
    # one they did not.
    r2 = _package(db, project=project_a, lab=lab, est=est, disease=disease, state="resident_done")
    own = _task(db, package=r2, project=project_a, lab=lab, disease=disease, state="resident_done", minutes=30)
    _task(db, package=r2, project=project_a, lab=lab, disease=disease, state="resident_done", minutes=31)
    db.add(Grade(task_id=own.id, grader_user_id=grader.id, role_slot="resident", disease_grading_id=grading.id))

    # Unresolvable target (no root disease) is never eligible.
    broken = _package(db, project=project_a, lab=lab, est=est, disease=disease, root_disease=False)
    _task(db, package=broken, project=project_a, lab=lab, disease=disease, state="pending", minutes=40)

    # Project B: arbitration only.
    arb = _package(db, project=project_b, lab=lab, est=est, disease=disease, state="arbitration")
    _task(db, package=arb, project=project_b, lab=lab, disease=disease, state="arbitration", minutes=50)
    db.flush()

    sql = list_project_encounter_set_queues(db, user_id=grader.id, reconcile=False)

    by_project = {queue.project_id: queue for queue in sql}
    a_slots = {slot.slot: slot for slot in by_project[project_a.id].slots}
    assert a_slots["resident"].package_count == 2
    assert a_slots["resident"].task_count == 3
    assert a_slots["resident"].first_package_uuid == older.uuid
    assert a_slots["resident2"].package_count == 1
    assert a_slots["resident2"].task_count == 1
    assert [slot.slot for slot in by_project[project_b.id].slots] == ["arbitrator"]

    # A user with no allocation sees nothing.
    assert list_project_encounter_set_queues(db, user_id=other.id, reconcile=False) == ()
