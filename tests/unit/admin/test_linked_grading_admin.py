from sqlalchemy import select

from models import Disease, LinkedDiseaseGrading
from tests.conftest import create_authenticated_client
from tests.helpers.factories import CoreEntityFactory, UserFactory


def _create_disease(db_session, name):
    return CoreEntityFactory.create_disease(db_session, name=name)


def test_admin_can_create_linked_grading(app, db_session):
    primary = _create_disease(db_session, "Primary Disease A")
    linked = _create_disease(db_session, "Linked Disease A")
    admin_user = UserFactory.create_admin(db_session, username="linked_admin_a")

    client = create_authenticated_client(app, admin_user, db_session)

    response = client.post(
        "/admin/linked-disease-gradings",
        data={
            "primary_disease_id": str(primary.id),
            "linked_disease_id": str(linked.id),
            "display_order": "2",
            "is_active": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    link = db_session.execute(
        select(LinkedDiseaseGrading)
        .where(LinkedDiseaseGrading.primary_disease_id == primary.id)
        .where(LinkedDiseaseGrading.linked_disease_id == linked.id)
    ).scalar_one_or_none()
    assert link is not None
    assert link.display_order == 2
    assert link.is_active is True


def test_admin_requires_delink_before_relink(app, db_session):
    primary = _create_disease(db_session, "Primary Disease B")
    linked = _create_disease(db_session, "Linked Disease B")
    other_primary = _create_disease(db_session, "Primary Disease C")
    admin_user = UserFactory.create_admin(db_session, username="linked_admin_b")

    db_session.add(
        LinkedDiseaseGrading(
            primary_disease_id=primary.id,
            linked_disease_id=linked.id,
            display_order=1,
            is_active=True,
        )
    )
    db_session.flush()

    client = create_authenticated_client(app, admin_user, db_session)
    response = client.post(
        "/admin/linked-disease-gradings",
        data={
            "primary_disease_id": str(other_primary.id),
            "linked_disease_id": str(linked.id),
            "display_order": "0",
            "is_active": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Delink first" in response.data

    links = db_session.execute(
        select(LinkedDiseaseGrading).where(LinkedDiseaseGrading.linked_disease_id == linked.id)
    ).scalars().all()
    assert len(links) == 1
    assert links[0].primary_disease_id == primary.id


def test_admin_can_update_and_delete_link(app, db_session):
    primary = _create_disease(db_session, "Primary Disease D")
    linked = _create_disease(db_session, "Linked Disease D")
    admin_user = UserFactory.create_admin(db_session, username="linked_admin_c")

    link = LinkedDiseaseGrading(
        primary_disease_id=primary.id,
        linked_disease_id=linked.id,
        display_order=1,
        is_active=True,
    )
    db_session.add(link)
    db_session.flush()

    client = create_authenticated_client(app, admin_user, db_session)

    update_response = client.post(
        f"/admin/linked-disease-gradings/{link.id}/edit",
        data={
            "primary_disease_id": str(primary.id),
            "linked_disease_id": str(linked.id),
            "display_order": "5",
            "is_active": "0",
        },
        follow_redirects=True,
    )
    assert update_response.status_code == 200

    updated = db_session.get(LinkedDiseaseGrading, link.id)
    assert updated.display_order == 5
    assert updated.is_active is False

    delete_response = client.post(
        f"/admin/linked-disease-gradings/{link.id}/delete",
        follow_redirects=True,
    )
    assert delete_response.status_code == 200

    deleted = db_session.get(LinkedDiseaseGrading, link.id)
    assert deleted is None
