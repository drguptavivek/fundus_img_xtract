from __future__ import annotations

from unittest.mock import patch

import pytest

from models import Job


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


@pytest.fixture
def null_lab_jobs(db_session, hosp_a_data_manager, hosp_b_data_manager):
    owner_id = db_session.merge(hosp_a_data_manager).id
    other_id = db_session.merge(hosp_b_data_manager).id
    owned = Job(
        token="owned-null-lab-job",
        status="queued",
        upload_type="processing",
        uploader_user_id=owner_id,
        lab_unit_id=None,
    )
    hidden = Job(
        token="hidden-null-lab-job",
        status="queued",
        upload_type="secret-processing-type",
        uploader_user_id=other_id,
        lab_unit_id=None,
    )
    db_session.add_all([owned, hidden])
    db_session.commit()
    return owner_id, other_id, owned.token, hidden.token


def test_null_lab_nonowner_cannot_read_any_generic_token_surface(
    client, null_lab_jobs
):
    owner_id, _, _, hidden_token = null_lab_jobs
    _login(client, owner_id)

    assert client.get(f"/jobs/{hidden_token}").status_code == 404
    assert client.get(f"/jobs/{hidden_token}/view").status_code == 404
    assert client.get(f"/jobs/processing/{hidden_token}").status_code == 404
    assert client.get(f"/api/direct/upload/status/{hidden_token}").status_code == 404


def test_owner_can_read_null_lab_job(client, null_lab_jobs):
    owner_id, _, owned_token, _ = null_lab_jobs
    _login(client, owner_id)

    assert client.get(f"/jobs/{owned_token}").status_code == 200
    assert client.get(f"/api/direct/upload/status/{owned_token}").status_code == 200
    with patch("jobs.routes.render_template", return_value="OK"):
        assert client.get(f"/jobs/{owned_token}/view").status_code == 200
        assert client.get(f"/jobs/processing/{owned_token}").status_code == 200


def test_job_list_and_type_choices_do_not_leak_hidden_null_lab_job(
    client, null_lab_jobs
):
    owner_id, _, owned_token, hidden_token = null_lab_jobs
    _login(client, owner_id)

    with patch("jobs.routes.render_template", return_value="OK") as render:
        response = client.get("/jobs/")

    assert response.status_code == 200
    context = render.call_args.kwargs
    assert {job.token for job in context["jobs"]} >= {owned_token}
    assert hidden_token not in {job.token for job in context["jobs"]}
    assert "secret-processing-type" not in context["job_types"]
