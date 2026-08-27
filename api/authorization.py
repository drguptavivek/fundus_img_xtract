"""Staged REST surface for the atomic authorization-v2 cutover.

This module is intentionally not imported by ``api.__init__`` until every live
endpoint is classified and the old authorization engine is removed.
"""

from __future__ import annotations

from uuid import uuid4

from flask import jsonify, request
from flask_login import current_user, login_required

from api import api_bp
from auth.utils import utcnow
from authz_v2.core.actions import Action
from authz_v2.core.principals import (
    PrincipalDTO,
    SessionChannel,
    SessionContextDTO,
)
from authz_v2.core.resources import ScopeDTO
from authz_v2.core.roles import Role, ScopeType
from authz_v2.domain.descriptions import describe_catalogue
from authz_v2.domain.exceptions import AuthorizationError
from authz_v2.domain.grants import (
    DESCRIPTION_UNSET,
    GrantCreateDTO,
    GrantUpdateDTO,
)
from authz_v2.flask import EndpointMode, authorization_endpoint
from authz_v2.repositories.audit import AuditRepository
from authz_v2.repositories.grants import GrantRepository
from authz_v2.resources.composition import register_core_adapters
from authz_v2.resources.registry import registry
from authz_v2.serialization.api import serialize_dto
from authz_v2.services.audit import AuthorizationAuditService
from authz_v2.services.decision import AuthorizationDecisionService
from authz_v2.services.grants import GrantMutationService
from authz_v2.services.projections import (
    capability_projection,
    upload_projection,
    workspace_projection,
)
from db_transaction_manager import transaction_scope


def _principal_from_current_user() -> PrincipalDTO:
    return PrincipalDTO(
        user_id=int(current_user.id),
        active=bool(current_user.is_active),
        authenticated=bool(current_user.is_authenticated),
        session=SessionContextDTO(
            request_id=str(uuid4()),
            channel=SessionChannel.WEB,
            evaluated_at=utcnow(),
        ),
    )


def _services(db):
    register_core_adapters(registry)
    repository = GrantRepository(db)
    decision = AuthorizationDecisionService(repository, registry)
    audit = AuthorizationAuditService(AuditRepository(db))
    mutations = GrantMutationService(repository, decision, audit)
    return repository, decision, mutations


def _json_body() -> dict[str, object]:
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise TypeError("request body must be a JSON object")
    return value


def _required_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _parse_grant_create(payload: dict[str, object]) -> GrantCreateDTO:
    allowed = {"user_id", "role", "scope_type", "scope_id", "description"}
    if set(payload) - allowed:
        raise ValueError("request contains unsupported fields")
    user_id = _required_int(payload.get("user_id"), "user_id")
    role_value = payload.get("role")
    scope_type_value = payload.get("scope_type")
    if not isinstance(role_value, str) or not isinstance(scope_type_value, str):
        raise TypeError("role and scope_type are required")
    role = Role(role_value)
    scope_type = ScopeType(scope_type_value)
    scope_id_value = payload.get("scope_id")
    if scope_type is ScopeType.SYSTEM:
        if scope_id_value is not None:
            raise ValueError("system scope_id must be null")
        scope_id = None
    else:
        scope_id = _required_int(scope_id_value, "scope_id")
    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError("description must be a string or null")
    return GrantCreateDTO(
        user_id=user_id,
        role=role,
        scope=ScopeDTO(scope_type, scope_id),
        description=description,
    )


def _parse_grant_update(payload: dict[str, object]) -> GrantUpdateDTO:
    if not payload or set(payload) - {"description", "active"}:
        raise ValueError("grant update must contain description or active")
    description: object = DESCRIPTION_UNSET
    if "description" in payload:
        description = payload["description"]
        if description is not None and not isinstance(description, str):
            raise ValueError("description must be a string or null")
    active = payload.get("active")
    if active is not None and not isinstance(active, bool):
        raise ValueError("active must be a boolean")
    return GrantUpdateDTO(description=description, active=active)


def _not_authorized():
    return jsonify({"error": {"code": "not_authorized"}}), 403


def _invalid_request():
    return jsonify({"error": {"code": "invalid_request"}}), 400


@api_bp.get("/authorization/catalogue")
@login_required
@authorization_endpoint(
    EndpointMode.SCREEN,
    Action.AUTHORIZATION_CATALOGUE_VIEW,
    enforcement="screen_entry",
)
def authorization_catalogue():
    with transaction_scope() as db:
        _repository, decision, _mutations = _services(db)
        try:
            decision.require(
                db,
                _principal_from_current_user(),
                Action.AUTHORIZATION_CATALOGUE_VIEW,
                None,
            )
        except AuthorizationError:
            return _not_authorized()
        payload = serialize_dto(describe_catalogue())
    return jsonify({"data": payload})


@api_bp.get("/authorization/me/capabilities")
@login_required
@authorization_endpoint(
    EndpointMode.PROTECTED,
    Action.AUTHORIZATION_ME_CAPABILITIES_VIEW,
    resolver="user",
)
def authorization_capabilities():
    try:
        with transaction_scope() as db:
            _repository, decision, _mutations = _services(db)
            principal = decision.authoritative_principal(_principal_from_current_user())
            decision.require(
                db,
                principal,
                Action.AUTHORIZATION_ME_CAPABILITIES_VIEW,
                principal.user_id,
            )
            payload = serialize_dto(
                capability_projection(principal, decision.active_grants(principal))
            )
    except AuthorizationError:
        return _not_authorized()
    return jsonify({"data": {"items": payload}})


@api_bp.get("/authorization/me/workspaces")
@login_required
@authorization_endpoint(
    EndpointMode.PROTECTED,
    Action.AUTHORIZATION_ME_WORKSPACES_VIEW,
    resolver="user",
)
def authorization_workspaces():
    try:
        with transaction_scope() as db:
            _repository, decision, _mutations = _services(db)
            principal = decision.authoritative_principal(_principal_from_current_user())
            decision.require(
                db,
                principal,
                Action.AUTHORIZATION_ME_WORKSPACES_VIEW,
                principal.user_id,
            )
            payload = serialize_dto(
                workspace_projection(db, decision.active_grants(principal))
            )
    except AuthorizationError:
        return _not_authorized()
    return jsonify({"data": {"items": payload}})


@api_bp.get("/authorization/me/upload-options")
@login_required
@authorization_endpoint(
    EndpointMode.PROTECTED,
    Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW,
    resolver="user",
)
def authorization_upload_options():
    try:
        with transaction_scope() as db:
            _repository, decision, _mutations = _services(db)
            principal = decision.authoritative_principal(_principal_from_current_user())
            decision.require(
                db,
                principal,
                Action.AUTHORIZATION_ME_UPLOAD_OPTIONS_VIEW,
                principal.user_id,
            )
            payload = serialize_dto(
                upload_projection(db, principal, decision.active_grants(principal))
            )
    except AuthorizationError:
        return _not_authorized()
    return jsonify({"data": {"items": payload}})


@api_bp.get("/authorization/grants")
@login_required
@authorization_endpoint(
    EndpointMode.SCREEN,
    Action.AUTHORIZATION_GRANTS_VIEW,
    enforcement="screen_entry",
)
def authorization_grants():
    with transaction_scope() as db:
        repository, decision, _mutations = _services(db)
        principal = _principal_from_current_user()
        try:
            decision.require(db, principal, Action.AUTHORIZATION_GRANTS_VIEW, None)
            rows = repository.list_manageable(int(principal.user_id))
        except AuthorizationError:
            return _not_authorized()
        payload = serialize_dto(rows)
    return jsonify({"data": {"items": payload}})


@api_bp.post("/authorization/grants")
@login_required
@authorization_endpoint(
    EndpointMode.PROTECTED,
    Action.AUTHORIZATION_GRANTS_MANAGE,
    resolver="grant_target",
)
def create_authorization_grant():
    try:
        command = _parse_grant_create(_json_body())
    except (TypeError, ValueError):
        return _invalid_request()
    try:
        with transaction_scope() as db:
            repository, _decision, mutations = _services(db)
            grant = mutations.create(_principal_from_current_user(), command)
            payload = serialize_dto(repository.as_view(grant))
    except (AuthorizationError, PermissionError):
        return _not_authorized()
    except ValueError:
        return _invalid_request()
    return jsonify({"data": payload}), 201


@api_bp.patch("/authorization/grants/<int:grant_id>")
@login_required
@authorization_endpoint(
    EndpointMode.PROTECTED,
    Action.AUTHORIZATION_GRANTS_MANAGE,
    resolver="grant_target",
)
def update_authorization_grant(grant_id: int):
    try:
        command = _parse_grant_update(_json_body())
    except (TypeError, ValueError):
        return _invalid_request()
    try:
        with transaction_scope() as db:
            repository, _decision, mutations = _services(db)
            grant = mutations.update(_principal_from_current_user(), grant_id, command)
            payload = serialize_dto(repository.as_view(grant))
    except (AuthorizationError, PermissionError, LookupError):
        return _not_authorized()
    except ValueError:
        return _invalid_request()
    return jsonify({"data": payload})
