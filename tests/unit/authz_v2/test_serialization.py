from authz_v2.core.catalogue import CATALOGUE
from authz_v2.core.decisions import DecisionDTO
from authz_v2.domain.descriptions import describe_catalogue
from authz_v2.serialization.api import serialize_dto
from authz_v2.serialization.catalogue import (
    catalogue_html,
    catalogue_markdown,
    role_action_matrix,
)


def test_api_serializer_exposes_dto_fields_but_rejects_arbitrary_objects():
    assert serialize_dto(DecisionDTO(True, "public.view")) == {
        "allowed": True,
        "action": "public.view",
        "reason_code": "allowed",
        "policy_path": None,
        "evidence": [],
    }
    try:
        serialize_dto(object())
    except TypeError as error:
        assert "unsupported authorization API value" in str(error)
    else:
        raise AssertionError("arbitrary object was serialized")


def test_catalogue_renderers_are_complete_and_deterministic():
    catalogue = describe_catalogue()
    markdown = catalogue_markdown(catalogue)
    html = catalogue_html(catalogue)
    matrix = role_action_matrix(catalogue)
    assert len(catalogue.actions) == len(CATALOGUE)
    assert len(matrix) == len(CATALOGUE) + 1
    assert "`grading.resident.submit`" in markdown
    assert "ScopedRoleRequirement" in markdown
    assert "grading.resident.submit" in html
