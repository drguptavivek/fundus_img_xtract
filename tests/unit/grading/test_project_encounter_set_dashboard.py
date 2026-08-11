from flask import render_template

from grading_allocation.dtos import (
    EncounterSetQueueSlotDTO,
    ProjectEncounterSetQueueDTO,
)


def test_grading_dashboard_separates_project_encounter_set_queues(
    app,
):
    queue = ProjectEncounterSetQueueDTO(
        project_id=3,
        project_title="Integrated DR Glaucoma Screening",
        project_code="ICMR-VG",
        target_key="disease_encounter:1:15",
        target_label="Glaucoma / EncounterSet",
        encounter_set_type_name="Remidio API Standard Encounter Set",
        slots=(
            EncounterSetQueueSlotDTO(
                slot="resident",
                package_count=1,
                task_count=1,
                first_package_uuid="package-uuid",
            ),
        ),
    )
    with app.test_request_context("/grading/"):
        body = render_template(
            "grading/index.html",
            v="test",
            project_encounter_set_queues=[queue.to_dict()],
            active_workbench={"session_uuid": "active-workbench-uuid"},
            diseases=[],
            is_resident=False,
            is_resident2=False,
            kpi_resident_pending=0,
            kpi_resident2_pending=0,
            kpi_arbitration_pending=0,
            kpi_resident_by_disease={},
            kpi_resident2_by_disease={},
            kpi_arbitration_by_disease={},
            kpi_arbitration_breakdown_by_disease={},
            kpi_resident_completed=0,
            kpi_resident2_completed=0,
            kpi_arbitration_completed=0,
            kpi_resident_completed_by_disease={},
            kpi_resident2_completed_by_disease={},
            kpi_arbitration_completed_by_disease={},
            task_tracker_kpi={
                "total": 0,
                "active": 0,
                "stale": 0,
                "by_role": {},
                "stale_by_role": {},
                "stuck_after_minutes": 60,
                "resume_task": None,
            },
            user_eligibility={},
            grading_eligibility={"non_project": [], "project": []},
            linked_followup_counts_by_disease={},
            history={
                "selected_date": "2026-08-10",
                "used_latest_fallback": False,
                "history_type": "all",
                "disease_id": None,
                "available_diseases": [],
                "trends": [],
                "items": [],
                "total_cards": 0,
                "total_tasks": 0,
                "total_images": 0,
                "page": 1,
                "total_pages": 1,
            },
            my_prev_url=None,
            my_next_url=None,
            page_prev_url=None,
            page_next_url=None,
        )

    assert "Project EncounterSet Grading" in body
    assert "Resume grading" in body
    assert "/grading/workbench/active-workbench-uuid" in body
    assert "Integrated DR Glaucoma Screening" in body
    assert "ICMR-VG" not in body
    assert "Glaucoma / EncounterSet" in body
    assert "Remidio API Standard Encounter Set" not in body
    assert "Resident (1 set)" in body
    assert "/grading/encounter_set_package/package-uuid/resident" in body
    assert "Legacy &amp; Image Grading" in body
    assert "My Grading Eligibility" in body
    assert 'data-bs-target="#nonProjectEligibility"' in body
    assert 'data-bs-target="#projectEligibility"' in body
    assert 'class="accordion-button collapsed' in body
    assert body.index("My Grading Eligibility") < body.index("My Grading History")
    assert body.index("My Grading History") < body.index("<h3>Pending</h3>")
