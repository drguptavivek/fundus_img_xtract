from __future__ import annotations

import ast
from pathlib import Path

from data_authorization.models import ProjectRoleGrant
from models import Project, Role, User
from regrade.service import (
    authorized_manager_project_grant_ids,
    can_submit_assigned_regrade,
)


def _role(db, name: str) -> Role:
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def test_regrade_manager_query_receives_only_active_data_manager_grant_ids(
    db_session, core_test_data
):
    actor = User(username="project_regrade_manager", password_hash="x", is_active=True)
    project = Project(title="Regrade authorization", code="REGR_AUTH", active=True)
    db_session.add_all([actor, project])
    db_session.flush()

    data_manager = _role(db_session, "data_manager")
    unrelated_role = _role(db_session, "regrade_adjudicator")
    active_grant = ProjectRoleGrant(
        project_id=project.id,
        user_id=actor.id,
        role_id=data_manager.id,
        scope_type="project",
        active=True,
    )
    inactive_grant = ProjectRoleGrant(
        project_id=project.id,
        user_id=actor.id,
        role_id=data_manager.id,
        scope_type="lab_unit",
        lab_unit_id=db_session.merge(core_test_data["lab_a1"]).id,
        active=False,
    )
    unrelated_grant = ProjectRoleGrant(
        project_id=project.id,
        user_id=actor.id,
        role_id=unrelated_role.id,
        scope_type="project",
        active=True,
    )
    db_session.add_all([active_grant, inactive_grant, unrelated_grant])
    db_session.flush()

    assert authorized_manager_project_grant_ids(
        db_session, actor=actor
    ) == frozenset({active_grant.id})


def test_admin_cannot_submit_regrade_by_break_glass_status(db_session):
    admin = User(username="regrade_admin", password_hash="x", is_active=True)
    local_admin = User(username="regrade_local_admin", password_hash="x", is_active=True)
    assignee = User(username="regrade_assignee", password_hash="x", is_active=True)
    db_session.add_all([admin, local_admin, assignee])
    db_session.flush()
    admin.roles.append(_role(db_session, "admin"))
    local_admin.roles.append(_role(db_session, "local_admin"))
    db_session.flush()

    assert not can_submit_assigned_regrade(
        actor=admin, assigned_to_user_id=assignee.id
    )
    assert not can_submit_assigned_regrade(
        actor=local_admin, assigned_to_user_id=assignee.id
    )
    assert can_submit_assigned_regrade(actor=assignee, assigned_to_user_id=assignee.id)


def test_project_capable_regrade_routes_use_login_gate_not_global_role_gate():
    source = Path("grading/regrade_tasks.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    expected = {
        "regrade_tasks",
        "start_random_regrade_task",
        "regrade_task_detail",
    }
    decorators = {
        node.name: {
            decorator.id
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Name)
        }
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in expected
    }

    assert decorators == {name: {"login_required"} for name in expected}

    api_source = Path("api/regrade_tasks.py").read_text(encoding="utf-8")
    api_module = ast.parse(api_source)
    submit = next(
        node
        for node in api_module.body
        if isinstance(node, ast.FunctionDef) and node.name == "submit_regrade_api"
    )
    assert any(
        isinstance(decorator, ast.Name)
        and decorator.id == "session_or_token_auth_required"
        for decorator in submit.decorator_list
    )
