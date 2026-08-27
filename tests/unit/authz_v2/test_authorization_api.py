from __future__ import annotations

import pytest

from api.authorization import _parse_grant_create, _parse_grant_update
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.grants import DESCRIPTION_UNSET


def test_grant_create_parser_accepts_only_stable_enum_and_id_fields():
    command = _parse_grant_create(
        {
            "user_id": 9,
            "role": "analytics_viewer",
            "scope_type": "lab_unit",
            "scope_id": 4,
            "description": "approved",
        }
    )
    assert command.user_id == 9
    assert command.role is Role.ANALYTICS_VIEWER
    assert command.scope.scope_type is ScopeType.LAB_UNIT
    assert command.scope.scope_id == 4

    with pytest.raises(ValueError):
        _parse_grant_create(
            {
                "user_id": 9,
                "role": "analytics_viewer",
                "scope_type": "lab_unit",
                "scope_id": 4,
                "hospital_id": 999,
            }
        )


def test_grant_update_parser_distinguishes_clear_from_omitted_description():
    active_only = _parse_grant_update({"active": False})
    assert active_only.description is DESCRIPTION_UNSET
    assert active_only.active is False

    clear = _parse_grant_update({"description": None})
    assert clear.description is None
    assert clear.active is None

    with pytest.raises(ValueError):
        _parse_grant_update({"active": "false"})
