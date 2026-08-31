import pytest
from werkzeug.exceptions import BadRequest

from api.analytics_exports import _filters_from_request


@pytest.mark.parametrize(
    "query",
    [
        "hospital_id=x",
        "hospital_id=",
        "lab_unit_id=0",
        "lab_unit_id=x",
        "project_id=x",
        "project_id=1&project_id=x",
        "include_classical=true",
        "include_classical=",
    ],
)
def test_explicit_invalid_scope_filter_is_rejected(app, query):
    with app.test_request_context(f"/?{query}"):
        with pytest.raises(BadRequest):
            _filters_from_request()


def test_valid_scope_filters_are_preserved(app):
    with app.test_request_context(
        "/?hospital_id=2&lab_unit_id=3&project_id=4&project_id=5&include_classical=0"
    ):
        filters = _filters_from_request()

    assert filters.hospital_id == 2
    assert filters.lab_unit_id == 3
    assert filters.project_ids == (4, 5)
    assert filters.include_classical is False
