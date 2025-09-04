from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

# Import all route handlers
from .dashboard import index
from .glaucoma import glaucoma_image, glaucoma_grade, glaucoma_remove
from .dr import dr_image, dr_grade, dr_remove
from .glaucoma_direct import direct_image, direct_glaucoma_grade, direct_glaucoma_remove

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET", "POST"])
bp.add_url_rule("/glaucoma/image/<uuid>", view_func=glaucoma_image, methods=["GET"])
bp.add_url_rule("/glaucoma/grade", view_func=glaucoma_grade, methods=["POST"])
bp.add_url_rule("/glaucoma/remove", view_func=glaucoma_remove, methods=["POST"])
bp.add_url_rule("/dr/image/<uuid>", view_func=dr_image, methods=["GET"])
bp.add_url_rule("/dr/grade", view_func=dr_grade, methods=["POST"])
bp.add_url_rule("/dr/remove", view_func=dr_remove, methods=["POST"])
bp.add_url_rule("/direct/<uuid>", view_func=direct_image, methods=["GET"])
bp.add_url_rule("/direct/glaucoma/grade", view_func=direct_glaucoma_grade, methods=["POST"])
bp.add_url_rule("/direct/glaucoma/remove", view_func=direct_glaucoma_remove, methods=["POST"])

