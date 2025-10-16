from flask import jsonify
from flask_login import login_required
from models import AIModel, Session
from auth.roles import roles_required
from . import api_bp


@api_bp.route("/ai-models", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def get_ai_models():
    """API endpoint to get all AI models."""
    db = Session()
    try:
        # Get all AI models
        ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
        
        # Format the results
        models = [
            {
                'id': model.id,
                'name': model.name,
                'version': model.version,
                'description': model.description,
                'display_name': f"{model.name} v{model.version}"
            } 
            for model in ai_models
        ]
        
        return jsonify({'models': models})
    finally:
        db.close()