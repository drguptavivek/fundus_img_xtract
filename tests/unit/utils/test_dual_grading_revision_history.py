from datetime import datetime, timedelta, timezone

from utils.dualGradingRevisionUtils import (
    REVISION_WINDOW_HOURS,
    check_revision_eligibility_by_task_state,
)


def test_revision_window_is_twelve_hours():
    assert REVISION_WINDOW_HOURS == 12


def test_recent_resident_grade_is_revisable():
    created_at = datetime.now(timezone.utc) - timedelta(hours=1)

    can_revise, message = check_revision_eligibility_by_task_state(
        "resident_done",
        "resident",
        created_at,
    )

    assert can_revise is True
    assert message == f"Eligible for revision (submitted within {REVISION_WINDOW_HOURS} hours)"


def test_recent_final_resident2_grade_is_revisable():
    created_at = datetime.now(timezone.utc) - timedelta(hours=2)

    can_revise, _ = check_revision_eligibility_by_task_state(
        "final",
        "resident2",
        created_at,
    )

    assert can_revise is True


def test_old_final_arbitrator_grade_is_not_revisable():
    created_at = datetime.now(timezone.utc) - timedelta(hours=REVISION_WINDOW_HOURS + 1)

    can_revise, message = check_revision_eligibility_by_task_state(
        "final",
        "arbitrator",
        created_at,
    )

    assert can_revise is False
    assert message == f"Cannot revise after {REVISION_WINDOW_HOURS} hours have passed."


def test_revision_closes_at_twelve_hour_boundary():
    created_at = datetime.now(timezone.utc) - timedelta(
        hours=REVISION_WINDOW_HOURS
    )

    can_revise, _ = check_revision_eligibility_by_task_state(
        "resident_done",
        "resident",
        created_at,
    )

    assert can_revise is False
