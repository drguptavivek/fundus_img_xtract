"""The WAI statistics scope clause must compile to valid, restrictive SQL.

The clause is spliced into raw SQL from the authz predicate compiler, so a
change to either side can produce SQL that does not parse. These execute it.
"""

from uuid import uuid4

import pytest

from models import Role, User
from services.wai_api_statistics import (
    ACTION_WAI_ROWS,
    WaiStatsFilters,
    get_encounter_results,
    get_image_results,
    get_summary,
    _scope_clause,
)
from tests.helpers.factories import UserFactory


def _user(db, *roles, hospital=None):
    user = User(username=f"wai_{uuid4().hex[:8]}", password_hash="x", is_active=True,
                hospital_id=hospital.id if hospital else None)
    roles_out = []
    for name in roles:
        role = db.query(Role).filter_by(name=name).one_or_none()
        if role is None:
            role = Role(name=name); db.add(role); db.flush()
        roles_out.append(role)
    user.roles = roles_out
    db.add(user); db.flush()
    return user


def test_scope_clause_executes_for_a_scoped_user(db_session, core_test_data):
    """A user with no relationships gets a restrictive clause that still runs."""
    user = _user(db_session, "data_manager", hospital=db_session.merge(core_test_data["hospital"]))
    payload = get_summary(db_session, user, WaiStatsFilters())
    assert isinstance(payload, dict)


def test_row_endpoints_execute_for_a_scoped_user(db_session, core_test_data):
    user = _user(db_session, "verifier", hospital=db_session.merge(core_test_data["hospital"]))
    images = get_image_results(db_session, user, WaiStatsFilters(), page=1, page_size=25)
    encounters = get_encounter_results(db_session, user, WaiStatsFilters(), page=1, page_size=25)
    assert images["rows"] == []
    assert encounters["rows"] == []


def test_admin_is_unrestricted(db_session):
    admin = UserFactory.create_admin(db_session, username=f"wai_admin_{uuid4().hex[:6]}")
    assert _scope_clause(db_session, admin, {}, ACTION_WAI_ROWS) == []


def test_a_user_with_no_lab_units_gets_a_restricting_clause(db_session, core_test_data):
    """The old rule fell back to `hospital_id = X`, i.e. the whole hospital."""
    user = _user(db_session, "data_manager", hospital=db_session.merge(core_test_data["hospital"]))
    clauses = _scope_clause(db_session, user, {}, ACTION_WAI_ROWS)
    assert clauses, "a non-admin must always be restricted"
    joined = " ".join(clauses)
    assert "inference_row_key IN" in joined
    # The specific regression: no bare hospital-wide escape hatch.
    assert "hospital_id = :scope_hospital_id" not in joined
