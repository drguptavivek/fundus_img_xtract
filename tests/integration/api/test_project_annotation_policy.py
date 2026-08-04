import tomllib

from encounter_set_types.models import EncounterSetType
from models import Disease, DiseaseGrading, GradingsFeatures, Project
from project_annotations.service import parse_policy_update, save_project_policy
from tests.helpers.test_factories import TestDataFactory
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileDisease,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeGradingPackage,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileEncounterSetTypePackageEncounterScheme,
    UploadProfileEncounterSetTypePackageImageScheme,
)


def _project_task(db_session, test_users, core_test_data):
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    if lab_unit not in test_users["admin"].lab_units:
        test_users["admin"].lab_units.append(lab_unit)
    project = Project(title="Annotation Project", code="ANNOTATION-PROJECT", active=True)
    db_session.add(project)
    db_session.flush()
    image = TestDataFactory.create_direct_image_upload(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        uploader_id=test_users["admin"].id,
        hospital_id=core_test_data["hospital"].id,
        camera_id=core_test_data["camera"].id,
        disease_id=core_test_data["glaucoma"].id,
        area_id=core_test_data["area"].id,
    )
    image.project_id = project.id
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=core_test_data["lab_unit"].id,
        disease_id=core_test_data["glaucoma"].id,
        direct_image_upload_id=image.id,
    )
    db_session.flush()
    return project, task


def _policy_payload():
    return {
        "enabled": True,
        "enabled_tools": ["box", "polygon"],
        "default_feature_policy": {
            "localization": "box_or_segmentation",
            "preferred_tool": "box",
            "allowed_tools": ["box", "polygon"],
        },
        "project_classes": [
            {
                "key": "lesion",
                "localization": "box_or_segmentation",
                "multiple_instances": True,
                "active": True,
            },
            {
                "key": "optic_disc",
                "localization": "segmentation",
                "multiple_instances": False,
                "active": True,
            },
        ],
    }


def _associated_classification_schema(db_session, project):
    scheme = Disease(
        name=f"Project classification {project.id}",
        grading_scope="image",
        remidio_ocr_linkage="none",
    )
    grade = DiseaseGrading(
        disease=scheme,
        impression="Referable",
        display_order=2,
        is_active=True,
        prioritize_for_task_selection=True,
        is_ungradable=False,
        guidelines="Refer when either feature is present.",
    )
    grade.features = [
        GradingsFeatures(sr_no=2, label="Haemorrhage"),
        GradingsFeatures(sr_no=1, label="Microaneurysm"),
    ]
    profile = UploadProfile(name=f"Project schema profile {project.id}", active=True)
    profile.diseases.append(UploadProfileDisease(disease=scheme, is_default=True))
    db_session.add_all([
        scheme,
        profile,
        ProjectUploadProfile(project=project, profile=profile, active=True),
    ])
    db_session.flush()
    return scheme, grade, profile


def test_admin_can_export_project_annotation_and_classification_schema_as_json(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    scheme, grade, profile = _associated_classification_schema(db_session, project)
    annotation_schema = save_project_policy(
        db_session,
        project_id=project.id,
        actor_user_id=test_users["admin"].id,
        update=parse_policy_update(_policy_payload()),
    ).to_dict()

    with app.test_client(user=test_users["admin"]) as client:
        response = client.get(f"/api/projects/{project.id}/schema.json")

    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.headers["Content-Disposition"] == (
        f'attachment; filename="{project.code.lower()}-annotation-classification-schema.json"'
    )
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.get_json()
    assert payload["schema_version"] == 1
    assert payload["project"] == {
        "id": project.id,
        "code": project.code,
        "title": project.title,
        "active": True,
    }
    assert payload["annotation_schema"] == annotation_schema
    assert payload["classification_schemas"] == [
        {
            "id": scheme.id,
            "name": scheme.name,
            "grading_scope": "image",
            "remidio_ocr_linkage": "none",
            "associations": [
                {
                    "kind": "upload_profile_disease",
                    "upload_profile_id": profile.id,
                    "upload_profile_name": profile.name,
                    "is_default": True,
                }
            ],
            "grades": [
                {
                    "id": grade.id,
                    "impression": "Referable",
                    "display_order": 2,
                    "is_active": True,
                    "prioritize_for_task_selection": True,
                    "is_ungradable": False,
                    "guidelines": "Refer when either feature is present.",
                    "features": [
                        {
                            "id": grade.features[1].id,
                            "sr_no": 1,
                            "label": "Microaneurysm",
                        },
                        {
                            "id": grade.features[0].id,
                            "sr_no": 2,
                            "label": "Haemorrhage",
                        },
                    ],
                }
            ],
        }
    ]


def test_project_schema_toml_export_matches_json_export(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    _associated_classification_schema(db_session, project)
    save_project_policy(
        db_session,
        project_id=project.id,
        actor_user_id=test_users["admin"].id,
        update=parse_policy_update(_policy_payload()),
    )

    with app.test_client(user=test_users["admin"]) as client:
        json_response = client.get(f"/api/projects/{project.id}/schema.json")
        toml_response = client.get(f"/api/projects/{project.id}/schema.toml")

    assert json_response.status_code == 200
    assert toml_response.status_code == 200
    assert toml_response.mimetype == "application/toml"
    assert toml_response.headers["Content-Disposition"] == (
        f'attachment; filename="{project.code.lower()}-annotation-classification-schema.toml"'
    )
    assert toml_response.headers["Cache-Control"] == "no-store"
    assert tomllib.loads(toml_response.get_data(as_text=True)) == json_response.get_json()


def test_project_schema_collects_encounter_and_package_classification_associations(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    image_scheme = Disease(name=f"Image schema {project.id}", grading_scope="image")
    encounter_scheme = Disease(name=f"Encounter schema {project.id}", grading_scope="encounter")
    package_image_scheme = Disease(name=f"Package image schema {project.id}", grading_scope="image")
    package_encounter_scheme = Disease(name=f"Package encounter schema {project.id}", grading_scope="encounter")
    encounter_type = EncounterSetType(
        name=f"Schema encounter type {project.id}",
        code=f"schema_est_{project.id}",
        metadata_schema_json={"fields": []},
        asset_rules_json={},
        active=True,
    )
    profile = UploadProfile(name=f"Encounter schema profile {project.id}", active=True)
    encounter_mapping = UploadProfileEncounterSetType(
        encounter_set_type=encounter_type,
        encounter_grading_scheme=encounter_scheme,
        active=True,
        image_grading_schemes=[
            UploadProfileEncounterSetTypeImageGradingScheme(
                disease=image_scheme,
                is_default=True,
                active=True,
            )
        ],
    )
    encounter_mapping.grading_packages.append(
        UploadProfileEncounterSetTypeGradingPackage(
            name="Primary package",
            code="primary",
            applicability="always",
            grading_mode="disease_specific",
            active=True,
            image_grading_schemes=[
                UploadProfileEncounterSetTypePackageImageScheme(
                    disease=package_image_scheme,
                    is_default=True,
                    active=True,
                )
            ],
            encounter_grading_schemes=[
                UploadProfileEncounterSetTypePackageEncounterScheme(
                    disease=package_encounter_scheme,
                    active=True,
                )
            ],
        )
    )
    profile.encounter_set_types.append(encounter_mapping)
    db_session.add_all([
        image_scheme,
        encounter_scheme,
        package_image_scheme,
        package_encounter_scheme,
        encounter_type,
        profile,
        ProjectUploadProfile(project=project, profile=profile, active=True),
    ])
    db_session.flush()

    with app.test_client(user=test_users["admin"]) as client:
        response = client.get(f"/api/projects/{project.id}/schema.json")

    assert response.status_code == 200
    schemas = {row["name"]: row for row in response.get_json()["classification_schemas"]}
    assert schemas[image_scheme.name]["associations"][0]["kind"] == "encounter_set_image"
    assert schemas[encounter_scheme.name]["associations"][0]["kind"] == "encounter_set_encounter"
    assert schemas[package_image_scheme.name]["associations"][0]["kind"] == "grading_package_image"
    assert schemas[package_encounter_scheme.name]["associations"][0]["kind"] == "grading_package_encounter"


def test_admin_can_save_project_policy(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)

    with app.test_client(user=test_users["admin"]) as client:
        saved = client.put(
            f"/api/projects/{project.id}/annotation-policy",
            json=_policy_payload(),
        )

    assert saved.status_code == 200
    saved_payload = saved.get_json()
    assert saved_payload["policy_source"] == "project"
    assert saved_payload["project_id"] == project.id
    assert saved_payload["revision"] == 1
    assert "feature_overrides" not in saved_payload
    assert set(saved_payload["project_classes"][0]) == {
        "id", "key", "localization", "display_order", "multiple_instances", "active"
    }
    assert saved_payload["project_classes"][1]["multiple_instances"] is False


def test_project_classes_are_returned_in_configured_display_order(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    payload = _policy_payload()
    payload["project_classes"][0]["display_order"] = 20
    payload["project_classes"][1]["display_order"] = 10

    with app.test_client(user=test_users["admin"]) as client:
        response = client.put(
            f"/api/projects/{project.id}/annotation-policy",
            json=payload,
        )

    assert response.status_code == 200
    rows = response.get_json()["project_classes"]
    assert [row["key"] for row in rows] == ["optic_disc", "lesion"]
    assert [row["display_order"] for row in rows] == [10, 20]


def test_grader_workspace_resolves_saved_project_policy(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, task = _project_task(db_session, test_users, core_test_data)
    expected = save_project_policy(
        db_session,
        project_id=project.id,
        actor_user_id=test_users["admin"].id,
        update=parse_policy_update(_policy_payload()),
    ).to_dict()

    with app.test_client(user=test_users["resident"]) as client:
        workspace = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert workspace.status_code == 200
    annotation_context = workspace.get_json()["annotation_context"]
    assert annotation_context == expected
    assert workspace.get_json()["capabilities"]["annotate"] is True


def test_grader_can_resolve_task_annotation_context_endpoint(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, task = _project_task(db_session, test_users, core_test_data)
    expected = save_project_policy(
        db_session,
        project_id=project.id,
        actor_user_id=test_users["admin"].id,
        update=parse_policy_update(_policy_payload()),
    ).to_dict()

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(
            f"/api/grading-tasks/{task.uuid}/annotation-context?slot=resident"
        )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["annotation_context"] == expected
    assert len(payload["context_revision"]) == 64
    assert response.headers["Cache-Control"] == "no-store, private"


def test_project_without_policy_does_not_use_non_project_fallback(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, task = _project_task(db_session, test_users, core_test_data)

    with app.test_client(user=test_users["resident"]) as client:
        workspace = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert workspace.status_code == 200
    payload = workspace.get_json()
    assert payload["annotation_context"] == {
        "policy_source": "project",
        "project_id": project.id,
        "enabled": False,
        "revision": 0,
        "enabled_tools": [],
        "default_feature_policy": {
            "localization": "box_or_segmentation",
            "preferred_tool": "box",
            "allowed_tools": [],
        },
        "project_classes": [],
    }
    assert payload["capabilities"]["annotate"] is False


def test_workbench_context_revision_changes_when_policy_revision_changes(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, task = _project_task(db_session, test_users, core_test_data)

    with app.test_client(user=test_users["resident"]) as client:
        before = client.get(
            f"/api/grading-tasks/{task.uuid}/annotation-context?slot=resident"
        )
        save_project_policy(
            db_session,
            project_id=project.id,
            actor_user_id=test_users["admin"].id,
            update=parse_policy_update(_policy_payload()),
        )
        after = client.get(
            f"/api/grading-tasks/{task.uuid}/annotation-context?slot=resident"
        )

    assert before.status_code == 200
    assert after.status_code == 200
    assert before.get_json()["annotation_context"]["revision"] == 0
    assert after.get_json()["annotation_context"]["revision"] == 1
    assert before.get_json()["context_revision"] != after.get_json()["context_revision"]


def test_disabled_project_policy_hides_tools_and_classes_from_grader(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, task = _project_task(db_session, test_users, core_test_data)
    payload = _policy_payload()
    payload["enabled"] = False
    save_project_policy(
        db_session,
        project_id=project.id,
        actor_user_id=test_users["admin"].id,
        update=parse_policy_update(payload),
    )

    with app.test_client(user=test_users["resident"]) as client:
        workspace = client.get(
            f"/api/grading-workbench/workspaces/task/{task.uuid}?slot=resident"
        )

    assert workspace.status_code == 200
    context = workspace.get_json()["annotation_context"]
    assert context["policy_source"] == "project"
    assert context["enabled"] is False
    assert context["revision"] == 1
    assert context["enabled_tools"] == []
    assert context["project_classes"] == []
    assert workspace.get_json()["capabilities"]["annotate"] is False


def test_admin_policy_revision_increments_and_omitted_class_is_deleted(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    with app.test_client(user=test_users["admin"]) as client:
        first = client.put(
            f"/api/projects/{project.id}/annotation-policy",
            json=_policy_payload(),
        )
        second_payload = _policy_payload()
        second_payload["project_classes"] = second_payload["project_classes"][:1]
        saved_classes = {row["key"]: row for row in first.get_json()["project_classes"]}
        second_payload["project_classes"][0]["id"] = saved_classes["lesion"]["id"]
        # Reuse the key of the omitted row to prove deletion occurs before the
        # retained row is updated.
        second_payload["project_classes"][0]["key"] = "optic_disc"
        second_payload["project_classes"][0]["localization"] = "segmentation"
        second = client.put(
            f"/api/projects/{project.id}/annotation-policy",
            json=second_payload,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    payload = second.get_json()
    assert payload["revision"] == 2
    classes = {row["key"]: row for row in payload["project_classes"]}
    assert len(classes) == 1
    assert classes["optic_disc"]["id"] == saved_classes["lesion"]["id"]
    assert classes["optic_disc"]["active"] is True
    assert classes["optic_disc"]["localization"] == "segmentation"


def test_policy_api_rejects_invalid_tool_without_server_error(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    payload = _policy_payload()
    payload["default_feature_policy"]["preferred_tool"] = "freehand"

    with app.test_client(user=test_users["admin"]) as client:
        response = client.put(
            f"/api/projects/{project.id}/annotation-policy",
            json=payload,
        )

    assert response.status_code == 422
    assert response.get_json()["error"] == "validation_error"


def test_grader_cannot_administer_project_policy(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(f"/api/projects/{project.id}/annotation-policy")

    assert response.status_code == 403


def test_manager_without_lab_scope_cannot_read_project_policy(
    app,
    db_session,
    test_users,
):
    project = Project(title="Out of scope", code="OUT-OF-SCOPE", active=True)
    db_session.add(project)
    db_session.flush()

    with app.test_client(user=test_users["admin"]) as client:
        response = client.get(f"/api/projects/{project.id}/annotation-policy")

    assert response.status_code == 403
    assert response.get_json()["error"] == "access_denied"


def test_project_workspace_exposes_annotation_policy_editor(
    app,
    db_session,
    test_users,
    core_test_data,
):
    project, _task = _project_task(db_session, test_users, core_test_data)

    with app.test_client(user=test_users["admin"]) as client:
        response = client.get(f"/admin/upload-projects/{project.id}/workspace")
        page = client.get("/admin/upload-projects")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-project-annotation-policy-panel' in html
    assert f'data-policy-url="/api/projects/{project.id}/annotation-policy"' in html
    assert f'data-policy-save-url="/api/projects/{project.id}/annotation-policy"' in html
    assert 'data-annotation-feature-select' not in html
    assert 'Feature-specific overrides' not in html
    assert 'Bounding box' in html
    assert 'Segmentation' in html
    assert '>Rect<' in html
    assert 'Project Annotations' in html
    assert f'href="/api/projects/{project.id}/schema.json"' in html
    assert f'href="/api/projects/{project.id}/schema.toml"' in html
    assert 'Export JSON' in html
    assert 'Export TOML' in html
    assert page.status_code == 200
    assert '/static/js/admin-project-annotations.js' in page.get_data(as_text=True)
