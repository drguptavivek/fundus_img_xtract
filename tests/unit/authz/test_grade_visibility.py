"""What a grader may read of the grades on a task.

A grader reads their own grades, and every other grade on a task they have
graded - the second reader's, the arbitrator's, and the AI grade allocated
to that task - so they can see how their reading compared. That visibility
is bounded by participation: grades on tasks they did not grade, including
AI grades, stay out of reach.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from authz import access_context
from grading.access import scope_inter_rater_grades
from grading_allocation.constants import AllocationScope
from grading_allocation.models import ProjectGraderAllocation
from models import (
    DirectImageUpload,
    Disease,
    DiseaseGrading,
    Grade,
    GradingTask,
    PatientEncounters,
    Project,
    Role,
    User,
    UserDiseaseUnitRole,
)
from project_configuration.models import ProjectLabUnit


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name); db.add(role); db.flush()
    return role


def _user(db, *roles):
    u = User(username=f"gv_{uuid4().hex[:8]}", password_hash="x", is_active=True)
    u.roles = [_role(db, r) for r in roles]
    db.add(u); db.flush()
    return u


def _task(db, lab, disease):
    enc = PatientEncounters(
        uuid=str(uuid4()), name="gv", patient_id=f"GV-{uuid4().hex[:6]}",
        capture_date="2024-01-01", lab_unit_id=lab.id, encounter_verified_status="pending",
    )
    db.add(enc); db.flush()
    task = GradingTask(patient_encounter_id=enc.id, disease_id=disease.id,
                       lab_unit_id=lab.id, state="pending")
    db.add(task); db.flush()
    return task


def _grading(db, disease):
    row = db.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
    if row is None:
        row = DiseaseGrading(disease_id=disease.id, impression="Normal",
                             display_order=1, is_active=True)
        db.add(row); db.flush()
    return row


def _grade(db, task, grading, *, grader, slot="resident"):
    g = Grade(task_id=task.id, grader_user_id=grader.id,
              role_slot=slot, disease_grading_id=grading.id)
    db.add(g); db.flush()
    return g


def _project_image_task(db, *, lab, hospital, camera, area, disease, project, uploader):
    image = DirectImageUpload(
        original_filename="project.jpg",
        filename="project.jpg",
        folder_rel="files/test_project_grading",
        file_hash=uuid4().hex,
        uploader_id=uploader.id,
        hospital_id=hospital.id,
        lab_unit_id=lab.id,
        project_id=project.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
    )
    db.add(image)
    db.flush()
    task = GradingTask(
        direct_image_upload_id=image.id,
        disease_id=disease.id,
        lab_unit_id=lab.id,
        state="pending",
    )
    db.add(task)
    db.flush()
    db.refresh(task)
    return task


@pytest.fixture
def world(db_session, core_test_data):
    db = db_session
    lab = db.merge(core_test_data["lab_unit"])
    disease = db.merge(core_test_data["dr"])

    me, peer, stranger = _user(db, "ophthalmologist"), _user(db, "ophthalmologist"), _user(db, "ophthalmologist")
    for user in (me, peer, stranger):
        user.lab_units.append(lab)
        db.add(
            UserDiseaseUnitRole(
                user_id=user.id,
                disease_id=disease.id,
                lab_unit_id=lab.id,
                can_grade_resident=True,
                can_grade_resident2=True,
                active=True,
            )
        )
    # AI grades are recorded against a dedicated model account, not a person.
    ai = _user(db)
    mine_task, other_task = _task(db, lab, disease), _task(db, lab, disease)

    grading = _grading(db, disease)
    grades = {
        "my_grade": _grade(db, mine_task, grading, grader=me, slot="resident"),
        "peer_on_my_task": _grade(db, mine_task, grading, grader=peer, slot="resident2"),
        "ai_on_my_task": _grade(db, mine_task, grading, grader=ai, slot="ai"),
        "peer_on_other_task": _grade(db, other_task, grading, grader=peer, slot="resident"),
        "ai_on_other_task": _grade(db, other_task, grading, grader=ai, slot="ai"),
    }
    return {"me": me, "peer": peer, "stranger": stranger, "grades": grades}


def _visible(db, user, world):
    context = access_context(db, user)
    query = select(Grade.id).join(GradingTask, Grade.task_id == GradingTask.id)
    ids = set(db.execute(scope_inter_rater_grades(query, context)).scalars())
    return {name for name, g in world["grades"].items() if g.id in ids}


def test_grader_sees_their_own_grade(db_session, world):
    assert "my_grade" in _visible(db_session, world["me"], world)


def test_grader_sees_the_second_readers_grade_on_their_own_task(db_session, world):
    """The point of the rule: comparing readings on the same task."""
    assert "peer_on_my_task" in _visible(db_session, world["me"], world)


def test_grader_sees_the_ai_grade_allocated_to_their_own_task(db_session, world):
    assert "ai_on_my_task" in _visible(db_session, world["me"], world)


def test_grader_does_not_see_grades_on_tasks_they_did_not_grade(db_session, world):
    visible = _visible(db_session, world["me"], world)
    assert "peer_on_other_task" not in visible


def test_grader_does_not_see_ai_grades_on_other_tasks(db_session, world):
    """AI grades follow participation too, not a blanket allowance."""
    assert "ai_on_other_task" not in _visible(db_session, world["me"], world)


def test_visibility_is_exactly_the_participated_task(db_session, world):
    assert _visible(db_session, world["me"], world) == {
        "my_grade", "peer_on_my_task", "ai_on_my_task",
    }


def test_a_grader_who_graded_nothing_sees_nothing(db_session, world):
    assert _visible(db_session, world["stranger"], world) == set()


def test_the_peer_sees_their_own_tasks_from_their_side(db_session, world):
    """Symmetry: the second reader sees the first reader's grade too."""
    visible = _visible(db_session, world["peer"], world)
    assert visible == {"peer_on_my_task", "my_grade", "ai_on_my_task",
                       "peer_on_other_task", "ai_on_other_task"}


def test_exact_cross_site_grading_role_is_sufficient_without_generic_lab_membership(db_session, world):
    world["me"].lab_units.clear()
    db_session.flush()
    assert _visible(db_session, world["me"], world) == {
        "my_grade", "peer_on_my_task", "ai_on_my_task",
    }


def test_admin_role_is_not_a_clinical_visibility_bypass(db_session, world):
    admin = _user(db_session, "admin")
    own_task = world["grades"]["my_grade"].task
    grading = world["grades"]["my_grade"].label
    world["grades"]["admin_grade"] = _grade(
        db_session, own_task, grading, grader=admin, slot="resident"
    )
    assert _visible(db_session, admin, world) == set()


@pytest.fixture
def project_world(db_session, core_test_data):
    db = db_session
    lab = db.merge(core_test_data["lab_unit"])
    hospital = db.merge(core_test_data["hospital"])
    camera = db.merge(core_test_data["camera"])
    area = db.merge(core_test_data["area"])
    disease = db.merge(core_test_data["dr"])
    other_disease = db.query(Disease).filter(Disease.id != disease.id).first()

    project = Project(
        title=f"Grade visibility project {uuid4().hex[:8]}",
        code=f"GV-P-{uuid4().hex[:8]}",
        active=True,
    )
    db.add(project)
    db.flush()
    boundary = ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True)
    db.add(boundary)

    me = _user(db, "field_ophthalmologist")
    peer = _user(db, "field_ophthalmologist")
    task = _project_image_task(
        db,
        lab=lab,
        hospital=hospital,
        camera=camera,
        area=area,
        disease=disease,
        project=project,
        uploader=me,
    )
    grading = _grading(db, disease)
    grades = {
        "my_grade": _grade(db, task, grading, grader=me, slot="resident"),
        "peer_on_my_task": _grade(db, task, grading, grader=peer, slot="resident2"),
    }
    allocation = ProjectGraderAllocation(
        project_id=project.id,
        user_id=me.id,
        lab_unit_id=lab.id,
        scope=AllocationScope.DISEASE_IMAGE.value,
        disease_id=disease.id,
        capacity="resident",
        active=True,
    )
    db.add(allocation)
    db.flush()
    return {
        "me": me,
        "project": project,
        "boundary": boundary,
        "allocation": allocation,
        "grades": grades,
        "disease": disease,
        "other_disease": other_disease,
    }


def test_project_grader_does_not_need_classical_slot(db_session, project_world):
    """Project grading is authorized by project allocation, not UserDiseaseUnitRole."""
    assert _visible(db_session, project_world["me"], project_world) == {
        "my_grade",
        "peer_on_my_task",
    }


def test_project_grader_with_inactive_allocation_is_denied(db_session, project_world):
    project_world["allocation"].active = False
    db_session.flush()
    assert _visible(db_session, project_world["me"], project_world) == set()


def test_project_grader_with_missing_allocation_is_denied(db_session, project_world):
    db_session.delete(project_world["allocation"])
    db_session.flush()
    assert _visible(db_session, project_world["me"], project_world) == set()


def test_project_grader_with_wrong_allocation_target_is_denied(db_session, project_world):
    project_world["allocation"].disease_id = project_world["other_disease"].id
    db_session.flush()
    assert _visible(db_session, project_world["me"], project_world) == set()


def test_project_grader_without_active_project_lab_unit_is_denied(db_session, project_world):
    project_world["boundary"].active = False
    db_session.flush()
    assert _visible(db_session, project_world["me"], project_world) == set()


@pytest.mark.parametrize("role", ["project_admin", "admin"])
def test_project_or_admin_role_alone_is_not_clinical_visibility(db_session, project_world, role):
    user = _user(db_session, role)
    project_world["grades"]["unauthorized_grade"] = _grade(
        db_session,
        project_world["grades"]["my_grade"].task,
        project_world["grades"]["my_grade"].label,
        grader=user,
    )
    assert _visible(db_session, user, project_world) == set()
