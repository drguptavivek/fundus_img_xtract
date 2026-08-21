"""Which IITK sessions still owe us images, and how a retry reaches them."""
from datetime import timedelta

import pytest

from auth.utils import utcnow
from iitk_api_integration.models import IITKApiSessionLink
from iitk_api_integration.service import (
    RESYNC_MAX_LOOKBACK_DAYS,
    inventory_image_count,
    session_is_incomplete,
)


def _link(**kwargs):
    defaults = dict(
        config_id=1,
        source_session_id="s1",
        patient_encounter_id=1,
        source_status="complete",
        source_image_count=11,
        local_image_count=10,
        source_metadata_json={
            "upstream_image_inventory_payload": {
                "images": [{"position": p} for p in (
                    "primary", "up", "up_right", "right", "down_right",
                    "down", "down_left", "left", "up_left", "composite",
                )]
            }
        },
    )
    defaults.update(kwargs)
    return IITKApiSessionLink(**defaults)


def test_a_fully_synced_session_is_not_incomplete_despite_a_higher_source_count():
    """source_image_count counts `consent`, which /listImages never returns.

    Comparing against it reports nearly every complete session as short by one,
    which is what made the old signal useless.
    """
    link = _link(source_image_count=11, local_image_count=10)

    assert inventory_image_count(link) == 10
    assert session_is_incomplete(link) is False


def test_a_session_missing_an_inventory_image_is_incomplete():
    link = _link(local_image_count=8)
    assert session_is_incomplete(link) is True


def test_an_upstream_partial_session_is_incomplete():
    link = _link(source_status="partial", local_image_count=10)
    assert session_is_incomplete(link) is True


def test_a_session_without_an_inventory_snapshot_is_not_guessed_incomplete():
    link = _link(source_metadata_json={})
    assert inventory_image_count(link) is None
    assert session_is_incomplete(link) is False


def test_the_resync_lookback_is_capped():
    """A permanently-partial session must not force a rescan back to day one."""
    assert RESYNC_MAX_LOOKBACK_DAYS == 14
