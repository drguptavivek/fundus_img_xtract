"""REST reads for mutable EncounterSet policy and frozen grading records."""
from __future__ import annotations

from flask import jsonify
from flask_login import current_user
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from encounter_sets.grading_policy import effective_project_policy_dto
from encounter_sets.grading_records import package_record_dto, reconcile_package_state
from grading_allocation import service as grading_allocation_service
from grading_allocation.exceptions import GradingAllocationError
from models import (
    EncounterSetGradingPackage,
    EncounterSetGradingScope,
    EncounterSetGradingSubmission,
    EncounterSetGradingSubmissionItem,
    Grade,
    GradingTask,
    PatientEncounters,
)
from utils.hospital_scoping import apply_scoping

from . import api_bp


MANAGER_ROLES = ("admin", "local_admin", "data_manager")
GRADING_ROLES = (
    "resident",
    "ophthalmologist",
)


@api_bp.route(
    "/projects/<int:project_id>/effective-encounter-set-grading-plan",
    methods=["GET"],
)
@roles_required(*MANAGER_ROLES)
def get_effective_encounter_set_grading_plan(project_id: int):
    """Return future task policy inferred from every active profile."""
    try:
        allocation_state = grading_allocation_service.get_project_allocation_state(
            current_user.id, project_id, include_inactive=False
        )
    except GradingAllocationError as exc:
        return jsonify({"success": False, "error": exc.message}), exc.status_code
    with transaction_scope() as db:
        plan = effective_project_policy_dto(db, project_id)
        return jsonify({
            "success": True,
            **plan,
            "allocation_targets": list(allocation_state.targets),
        })


@api_bp.route(
    "/encounter-sets/<string:encounter_uuid>/grading-records", methods=["GET"]
)
@roles_required(*GRADING_ROLES)
def get_encounter_set_grading_records(encounter_uuid: str):
    """Return frozen package, scope, submission, image-grade, and consensus history."""
    with transaction_scope() as db:
        query = db.query(PatientEncounters).filter(
            PatientEncounters.uuid == encounter_uuid,
            PatientEncounters.is_set_based.is_(True),
        )
        query = apply_scoping(query, PatientEncounters, current_user, "grading")
        encounter = query.first()
        if encounter is None:
            return jsonify({"success": False, "error": "EncounterSet not found."}), 404
        packages = (
            db.query(EncounterSetGradingPackage)
            .options(
                selectinload(EncounterSetGradingPackage.patient_encounter),
                selectinload(EncounterSetGradingPackage.submissions)
                .selectinload(EncounterSetGradingSubmission.items),
                selectinload(EncounterSetGradingPackage.scopes)
                .selectinload(EncounterSetGradingScope.tasks)
                .selectinload(GradingTask.encounter_set_image),
                selectinload(EncounterSetGradingPackage.scopes)
                .selectinload(EncounterSetGradingScope.tasks)
                .selectinload(GradingTask.grades),
                selectinload(EncounterSetGradingPackage.scopes)
                .selectinload(EncounterSetGradingScope.tasks)
                .selectinload(GradingTask.consensus),
            )
            .filter(EncounterSetGradingPackage.patient_encounter_id == encounter.id)
            .order_by(EncounterSetGradingPackage.id)
            .with_for_update()
            .all()
        )
        for package in packages:
            reconcile_package_state(db, package)
        return jsonify({
            "success": True,
            "encounter_uuid": encounter.uuid,
            "packages": [
                package_record_dto(package, viewer_user_id=current_user.id)
                for package in packages
            ],
        })
