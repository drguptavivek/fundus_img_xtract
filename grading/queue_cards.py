"""Disease queue cards for the grading dashboard.

The dashboard used to compute every disease's pending totals before it could
render anything, which meant the page blocked on a full sweep of the pending
queue. These helpers split that into two questions the page can ask
separately:

* ``gradable_disease_cards`` - which cards exist. Derived from role rows only,
  so it stays cheap as the task table grows.
* ``disease_queue_card`` - what is inside one card. Paid per disease, after the
  page has already painted, and concurrently across diseases.

Both the JSON API in ``api.grading_dashboard`` and the HTMX fragment route in
``grading.dashboard`` render from these, so the two surfaces cannot drift.
"""

from __future__ import annotations

from typing import Any

from utils.dualGradingKPIs import (
    get_user_gradable_diseases,
    get_user_kpi_linked_followup_counts,
    get_user_kpi_pending_task_count_data,
)

# Project-allocated EncounterSet packages are presented in their own dashboard
# panel, so every count here excludes them to avoid showing the same work twice.
EXCLUDE_PROJECT_ENCOUNTER_SETS = True

def gradable_disease_cards(db, *, user_id: int) -> list[dict[str, Any]]:
    """The disease cards this grader should see, uncounted."""
    return get_user_gradable_diseases(db, user_id)


def grader_queue_overview(db, *, user_id: int) -> dict[str, Any]:
    """Both dashboard queue panels in one payload.

    ``project_encounter_sets`` arrives complete with its counts because those
    are cheap to derive. ``legacy_diseases`` deliberately carries no counts:
    each disease is counted on demand through ``disease_queue_card`` so one
    large queue cannot hold up the rest of the dashboard.
    """
    return {
        "project_encounter_sets": project_encounter_set_cards(db, user_id=user_id),
        "legacy_diseases": get_user_gradable_diseases(db, user_id),
    }


def disease_queue_card(
    db,
    *,
    user_id: int,
    disease_id: int,
    refresh: bool = False,
) -> dict[str, Any] | None:
    """Pending totals and linked follow-ups for a single disease.

    Returns ``None`` when the user holds no active eligibility for the disease,
    which the callers turn into a 404 rather than an empty card.

    ``refresh`` remains a transport hint for existing HTMX callers; all
    eligibility and counts are evaluated live.
    """
    _ = refresh

    diseases = get_user_gradable_diseases(db, user_id)
    disease = next((row for row in diseases if row["id"] == disease_id), None)
    if disease is None:
        return None

    pending = get_user_kpi_pending_task_count_data(
        db,
        user_id,
        exclude_project_encounter_sets=EXCLUDE_PROJECT_ENCOUNTER_SETS,
        disease_ids={disease_id},
    ).get(disease["name"], {})

    linked_followups = get_user_kpi_linked_followup_counts(
        db,
        user_id,
        exclude_project_encounter_sets=EXCLUDE_PROJECT_ENCOUNTER_SETS,
        disease_ids={disease_id},
    ).get(disease["name"], [])

    resident_pending = int(pending.get("resident_pending", 0))
    resident2_pending = int(pending.get("resident2_pending", 0))
    arbitration_pending = int(pending.get("arbitration_pending", 0))
    linked_total = sum(int(item.get("count", 0)) for item in linked_followups)

    card = {
        "disease": {"id": disease["id"], "name": disease["name"]},
        "can_grade_resident": disease["can_grade_resident"],
        "can_grade_resident2": disease["can_grade_resident2"],
        "can_arbitrate": disease["can_arbitrate"],
        "resident_pending": resident_pending,
        "resident2_pending": resident2_pending,
        # The Start Grading button leases either resident slot, so it shows the
        # combined figure rather than either half.
        "combined_pending": resident_pending + resident2_pending,
        "arbitration_pending": arbitration_pending,
        "arbitration_breakdown": pending.get("arbitration_breakdown", {}),
        "linked_followups": sorted(
            linked_followups, key=lambda item: str(item.get("name", ""))
        ),
        "linked_followup_total": linked_total,
        "has_work": bool(
            resident_pending or resident2_pending or arbitration_pending or linked_total
        ),
    }
    return card


def project_encounter_set_cards(
    db,
    *,
    user_id: int,
    refresh: bool = False,
) -> list[dict[str, Any]]:
    """The Project EncounterSet Grading panel, as serialisable dicts.

    Package reconciliation and the following authorized projection both run
    live so revoked allocations cannot leave queue data in a shared cache.
    """
    from grading.workbench.package_workflow import reconcile_active_packages
    from grading_allocation.dashboard import list_project_encounter_set_queues

    reconcile_active_packages(db)

    _ = refresh

    queues = [
        queue.to_dict()
        for queue in list_project_encounter_set_queues(
            db, user_id=user_id, reconcile=False
        )
    ]
    return queues
