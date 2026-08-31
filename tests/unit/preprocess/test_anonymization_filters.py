"""Tests for fail-closed preprocess dashboard ID filters."""

import pytest
from flask import Flask

from preprocess.anonymize_image import _parse_optional_positive_int_filter


@pytest.mark.parametrize("raw", ["", "0", "-1", "abc", "1.5"])
def test_supplied_invalid_filter_id_is_not_treated_as_missing(raw):
    app = Flask(__name__)
    with app.test_request_context(f"/preprocess/dashboard?camera_id={raw}"):
        with pytest.raises(ValueError, match="invalid_camera_id"):
            _parse_optional_positive_int_filter("camera_id")


def test_absent_filter_is_none():
    app = Flask(__name__)
    with app.test_request_context("/preprocess/dashboard"):
        assert _parse_optional_positive_int_filter("camera_id") is None


def test_positive_filter_id_is_preserved():
    app = Flask(__name__)
    with app.test_request_context("/preprocess/dashboard?camera_id=12"):
        assert _parse_optional_positive_int_filter("camera_id") == 12


@pytest.mark.parametrize(
    "filter_name",
    [
        "hospital_id",
        "lab_unit_id",
        "camera_id",
        "disease_id",
        "area_id",
        "verified_by_id",
    ],
)
def test_dashboard_rejects_malformed_scoping_filter(
    auth_client, hosp_a_data_manager, filter_name
):
    client = auth_client(hosp_a_data_manager)
    response = client.get(f"/preprocess/dashboard?{filter_name}=not-an-id")

    assert response.status_code in {302, 303, 400}
    if response.status_code in {302, 303}:
        assert "dashboard" in response.headers["Location"]


@pytest.mark.parametrize(
    "filter_name",
    [
        "hospital_id",
        "lab_unit_id",
        "camera_id",
        "disease_id",
        "area_id",
        "verified_by_id",
    ],
)
def test_dashboard_rejects_scoping_id_outside_authorized_set(
    auth_client, hosp_a_data_manager, filter_name
):
    client = auth_client(hosp_a_data_manager)
    response = client.get(f"/preprocess/dashboard?{filter_name}=2147483647")

    assert response.status_code in {302, 303, 400}
    if response.status_code in {302, 303}:
        assert "dashboard" in response.headers["Location"]
