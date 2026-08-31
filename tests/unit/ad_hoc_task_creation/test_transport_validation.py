from __future__ import annotations

import pytest

from ad_hoc_task_creation import AdHocTaskCreationError
from tasks.ad_hoc import _int_or_none, _source


@pytest.mark.parametrize("value", ["abc", "1.2", -1, 0, True, 2.5])
def test_supplied_malformed_filter_id_is_rejected(value):
    with pytest.raises(AdHocTaskCreationError, match="positive integer"):
        _int_or_none(value, "lab_unit_id")


@pytest.mark.parametrize("value", ["project", 1, False, []])
def test_unknown_or_non_string_source_is_rejected(value):
    with pytest.raises(AdHocTaskCreationError, match="all, direct, or zip"):
        _source(value)


def test_omitted_filter_values_remain_omitted():
    assert _int_or_none(None, "lab_unit_id") is None
    assert _int_or_none("", "lab_unit_id") is None
    assert _source(None) == "all"


@pytest.mark.parametrize("value", [True, False, 1.9, "1.9", 0, -1])
def test_preview_max_images_uses_strict_positive_integer_contract(value):
    with pytest.raises(AdHocTaskCreationError, match="positive integer"):
        _int_or_none(value, "max_images")
