# api/gradings.py
from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload

from . import api_bp
from auth.roles import roles_required
from models import Session, EncounterFile, DirectImageUpload, ImageGrading


@api_bp.route('/gradings/by-image-uuid/<uuid>', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist")
def get_gradings_by_image_uuid(uuid: str):
    """Get all gradings for a specific image by its UUID."""
    with Session() as db:
        # First, try to find the image in EncounterFile
        encounter_file = db.execute(
            select(EncounterFile)
            .options(selectinload(EncounterFile.gradings).selectinload(ImageGrading.grader))
            .where(EncounterFile.uuid == uuid)
        ).scalar_one_or_none()

        if encounter_file:
            gradings = encounter_file.gradings
        else:
            # If not found, try to find it in DirectImageUpload
            direct_image_upload = db.execute(
                select(DirectImageUpload)
                .options(selectinload(DirectImageUpload.gradings).selectinload(ImageGrading.grader))
                .where(DirectImageUpload.uuid == uuid)
            ).scalar_one_or_none()

            if not direct_image_upload:
                return jsonify({"error": "Image not found"}), 404
            gradings = direct_image_upload.gradings

        return jsonify([
            {
                "id": g.id,
                "grader_user_id": g.grader_user_id,
                "grader_username": g.grader.username if g.grader else g.grader_username,
                "grader_full_name": g.grader.full_name if g.grader else None,
                "grader_role": g.grader_role,
                "graded_for": g.graded_for,
                "impression": g.impression,
                "remarks": g.remarks,
                "created_at": g.created_at.isoformat(),
                "updated_at": g.updated_at.isoformat(),
            }
            for g in sorted(gradings, key=lambda x: x.updated_at, reverse=True)
        ])
