from flask import Blueprint

bp = Blueprint("grading", __name__, url_prefix="/grading")

# Import all route handlers
from .dashboard import index
from .remedio_glaucoma import remedio_glaucoma_image, remedio_glaucoma_grade, remedio_glaucoma_remove
from .glaucoma_direct import direct_image, direct_glaucoma_grade, direct_glaucoma_remove
from .remedio_dr import remedio_dr_image, remedio_dr_grade, remedio_dr_remove
from .direct_disease import direct_disease_image, direct_disease_grade, direct_disease_remove
from .arbitration import arbitration_dashboard, arbitration_image, arbitration_grade

# Register routes with the blueprint
bp.add_url_rule("/", view_func=index, methods=["GET"])

# Glaucoma grading routes for Remed.io ZIP files
bp.add_url_rule("/remedio/glaucoma/<uuid>", view_func=remedio_glaucoma_image, methods=["GET"])
bp.add_url_rule("/remedio/glaucoma/grade", view_func=remedio_glaucoma_grade, methods=["POST"])
bp.add_url_rule("/remedio/glaucoma/remove", view_func=remedio_glaucoma_remove, methods=["POST"])

# Glaucoma grading routes for direct uploads
bp.add_url_rule("/direct/<uuid>", view_func=direct_image, methods=["GET"])
bp.add_url_rule("/direct/glaucoma/grade", view_func=direct_glaucoma_grade, methods=["POST"])
bp.add_url_rule("/direct/glaucoma/remove", view_func=direct_glaucoma_remove, methods=["POST"])

# DR grading routes for Remed.io ZIP files
bp.add_url_rule("/remedio/dr/<uuid>", view_func=remedio_dr_image, methods=["GET"])
bp.add_url_rule("/remedio/dr/grade", view_func=remedio_dr_grade, methods=["POST"])
bp.add_url_rule("/remedio/dr/remove", view_func=remedio_dr_remove, methods=["POST"])

# Disease grading routes for direct uploads
bp.add_url_rule("/direct/disease/<uuid>/<int:disease_id>", view_func=direct_disease_image, methods=["GET"])
bp.add_url_rule("/direct/disease/grade", view_func=direct_disease_grade, methods=["POST"])
bp.add_url_rule("/direct/disease/remove", view_func=direct_disease_remove, methods=["POST"])

# Arbitration routes
bp.add_url_rule("/arbitration", view_func=arbitration_dashboard, methods=["GET"])
bp.add_url_rule("/arbitration/<uuid>", view_func=arbitration_image, methods=["GET"])
bp.add_url_rule("/arbitration/grade", view_func=arbitration_grade, methods=["POST"])

