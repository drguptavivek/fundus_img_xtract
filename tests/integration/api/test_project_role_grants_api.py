from models import Project, Role, User


def _role(db_session, name: str) -> Role:
    role = db_session.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db_session.add(role)
        db_session.flush()
    return role


def test_project_role_grant_api_and_workspace_group_roles(
    app,
    db_session,
    test_users,
    core_test_data,
):
    admin = db_session.merge(test_users["admin"])
    lab = db_session.merge(core_test_data["lab_a1"])
    if lab not in admin.lab_units:
        admin.lab_units.append(lab)
        db_session.flush()
    _role(db_session, "collaborator")
    _role(db_session, "analytics_viewer")
    target = User(
        username="project_grant_api_target",
        full_name="Project Grant Target",
        password_hash="x",
        is_active=True,
        hospital_id=lab.hospital_id,
        lab_units=[lab],
    )
    project = Project(
        title="Project Grant API Project",
        code="PROJECT_GRANT_API",
        active=True,
    )
    db_session.add_all([target, project])
    db_session.flush()

    with app.test_client(user=admin) as client:
        response = client.post(
            f"/api/projects/{project.id}/role-grants",
            json={
                "user_id": target.id,
                "scope_type": "lab_unit",
                "lab_unit_id": lab.id,
                "role_names": ["collaborator", "analytics_viewer"],
            },
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert {row["role_name"] for row in payload["data"]["updated"]} == {
            "collaborator",
            "analytics_viewer",
        }

        workspace = client.get(f"/admin/upload-projects/{project.id}/workspace")

    assert workspace.status_code == 200
    html = workspace.get_data(as_text=True)
    assert "Project Grant Target" in html
    assert lab.hospital.name in html
    assert lab.name in html
    assert "Collaborator" in html
    assert "Analytics Viewer" in html
    assert ">Edit</button>" in html
    assert "Remove collaborator grant" in html
    assert "Remove analytics viewer grant" in html
    assert "Upload</th>" not in html
    assert "Browse</th>" not in html


def test_remove_project_role_grant_api_deactivates_row(
    app,
    db_session,
    test_users,
    core_test_data,
):
    admin = db_session.merge(test_users["admin"])
    lab = db_session.merge(core_test_data["lab_a1"])
    _role(db_session, "collaborator")
    target = User(
        username="project_grant_remove_target",
        password_hash="x",
        is_active=True,
        hospital_id=lab.hospital_id,
        lab_units=[lab],
    )
    project = Project(
        title="Project Grant Remove Project",
        code="PROJECT_GRANT_REMOVE",
        active=True,
    )
    db_session.add_all([target, project])
    db_session.flush()

    with app.test_client(user=admin) as client:
        created = client.post(
            f"/api/projects/{project.id}/role-grants",
            json={
                "user_id": target.id,
                "scope_type": "lab_unit",
                "lab_unit_id": lab.id,
                "role_names": ["collaborator"],
            },
        ).get_json()["data"]["updated"][0]
        removed = client.delete(
            f"/api/projects/{project.id}/role-grants/{created['id']}"
        )

    assert removed.status_code == 200
    assert removed.get_json()["data"]["removed"]["active"] is False
