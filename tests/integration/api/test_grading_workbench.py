from models import (
    EncounterSetGradingPackage,
    EncounterSetImage,
    GradingTask,
    LinkedDiseaseGrading,
    UserDiseaseUnitRole,
)
from tests.helpers.test_factories import TestDataFactory


def test_eligible_grader_can_resolve_standalone_task_workspace(
    app,
    db_session,
    test_users,
    core_test_data,
):
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        state="pending",
        image_name="standalone-workbench.jpg",
    )

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["schema_version"] == 2
    assert payload["target"] == {
        "type": "task",
        "ref": task.uuid,
        "slot": "resident",
    }
    assert payload["task"]["uuid"] == task.uuid
    assert payload["task"]["state"] == "pending"
    assert payload["task"]["disease"] == {
        "id": core_test_data["glaucoma"].id,
        "name": core_test_data["glaucoma"].name,
    }
    assert payload["image"]["uuid"] == task.encounter_file.uuid
    assert payload["image"]["url"].endswith(
        f"/media/img/{task.encounter_file.uuid}"
    )
    assert payload["active_image_uuid"] == task.encounter_file.uuid
    assert payload["images"] == [payload["image"]]
    assert len(payload["panels"]) == 1
    panel = payload["panels"][0]
    assert panel["task_uuid"] == task.uuid
    assert panel["disease"] == {
        "id": core_test_data["glaucoma"].id,
        "name": core_test_data["glaucoma"].name,
    }
    assert panel["grading_scope"] == "image"
    assert panel["target_level"] == "image"
    assert panel["read_only"] is False
    assert panel["grades"]
    assert all(grade["is_active"] for grade in panel["grades"])
    assert [grade["display_order"] for grade in panel["grades"]] == sorted(
        grade["display_order"] for grade in panel["grades"]
    )
    assert panel["existing_grade"] is None
    assert payload["capabilities"] == {
        "view": True,
        "annotate": True,
        "submit": False,
    }
    assert payload["annotation_context"] == {
        "policy_source": "non_project_default",
        "project_id": None,
        "enabled": True,
        "revision": 1,
            "enabled_tools": [
                "box",
                "rect",
                "polygon",
                "brush_mask",
            "ellipse",
            "pyramid",
        ],
        "default_feature_policy": {
            "localization": "box_or_segmentation",
            "preferred_tool": "box",
                "allowed_tools": [
                    "box",
                    "rect",
                    "polygon",
                "brush_mask",
                "ellipse",
                "pyramid",
            ],
        },
        "project_classes": [],
    }
    assert isinstance(payload["context_revision"], str)
    assert len(payload["context_revision"]) == 64


def test_grader_without_task_grant_cannot_resolve_workspace(
    app,
    db_session,
    test_users,
    core_test_data,
):
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        state="pending",
    )

    with app.test_client(user=test_users["ophthalmologist"]) as client:
        response = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert response.status_code == 403
    assert response.get_json() == {
        "error": "access_denied",
        "message": "You are not eligible to view this grading slot.",
    }


def test_workspace_keeps_linked_disease_gradings_in_separate_panels(
    app,
    db_session,
    test_users,
    core_test_data,
):
    primary = core_test_data["dr"]
    linked = core_test_data["dme"]
    relationship = (
        db_session.query(LinkedDiseaseGrading)
        .filter_by(primary_disease_id=primary.id, linked_disease_id=linked.id)
        .first()
    )
    if relationship is None:
        db_session.add(
            LinkedDiseaseGrading(
                primary_disease_id=primary.id,
                linked_disease_id=linked.id,
                display_order=1,
                is_active=True,
            )
        )
    else:
        relationship.is_active = True

    resident = test_users["resident"]
    for disease in (primary, linked):
        db_session.add(
            UserDiseaseUnitRole(
                user_id=resident.id,
                disease_id=disease.id,
                lab_unit_id=core_test_data["lab_unit"].id,
                can_grade_resident=True,
                can_grade_resident2=False,
                can_arbitrate=False,
            )
        )
    primary_task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=primary.id,
        state="pending",
        image_name="linked-workbench.jpg",
    )
    linked_task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=linked.id,
        encounter_file_id=primary_task.encounter_file_id,
        state="pending",
    )
    db_session.flush()

    with app.test_client(user=resident) as client:
        response = client.get(
            f"/api/grading-workbench/workspaces/task/{primary_task.uuid}?slot=resident"
        )

    assert response.status_code == 200
    panels = response.get_json()["panels"]
    assert [panel["task_uuid"] for panel in panels] == [primary_task.uuid, linked_task.uuid]
    assert [panel["disease"]["id"] for panel in panels] == [primary.id, linked.id]
    assert all(panel["grades"] for panel in panels)
    assert all(panel["read_only"] is False for panel in panels)


def test_encounter_set_package_workspace_includes_all_images_and_image_and_encounter_panels(
    app,
    db_session,
    test_users,
    core_test_data,
):
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
    )
    encounter.is_set_based = True
    images = []
    for position in (1, 2):
        image = EncounterSetImage(
            patient_encounter_id=encounter.id,
            spatial_position=position,
            original_filename=f"encounter-set-{position}.jpg",
            folder_rel="files/encounter_sets/test",
            visible_to_grader=True,
        )
        db_session.add(image)
        images.append(image)
    package = EncounterSetGradingPackage(
        patient_encounter_id=encounter.id,
        name="Comprehensive eye grading",
        code="comprehensive_eye",
        grading_mode="disease_specific",
    )
    db_session.add(package)
    db_session.flush()

    encounter_disease = core_test_data["dme"]
    encounter_disease.grading_scope = "encounter"
    resident = test_users["resident"]
    db_session.add(
        UserDiseaseUnitRole(
            user_id=resident.id,
            disease_id=encounter_disease.id,
            lab_unit_id=core_test_data["lab_unit"].id,
            can_grade_resident=True,
            can_grade_resident2=False,
            can_arbitrate=False,
        )
    )
    image_task = GradingTask(
        encounter_set_image_id=images[0].id,
        encounter_set_package_id=package.id,
        grading_target_level="image",
        disease_id=core_test_data["glaucoma"].id,
        lab_unit_id=core_test_data["lab_unit"].id,
        state="pending",
    )
    encounter_task = GradingTask(
        patient_encounter_id=encounter.id,
        encounter_set_package_id=package.id,
        grading_target_level="encounter",
        disease_id=encounter_disease.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        state="pending",
    )
    db_session.add_all([image_task, encounter_task])
    db_session.flush()

    with app.test_client(user=resident) as client:
        response = client.get(
            f"/api/grading-workbench/workspaces/task/{image_task.uuid}?slot=resident"
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert [image["uuid"] for image in payload["images"]] == [
        images[0].uuid,
        images[1].uuid,
    ]
    assert [panel["target_level"] for panel in payload["panels"]] == [
        "image",
        "encounter",
    ]
    assert [panel["grading_scope"] for panel in payload["panels"]] == [
        "image",
        "encounter",
    ]


def test_standalone_workbench_page_uses_vite_assets_and_workspace_api(
    app,
    db_session,
    test_users,
    core_test_data,
    monkeypatch,
):
    from grading import workbench as page_routes

    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        state="pending",
    )
    monkeypatch.setattr(
        page_routes,
        "get_workbench_assets",
        lambda: {
            "script": "grading-workbench/assets/workbench.js",
            "styles": ["grading-workbench/assets/workbench.css"],
        },
    )

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(
            f"/grading/workbench/task/{task.uuid}/resident"
        )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="grading-workbench-root"' in html
    assert (
        f'data-workspace-url="/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"'
        in html
    )
    assert '/static/grading-workbench/assets/workbench.js' in html
    assert '/static/grading-workbench/assets/workbench.css' in html
    assert 'meta name="csrf-token"' in html
    assert '/static/css/fa_7.0.1.all.min.css' in html
    assert 'bootstrap.min.css' not in html
    assert "partials/_grading_card.html" not in html
