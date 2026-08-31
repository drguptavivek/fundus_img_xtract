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
                first_package_uuid="resident-package-uuid",
            ),
            EncounterSetQueueSlotDTO(
                slot="resident2",
                package_count=2,
                task_count=2,
                first_package_uuid="resident2-package-uuid",
            ),
        ),
    )
    with app.test_request_context("/grading/"):
        body = render_template(
            "grading/index.html",
            v="test",
            project_encounter_set_queues=[queue.to_dict()],
            active_workbench={"session_uuid": "active-workbench-uuid"},
            is_resident=False,
            is_resident2=False,
            user_eligibility={},
            grading_eligibility={"non_project": [], "project": []},
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
    assert "Resident (3 sets)" in body
    assert "Resident 2" not in body
    assert 'data-resident-slot="resident2"' in body
    assert "/grading/encounter_set_package/resident2-package-uuid/resident2" in body
    assert "/grading/encounter_set_package/resident-package-uuid/resident" not in body
    assert "Legacy &amp; Image Grading" in body
    assert "My Grading Eligibility" in body
    assert 'data-bs-target="#nonProjectEligibility"' in body
    assert 'data-bs-target="#projectEligibility"' in body
    assert 'class="accordion-button collapsed' in body
    assert body.index("My Grading Eligibility") < body.index("My Grading History")
    # The pending/completed KPI tiles were removed from this page; per-disease
    # queue cards now hydrate themselves after the initial render instead.
    assert "<h3>Pending</h3>" not in body
    assert "<h3>My Gradings</h3>" not in body
    # The Legacy panel is fetched from its own endpoint, so the page ships a
    # loading shell rather than the cards themselves.
    assert 'id="disease-queues-shell"' in body
    assert "Loading your grading queues" in body


def test_project_encounter_set_ui_falls_back_to_internal_resident_slot(app):
    queue = ProjectEncounterSetQueueDTO(
        project_id=3,
        project_title="Resident Fallback Project",
        project_code="FALLBACK",
        target_key="disease_encounter:1:15",
        target_label="DR / EncounterSet",
        encounter_set_type_name="Encounter Set",
        slots=(
            EncounterSetQueueSlotDTO(
                slot="resident",
                package_count=1,
                task_count=1,
                first_package_uuid="resident-fallback-package",
            ),
        ),
    )

    with app.test_request_context("/grading/"):
        body = render_template(
            "grading/_project_encounter_set_queues.html",
            project_encounter_set_queues=[queue.to_dict()],
        )

    assert "Resident (1 set)" in body
    assert "Resident 2" not in body
    assert 'data-resident-slot="resident"' in body
    assert "/grading/encounter_set_package/resident-fallback-package/resident" in body
