"""What a grader may read of the grades on a task.

A grader reads their own grades, and every other grade on a task they have
graded - the second reader's, the arbitrator's, and the AI grade allocated
to that task - so they can see how their reading compared. That visibility
is bounded by participation: grades on tasks they did not grade, including
AI grades, stay out of reach.
"""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from authz.predicates import scope_grades
from authz.resolver import resolve_grants
from models import DiseaseGrading, Grade, GradingTask, PatientEncounters, Role, User


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


@pytest.fixture
def world(db_session, core_test_data):
    db = db_session
    lab = db.merge(core_test_data["lab_unit"])
    disease = db.merge(core_test_data["dr"])

    me, peer, stranger = _user(db, "ophthalmologist"), _user(db, "ophthalmologist"), _user(db, "ophthalmologist")
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
    return dict(me=me, peer=peer, stranger=stranger, grades=grades)


def _visible(db, user, world):
    resolved = resolve_grants(db, user)
    ids = set(db.execute(scope_grades(select(Grade.id), resolved)).scalars())
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
