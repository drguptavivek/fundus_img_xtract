from flask import jsonify
from flask_login import login_required
from sqlalchemy.orm import selectinload

from models import AIModel
from auth.roles import roles_required
from utils.utils import get_db_session
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
