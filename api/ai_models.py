from flask import jsonify, request
from flask_login import current_user
from sqlalchemy.orm import selectinload

from models import AIModel
from auth.roles import roles_required
from utils.utils import get_db_session
from services.wadhwani_glaucoma_inference import run_task_inference
from . import api_bp


@api_bp.route("/ai-models", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "optometrist")
def get_ai_models():
    """API endpoint to get all AI models."""
    with get_db_session() as db:
        # Get all AI models
        ai_models = (
            db.query(AIModel)
            .options(selectinload(AIModel.integration))
            .order_by(AIModel.name, AIModel.version)
            .all()
        )
        
        # Format the results
        models = [
            {
                'id': model.id,
                'name': model.name,
                'version': model.version,
                'description': model.description,
                'display_name': f"{model.name} v{model.version}",
                'integration_provider': model.integration.provider if model.integration else None,
                'is_wadhwani_glaucoma_linked': bool(
                    model.integration and model.integration.provider == "wadhwani_glaucoma"
                ),
            } 
            for model in ai_models
        ]
        
        return jsonify({'models': models})


@api_bp.route("/ai-models/wadhwani-glaucoma/tasks/<int:task_id>/infer", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def infer_wadhwani_glaucoma_task(task_id: int):
    payload = request.get_json(silent=True) or {}
    force = bool(payload.get("force", False))
    result = run_task_inference(
        task_id=task_id,
        requested_by_user_id=current_user.id if getattr(current_user, "is_authenticated", False) else None,
        force=force,
    )
    body = {
        "success": result.status in {"success", "skipped"},
        "task_id": result.task_id,
        "ai_model_id": result.ai_model_id,
        "inference_run_id": result.inference_run_id,
        "grade_id": result.grade_id,
        "status": result.status,
        "message": result.message,
        "reused_existing_grade": result.reused_existing_grade,
        "prediction_id": result.prediction_id,
        "confidence": result.confidence,
        "predicted_class": result.predicted_class,
        "predicted_class_name": result.predicted_class_name,
        "grade_impression": result.grade_impression,
        "error_code": result.error_code,
    }
    status_code = 200 if body["success"] else 400
    return jsonify(body), status_code
