"""Project-only image graders must discover their assigned image queues."""

from uuid import uuid4

import pytest
from flask import render_template

from grading.queue_cards import disease_queue_card, gradable_disease_cards
from grading_allocation.models import ProjectGraderAllocation
from models import UserDiseaseUnitRole
from project_configuration.models import ProjectLabUnit
from tests.helpers.factories import UserFactory
from tests.unit.grading_allocation.test_allocation_domain import (
    _direct_task,
    _project_with_image_target,
)


@pytest.mark.parametrize("capacity,state,count_key", [
    ("resident", "pending", "resident_pending"),
    ("resident", "resident_done", "resident2_pending"),
    ("arbitrator", "arbitration", "arbitration_pending"),
])
def test_project_only_image_queue_discovery_and_revocation(
    app, db_session, core_test_data, capacity, state, count_key
):
    db = db_session
    disease = db.merge(core_test_data["dr"])
    lab = db.merge(core_test_data["lab_unit"])
    user = UserFactory.create_by_role(
        db, "ophthalmologist", username=f"image_grader_{uuid4().hex[:8]}", lab_units=[lab]
    )
    db.query(UserDiseaseUnitRole).filter_by(user_id=user.id).delete()
    project, _ = _project_with_image_target(db, disease)
    other_project, _ = _project_with_image_target(db, disease)
    for owner in (project, other_project, None):
        task = _direct_task(db, core_test_data, user, disease, project=owner)
        task.state = state
    allocation = ProjectGraderAllocation(
        project_id=project.id, user_id=user.id, lab_unit_id=lab.id,
        scope="disease_image", disease_id=disease.id, capacity=capacity, active=True,
    )
    db.add(allocation)
    db.flush()

    cards = gradable_disease_cards(db, user_id=user.id)
    assert [card["id"] for card in cards] == [disease.id]
    assert cards[0]["can_grade_resident"] == (capacity == "resident")
    assert cards[0]["can_grade_resident2"] == (capacity == "resident")
    assert cards[0]["can_arbitrate"] == (capacity == "arbitrator")
    card = disease_queue_card(db, user_id=user.id, disease_id=disease.id)
    assert card[count_key] == 1
    with app.test_request_context():
        html = render_template("grading/_disease_queue_card.html", card=card)
    assert ("Start Grading (1 pending)" if capacity == "resident" else "Start Arbitration (1 pending)") in html

    allocation.active = False
    db.flush()
    assert gradable_disease_cards(db, user_id=user.id) == []
    allocation.active = True
    project.active = False
    db.flush()
    assert gradable_disease_cards(db, user_id=user.id) == []
    project.active = True
    project_lab = db.query(ProjectLabUnit).filter_by(project_id=project.id, lab_unit_id=lab.id).one()
    project_lab.active = False
    db.flush()
    assert gradable_disease_cards(db, user_id=user.id) == []
