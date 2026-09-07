"""Regression coverage for just-in-time discrepancy-review navigation."""

from review.route_discrepancy_review import discrepancy_review


def test_discrepancy_review_route_is_not_response_cached():
    """Review listing responses must not outlive their MV snapshot."""
    assert not hasattr(discrepancy_review, "uncached")


def test_discrepancy_review_lists_classical_adjudicators(
    auth_client_factory, db_session, core_test_data, monkeypatch
):
    from types import SimpleNamespace
    from uuid import uuid4
    from flask import jsonify
    from tests.helpers.factories import UserFactory
    import review.route_discrepancy_review as route

    lab = db_session.merge(core_test_data["lab_unit"])
    admin = UserFactory.create_admin(db_session, username=f"review_admin_{uuid4().hex[:8]}")
    adjudicator = UserFactory.create_by_role(
        db_session, "regrade_adjudicator",
        username=f"review_adjudicator_{uuid4().hex[:8]}", lab_units=[lab],
    )
    inactive = UserFactory.create_by_role(
        db_session, "regrade_adjudicator",
        username=f"inactive_adjudicator_{uuid4().hex[:8]}", lab_units=[lab],
    )
    inactive.is_active = False
    db_session.flush()
    monkeypatch.setattr(route, "_review_lab_unit_ids", lambda db: {lab.id})
    monkeypatch.setattr(route, "list_discrepancy_filter_options", lambda *args, **kwargs:
                        SimpleNamespace(projects=[], diseases=[], lab_units=[lab]))
    monkeypatch.setattr(route, "render_template", lambda template, **context:
                        jsonify(adjudicators=[user.id for user in context["regrade_adjudicators"]]))
    client = auth_client_factory(admin)
    response = client.get("/review/discrepancy-review", follow_redirects=True)
    assert response.status_code == 200
    assert adjudicator.id in response.json["adjudicators"]
    assert inactive.id not in response.json["adjudicators"]
