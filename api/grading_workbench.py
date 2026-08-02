from flask import jsonify, request, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from grading_workbench import service
from grading_workbench.errors import (
    InvalidWorkbenchTarget,
    WorkbenchAccessDenied,
    WorkbenchImageUnavailable,
    WorkbenchTargetNotFound,
)

from . import api_bp


@api_bp.route(
    "/grading-workbench/workspaces/task/<string:task_uuid>",
    methods=["GET"],
)
@roles_required("resident", "ophthalmologist", "admin")
def get_task_grading_workbench(task_uuid: str):
    slot = request.args.get("slot", "")
    try:
        with get_db_session() as db:
            workspace = service.resolve_task_workspace(
                db,
                user_id=current_user.id,
                task_uuid=task_uuid,
                slot=slot,
                image_url_builder=lambda image_uuid: url_for(
                    "media._imgForGradingByUUID",
                    uuid_str=image_uuid,
                ),
            )
    except InvalidWorkbenchTarget as exc:
        return jsonify({"error": "invalid_target", "message": str(exc)}), 400
    except WorkbenchTargetNotFound as exc:
        return jsonify({"error": "not_found", "message": str(exc)}), 404
    except WorkbenchAccessDenied as exc:
        return jsonify({"error": "access_denied", "message": str(exc)}), 403
    except WorkbenchImageUnavailable as exc:
        return jsonify({"error": "image_unavailable", "message": str(exc)}), 422

    response = jsonify(workspace.to_dict())
    response.headers["Cache-Control"] = "no-store, private"
    return response
