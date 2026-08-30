from types import SimpleNamespace

from screenings.access import (
    apply_screening_scope,
    authorized_screening_lab_unit_ids,
    screening_is_authorized,
)
from tests.helpers.test_factories import TestDataFactory


def _encounter(*, project_id=None, lab_unit_id=11):
    return SimpleNamespace(project_id=project_id, lab_unit_id=lab_unit_id)


def test_screening_authorization_requires_classical_exact_lab_unit():
    encounter = _encounter()

    assert screening_is_authorized(
        encounter,
        is_admin=False,
        allowed_lab_unit_ids={11},
    )
    assert not screening_is_authorized(
        encounter,
        is_admin=False,
        allowed_lab_unit_ids={12},
    )


def test_screening_authorization_rejects_project_and_null_lineage():
    assert not screening_is_authorized(
        _encounter(project_id=7),
        is_admin=False,
        allowed_lab_unit_ids={11},
    )
    assert not screening_is_authorized(
        _encounter(lab_unit_id=None),
        is_admin=False,
        allowed_lab_unit_ids={11},
    )
    assert not screening_is_authorized(
        _encounter(),
        is_admin=False,
        allowed_lab_unit_ids=set(),
    )


def test_admin_is_explicit_break_glass_for_any_persisted_record():
    assert screening_is_authorized(
        _encounter(project_id=7, lab_unit_id=None),
        is_admin=True,
        allowed_lab_unit_ids=set(),
    )


def test_sql_scope_filters_project_rows_and_empty_lineage():
    class Query:
        def __init__(self):
            self.criteria = ()

        def filter(self, *criteria):
            self.criteria += criteria
            return self

    query = apply_screening_scope(
        Query(),
        is_admin=False,
        allowed_lab_unit_ids={11},
    )
    assert len(query.criteria) == 3
    assert "project_id" in str(query.criteria[0])
    assert "lab_unit_id" in str(query.criteria[1])
    assert "lab_unit_id" in str(query.criteria[2])

    empty = apply_screening_scope(
        Query(),
        is_admin=False,
        allowed_lab_unit_ids=set(),
    )
    assert len(empty.criteria) == 1
    assert "false" in str(empty.criteria[0]).lower()


def test_legacy_screenings_routes_exclude_project_encounters(
    auth_client, hospital_data, hosp_a_data_manager, db_session
):
    """A classical Lab Unit assignment cannot reach a project encounter."""
    from models import Project

    project = Project(
        title="Screenings boundary project",
        code="SCREENINGS_BOUNDARY_PROJECT",
        active=True,
    )
    db_session.add(project)
    db_session.flush()
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
        patient_id="PROJECT_SCREENING_MUST_NOT_LEAK",
    )
    encounter.project_id = project.id
    db_session.flush()

    client = auth_client(db_session.merge(hosp_a_data_manager))

    listing = client.get("/screenings/", follow_redirects=True)
    assert listing.status_code == 200
    assert b"PROJECT_SCREENING_MUST_NOT_LEAK" not in listing.data

    for path in (
        f"/screenings/{encounter.id}",
        f"/screenings/reprocess_pdf/{encounter.id}",
        f"/screenings/delete/{encounter.id}",
        f"/screenings/delete_reports/{encounter.id}",
    ):
        response = client.post(path) if "delete" in path or "reprocess" in path else client.get(path)
        assert response.status_code == 403, path


def test_classical_data_manager_reaches_every_lab_in_own_hospital(
    hospital_data, hosp_a_data_manager, db_session
):
    manager = db_session.merge(hosp_a_data_manager)
    expected = {
        lab.id for lab in hospital_data["hospital_a"]["lab_units"]
    }

    assert expected
    authorized = authorized_screening_lab_unit_ids(db_session, manager)
    assert expected.issubset(authorized)
    other_hospital_labs = {
        lab.id for lab in hospital_data["hospital_b"]["lab_units"]
    }
    assert authorized.isdisjoint(other_hospital_labs)
