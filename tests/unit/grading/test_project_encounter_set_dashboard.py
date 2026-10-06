from flask import render_template, render_template_string

from grading_allocation.dtos import (
    EncounterSetQueueSlotDTO,
    ProjectEncounterSetQueueDTO,
)


def test_grading_display_labels_hide_internal_initial_slot_names(app):
    with app.test_request_context("/grading/"):
        body = render_template_string(
            """
            {% from "grading/_display_labels.html" import grading_slot_label, grading_state_label %}
            {{ grading_slot_label('resident') }}|
            {{ grading_slot_label('resident2') }}|
            {{ grading_slot_label('arbitrator') }}|
            {{ grading_state_label('resident_done') }}|
            {{ grading_state_label('resident2_done') }}
            """
        )

    assert body.count("Initial grading|") == 2
    assert "Arbitration|" in body
    assert "Initial 1 done|" in body
    assert "Initial 2 done" in body
    assert "Resident" not in body


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
        page = render_template(
            "grading/index.html",
            v="test",
            active_workbench={"session_uuid": "active-workbench-uuid"},
            refresh=False,
            oob=False,
        )
        body = render_template(
            "grading/_project_encounter_set_queues.html",
            project_encounter_set_queues=[queue.to_dict()],
        )
        eligibility = render_template(
            "grading/_eligibility_panel.html",
            grading_eligibility={"non_project": [], "project": []},
        )

    # The page paints shells only; queues load after first paint and
    # eligibility/history on demand, each from its own fragment endpoint.
    assert "Project EncounterSet Grading" in page
    assert "Resume grading" in page
    assert "/grading/workbench/active-workbench-uuid" in page
    assert "Legacy &amp; Image Grading" in page
    assert 'id="disease-queues-shell"' in page
    assert "Loading your grading queues" in page
    assert 'id="project-encounter-set-queues"' in page
    assert "/grading/fragments/project-queues" in page
    assert "/grading/fragments/eligibility" in page
    assert 'id="show-grading-eligibility"' in page
    assert 'id="show-grading-history"' in page
    assert 'click from:#show-grading-history' in page
    assert page.index("My Grading Eligibility") < page.index("My Grading History")
    assert "<h3>Pending</h3>" not in page
    assert "<h3>My Gradings</h3>" not in page

    assert "Integrated DR Glaucoma Screening" in body
    assert "ICMR-VG" not in body
    assert "Glaucoma / EncounterSet" in body
    assert "Remidio API Standard Encounter Set" not in body
    assert "Initial grading (3 sets)" in body
    assert "Start Initial grading for Glaucoma / EncounterSet" in body
    assert "Resident (3 sets)" not in body
    assert 'data-resident-slot="resident"' not in body
    assert 'data-resident-slot="resident2"' in body
    assert "/grading/encounter_set_package/resident2-package-uuid/resident2" in body
    assert "/grading/encounter_set_package/resident-package-uuid/resident" not in body

    assert "My Grading Eligibility" in eligibility
    assert 'data-bs-target="#nonProjectEligibility"' in eligibility
    assert 'data-bs-target="#projectEligibility"' in eligibility
    assert 'class="accordion-button collapsed' in eligibility


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

    assert "Initial grading (1 set)" in body
    assert 'data-resident-slot="resident"' in body
    assert "/grading/encounter_set_package/resident-fallback-package/resident" in body
