"""REST API for project-scoped grader allocation."""

from __future__ import annotations

from typing import Any

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from grading_allocation.constants import AllocationCapacity, AllocationScope
from grading_allocation.dashboard import list_project_encounter_set_queues
from grading_allocation.dtos import AllocationInputDTO
from grading_allocation.exceptions import GradingAllocationError
from grading_allocation import service
from db_transaction_manager import transaction_scope

from . import api_bp


MANAGER_ROLES = ("admin", "local_admin", "data_manager")
GRADER_ROLES = ("resident", "resident2", "ophthalmologist", "arbitrator", "admin")


@api_bp.route("/grading/project-encounter-set-queues", methods=["GET"])
@roles_required(*GRADER_ROLES)
def get_project_encounter_set_queues():
    """Return pending enforced-project EncounterSet queues eligible for the user."""
    with transaction_scope() as db:
        queues = list_project_encounter_set_queues(db, user_id=current_user.id)
        return jsonify(
            {
                "success": True,
                "queues": [queue.to_dict() for queue in queues],
            }
        )


@api_bp.route(
    "/projects/<int:project_id>/grader-allocation-candidates",
    methods=["GET"],
)
@roles_required(*MANAGER_ROLES)
def get_project_grader_allocation_candidates(project_id: int):
    """Return role-compatible users for one managed allocation lab/capacity."""
    try:
        lab_unit_id = _required_int(request.args, "lab_unit_id")
        try:
            capacity = AllocationCapacity(str(request.args.get("capacity") or ""))
        except ValueError as exc:
            raise GradingAllocationError(
                "capacity is invalid.",
                details={
                    "allowed_capacities": [item.value for item in AllocationCapacity]
                },
            ) from exc
        candidates = service.list_grader_candidates(
            current_user.id,
            project_id,
            lab_unit_id=lab_unit_id,
            capacity=capacity,
        )
        return jsonify(
            {
                "success": True,
                "candidates": [candidate.to_dict() for candidate in candidates],
            }
        )
    except GradingAllocationError as exc:
        return _error_response(exc)


@api_bp.route("/projects/<int:project_id>/grader-allocations", methods=["GET"])
@roles_required(*MANAGER_ROLES)
def get_project_grader_allocations(project_id: int):
    """Return policy, derived targets, coverage, and project allocations."""
    try:
        state = service.get_project_allocation_state(
            current_user.id,
            project_id,
            include_inactive=_bool_value(request.args.get("include_inactive"), default=False),
        )
        return jsonify({"success": True, **state.to_dict()})
    except GradingAllocationError as exc:
        return _error_response(exc)


@api_bp.route("/projects/<int:project_id>/grader-allocations", methods=["POST"])
@roles_required(*MANAGER_ROLES)
def create_project_grader_allocation(project_id: int):
    """Create or reactivate one normalized project grader allocation."""
    try:
        allocation = service.create_or_reactivate_allocation(
            current_user.id,
            project_id,
            _allocation_input(_json_object()),
        )
        return jsonify({"success": True, "allocation": allocation.to_dict()}), 201
    except GradingAllocationError as exc:
        return _error_response(exc)


@api_bp.route(
    "/projects/<int:project_id>/grader-allocations/<int:allocation_id>",
    methods=["PATCH"],
)
@roles_required(*MANAGER_ROLES)
def update_project_grader_allocation(project_id: int, allocation_id: int):
    """Activate or deactivate an existing allocation without deleting history."""
    try:
        data = _json_object()
        if "active" not in data:
            raise GradingAllocationError("The active field is required.")
        allocation = service.set_allocation_active(
            current_user.id,
            project_id,
            allocation_id,
            active=_bool_value(data.get("active"), default=False),
        )
        return jsonify({"success": True, "allocation": allocation.to_dict()})
    except GradingAllocationError as exc:
        return _error_response(exc)


@api_bp.route(
    "/projects/<int:project_id>/grader-allocations/<int:allocation_id>",
    methods=["DELETE"],
)
@roles_required(*MANAGER_ROLES)
def deactivate_project_grader_allocation(project_id: int, allocation_id: int):
    """Deactivate an allocation; historical rows are never deleted by the API."""
    try:
        allocation = service.set_allocation_active(
            current_user.id,
            project_id,
            allocation_id,
            active=False,
        )
        return jsonify({"success": True, "allocation": allocation.to_dict()})
    except GradingAllocationError as exc:
        return _error_response(exc)


@api_bp.route("/projects/<int:project_id>/grader-allocation-policy", methods=["PUT"])
@roles_required(*MANAGER_ROLES)
def update_project_grader_allocation_policy(project_id: int):
    """Atomically enable or disable project allocation enforcement."""
    try:
        data = _json_object()
        if "enforcement_enabled" not in data:
            raise GradingAllocationError("The enforcement_enabled field is required.")
        policy = service.set_project_enforcement(
            current_user.id,
            project_id,
            enabled=_bool_value(data.get("enforcement_enabled"), default=False),
        )
        return jsonify({"success": True, "policy": policy.to_dict()})
    except GradingAllocationError as exc:
        return _error_response(exc)


def _allocation_input(data: dict[str, Any]) -> AllocationInputDTO:
    user_id = _required_int(data, "user_id")
    lab_unit_id = _required_int(data, "lab_unit_id")
    disease_id = _optional_int(data.get("disease_id"), "disease_id")
    encounter_set_type_id = _optional_int(
        data.get("encounter_set_type_id"), "encounter_set_type_id"
    )
    try:
        scope = AllocationScope(str(data.get("scope") or ""))
        capacity = AllocationCapacity(str(data.get("capacity") or ""))
    except ValueError as exc:
        raise GradingAllocationError(
            "scope or capacity is invalid.",
            details={
                "allowed_scopes": [scope.value for scope in AllocationScope],
                "allowed_capacities": [capacity.value for capacity in AllocationCapacity],
            },
        ) from exc
    return AllocationInputDTO(
        user_id=user_id,
        lab_unit_id=lab_unit_id,
        scope=scope,
        capacity=capacity,
        disease_id=disease_id,
        encounter_set_type_id=encounter_set_type_id,
    )


def _json_object() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise GradingAllocationError("A JSON object request body is required.")
    return data


def _required_int(data: dict[str, Any], key: str) -> int:
    value = _optional_int(data.get(key), key)
    if value is None:
        raise GradingAllocationError(f"{key} is required.")
    return value


def _optional_int(value: Any, key: str) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise GradingAllocationError(f"{key} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise GradingAllocationError(f"{key} must be an integer.") from exc
    if parsed < 1:
        raise GradingAllocationError(f"{key} must be a positive integer.")
    return parsed


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise GradingAllocationError("Boolean fields must contain true or false.")


def _error_response(exc: GradingAllocationError):
    return (
        jsonify(
            {
                "success": False,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
            }
        ),
        exc.status_code,
    )
