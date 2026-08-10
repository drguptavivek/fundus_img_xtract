from models import Project
from project_annotations.models import (
    ProjectAnnotationClass,
    ProjectAnnotationPolicyRevision,
)
from tests.helpers.test_factories import TestDataFactory


def _project_task(db_session, test_users, core_test_data):
    lab_unit = db_session.merge(core_test_data["lab_unit"])
    admin = db_session.merge(test_users["admin"])
    if lab_unit not in admin.lab_units:
        admin.lab_units.append(lab_unit)
    project = Project(title="HTML annotation project", code="HTML-ANNOTATION", active=True)
    db_session.add(project)
    db_session.flush()
    image = TestDataFactory.create_direct_image_upload(
        db_session,
        lab_unit_id=lab_unit.id,
        uploader_id=admin.id,
        hospital_id=core_test_data["hospital"].id,
        camera_id=core_test_data["camera"].id,
        disease_id=core_test_data["glaucoma"].id,
        area_id=core_test_data["area"].id,
    )
    image.project_id = project.id
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=lab_unit.id,
        disease_id=core_test_data["glaucoma"].id,
        direct_image_upload_id=image.id,
    )
    db_session.flush()
    return project, task


def _payload(revision=0, classes=None):
    return {
        "revision": revision,
        "enabled": True,
        "enabled_tools": ["box", "polygon"],
        "default_feature_policy": {
            "localization": "box_or_segmentation",
            "preferred_tool": "box",
            "allowed_tools": ["box", "polygon"],
        },
        "project_classes": classes if classes is not None else [
            {
                "key": "optic_disc",
                "localization": "segmentation",
                "display_order": 10,
                "multiple_instances": False,
                "active": True,
            }
        ],
    }


def test_admin_policy_update_preserves_history_and_rejects_stale_revision(
    app, db_session, test_users, core_test_data
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    with app.test_client(user=test_users["admin"]) as client:
        created = client.put(
            f"/api/projects/{project.id}/annotation-policy", json=_payload()
        )
        stale = client.put(
            f"/api/projects/{project.id}/annotation-policy", json=_payload()
        )

    assert created.status_code == 200
    assert created.get_json()["revision"] == 1
    assert stale.status_code == 409
    assert stale.get_json()["error"] == "stale_revision"
    assert db_session.query(ProjectAnnotationPolicyRevision).filter_by(
        revision=1
    ).count() == 1


def test_omitted_project_class_is_deactivated_not_deleted(
    app, db_session, test_users, core_test_data
):
    project, _task = _project_task(db_session, test_users, core_test_data)
    with app.test_client(user=test_users["admin"]) as client:
        created = client.put(
            f"/api/projects/{project.id}/annotation-policy", json=_payload()
        ).get_json()
        updated = client.put(
            f"/api/projects/{project.id}/annotation-policy",
            json=_payload(revision=created["revision"], classes=[]),
        )

    assert updated.status_code == 200
    saved_class = db_session.get(
        ProjectAnnotationClass, created["project_classes"][0]["id"]
    )
    assert saved_class is not None
    assert saved_class.active is False
    assert updated.get_json()["project_classes"][0]["active"] is False


def test_grader_can_read_resolved_task_annotation_context(
    app, db_session, test_users, core_test_data
):
    project, task = _project_task(db_session, test_users, core_test_data)
    with app.test_client(user=test_users["admin"]) as client:
        saved = client.put(
            f"/api/projects/{project.id}/annotation-policy", json=_payload()
        )
    assert saved.status_code == 200

    with app.test_client(user=test_users["resident"]) as client:
        response = client.get(
            f"/api/grading-tasks/{task.uuid}/annotation-context?slot=resident"
        )

    assert response.status_code == 200
    assert response.get_json()["project_id"] == project.id
    assert response.get_json()["project_classes"][0]["key"] == "optic_disc"
    assert response.headers["Cache-Control"] == "no-store, private"


def test_project_workspace_exposes_non_react_policy_editor(
    app, db_session, test_users, core_test_data
):
    project, _task = _project_task(db_session, test_users, core_test_data)

    with app.test_client(user=test_users["admin"]) as client:
        workspace = client.get(f"/admin/upload-projects/{project.id}/workspace")
        page = client.get("/admin/upload-projects")

    assert workspace.status_code == 200
    html = workspace.get_data(as_text=True)
    assert "data-project-annotation-policy-panel" in html
    assert f"/api/projects/{project.id}/annotation-policy" in html
    assert "Project Annotations" in html
    assert page.status_code == 200
    assert "admin-project-annotations.js" in page.get_data(as_text=True)
