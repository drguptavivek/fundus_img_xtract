from flask import abort, render_template, url_for
from flask_login import current_user

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from grading_workbench import service
from grading_workbench.assets import get_workbench_assets
from grading_workbench.errors import (
    InvalidWorkbenchTarget,
    WorkbenchAccessDenied,
    WorkbenchImageUnavailable,
    WorkbenchTargetNotFound,
)


def register_routes(bp):
    bp.add_url_rule(
        "/workbench/task/<string:task_uuid>/<string:slot>",
        view_func=standalone_task_workbench,
        methods=["GET"],
    )


@roles_required("resident", "ophthalmologist", "admin")
def standalone_task_workbench(task_uuid: str, slot: str):
    try:
        with get_db_session() as db:
            service.resolve_task_workspace(
                db,
                user_id=current_user.id,
                task_uuid=task_uuid,
                slot=slot,
                image_url_builder=lambda image_uuid: url_for(
                    "media._imgForGradingByUUID",
                    uuid_str=image_uuid,
                ),
            )
        assets = get_workbench_assets()
    except InvalidWorkbenchTarget as exc:
        abort(400, description=str(exc))
    except WorkbenchTargetNotFound as exc:
        abort(404, description=str(exc))
    except WorkbenchAccessDenied as exc:
        abort(403, description=str(exc))
    except WorkbenchImageUnavailable as exc:
        abort(422, description=str(exc))
    except RuntimeError as exc:
        abort(503, description=str(exc))

    response = render_template(
        "grading/workbench.html",
        task_uuid=task_uuid,
        slot=slot,
        workspace_url=url_for(
            "fundus_api.get_task_grading_workbench",
            task_uuid=task_uuid,
            slot=slot,
        ),
        workbench_script=assets["script"],
        workbench_styles=assets["styles"],
    )
    return response, 200, {
        "Cache-Control": "no-cache, no-store, must-revalidate, private",
    }
