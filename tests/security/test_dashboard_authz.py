"""AUTHZ-01: /dashboard/* must authorize and scope, including on export.

Before this, the three dashboard routes carried no authorization decorators at
all. The application-wide guard establishes authentication only, so any active
account could read facility and image data for every hospital and export it.

These tests pin both halves of the fix: the action gate decides whether the
dashboard may be opened, and the scope decides what it may contain. The export
assertion matters most - a filtered page with an unfiltered export is the same
leak wearing a different hat.

See docs/audit/AUTHZ_SURFACE_ROUTE_AUDIT_2026-08-25.md.
"""

from uuid import uuid4

import pytest

from tests.helpers.factories import ImageFactory, UserFactory


DASHBOARD_ROUTES = ("/dashboard/", "/dashboard/images")


def _authenticate(client, user):
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)
        session["_fresh"] = True


def _image_in(db_session, lab_unit, *, filename):
    image = ImageFactory.create_direct_upload(
        db_session,
        hospital_id=lab_unit.hospital_id,
        lab_unit_id=lab_unit.id,
        filename=filename,
    )
    db_session.flush()
    return image


@pytest.mark.security
def test_dashboard_denies_account_with_no_lab_scope(client, db_session, core_test_data):
    """An empty scope must mean no access, never an unfiltered view."""
    user = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"authz01_noscope_{uuid4().hex[:8]}",
        lab_units=[],
    )
    db_session.flush()
    _authenticate(client, user)

    for route in DASHBOARD_ROUTES:
        assert client.get(route).status_code == 403, route


@pytest.mark.security
def test_dashboard_hides_hospitals_outside_the_callers_scope(
    client, db_session, core_test_data
):
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    hospital_b = db_session.merge(core_test_data["hospital_b"])
    lab_a1 = db_session.merge(core_test_data["lab_a1"])

    user = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"authz01_scoped_{uuid4().hex[:8]}",
        lab_units=[lab_a1],
    )
    db_session.flush()
    _authenticate(client, user)

    body = client.get("/dashboard/").get_data(as_text=True)
    assert hospital_a.name in body
    assert hospital_b.name not in body


@pytest.mark.security
def test_dashboard_hospital_detail_is_non_disclosing_across_hospitals(
    client, db_session, core_test_data
):
    """An out-of-scope hospital must be indistinguishable from a missing one."""
    hospital_b = db_session.merge(core_test_data["hospital_b"])
    lab_a1 = db_session.merge(core_test_data["lab_a1"])

    user = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"authz01_detail_{uuid4().hex[:8]}",
        lab_units=[lab_a1],
    )
    db_session.flush()
    _authenticate(client, user)

    in_scope = client.get(f"/dashboard/hospital/{lab_a1.hospital_id}")
    out_of_scope = client.get(f"/dashboard/hospital/{hospital_b.id}")
    missing = client.get("/dashboard/hospital/98765432")

    assert in_scope.status_code == 200
    assert out_of_scope.status_code == 404
    assert out_of_scope.status_code == missing.status_code
    assert hospital_b.name not in out_of_scope.get_data(as_text=True)


@pytest.mark.security
@pytest.mark.parametrize("export_format", ["csv", "excel"])
def test_dashboard_image_export_cannot_widen_the_page_selection(
    client, db_session, core_test_data, export_format
):
    """Export must reuse the page's filtered query, not a fresh unfiltered one."""
    lab_a1 = db_session.merge(core_test_data["lab_a1"])
    lab_b1 = db_session.merge(core_test_data["lab_b1"])

    mine = _image_in(db_session, lab_a1, filename="authz01_in_scope.jpg")
    theirs = _image_in(db_session, lab_b1, filename="authz01_out_of_scope.jpg")

    user = UserFactory.create_by_role(
        db_session,
        "ophthalmologist",
        username=f"authz01_export_{uuid4().hex[:8]}",
        lab_units=[lab_a1],
    )
    db_session.flush()
    _authenticate(client, user)

    response = client.get(f"/dashboard/images?export={export_format}")
    assert response.status_code == 200

    if export_format == "csv":
        exported = response.get_data(as_text=True)
    else:
        # xlsx is a zip archive, so the UUIDs have to be read out of the sheet
        # rather than matched against the raw bytes.
        import io

        import pandas as pd

        exported = pd.read_excel(io.BytesIO(response.get_data())).to_csv(index=False)

    assert mine.uuid in exported
    assert theirs.uuid not in exported


@pytest.mark.security
def test_dashboard_still_shows_every_hospital_to_an_admin(
    client, db_session, core_test_data
):
    """Scoping must not cost admins their existing cross-hospital view.

    The engine grants ADMIN_GLOBAL, which matches every lab unit, so an admin's
    scope is the whole estate. This is the regression that would matter most if
    the per-lab authorization were wrong in the restrictive direction.
    """
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    hospital_b = db_session.merge(core_test_data["hospital_b"])

    admin = UserFactory.create_admin(
        db_session, username=f"authz01_admin_{uuid4().hex[:8]}"
    )
    db_session.flush()
    _authenticate(client, admin)

    response = client.get("/dashboard/")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert hospital_a.name in body
    assert hospital_b.name in body

    assert client.get(f"/dashboard/hospital/{hospital_b.id}").status_code == 200
