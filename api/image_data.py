# api/image_data.py
import os
from flask import jsonify, send_file, current_app
from sqlalchemy import select

from . import api_bp
from auth.roles import roles_required
from models import Session, EncounterFile, DirectImageUpload, EncounterFilePDF


@api_bp.route('/images/<uuid>/data', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist", "optometrist", "resident")
def get_image_data_by_uuid(uuid: str):
    """
    Serve image data for a specific image by its UUID.
    
    Args:
        uuid (str): UUID of the image
        
    Returns:
        Image file data with UUID as filename
    """
    with Session() as db:
        # Try to find the image in DirectImageUpload
        direct_image = db.execute(
            select(DirectImageUpload)
            .where(DirectImageUpload.uuid == uuid)
        ).scalar_one_or_none()

        if direct_image:
            # For DirectImageUpload, prefer edited images when available
            if direct_image.has_edited and direct_image.edited_filename:
                # Use edited image
                image_path = os.path.join(
                    current_app.config.get('DIRECT_UPLOAD_DIR', 'files/direct_uploads'),
                    direct_image.folder_rel,
                    'edited',
                    direct_image.edited_filename
                )
                # Determine file extension for edited image
                file_extension = os.path.splitext(direct_image.edited_filename)[1] or '.jpg'
            else:
                # Use original image
                image_path = os.path.join(
                    current_app.config.get('DIRECT_UPLOAD_DIR', 'files/direct_uploads'),
                    direct_image.folder_rel,
                    direct_image.filename
                )
                # Determine file extension for original image
                file_extension = os.path.splitext(direct_image.filename)[1] or '.jpg'
            
            # Check if file exists
            if os.path.exists(image_path):
                # Serve file with UUID as filename to prevent exposing original filename
                return send_file(image_path, as_attachment=True, download_name=f"{uuid}{file_extension}")
            else:
                return jsonify({"error": "Image file not found on disk"}), 404
        
        # If not found in DirectImageUpload, try EncounterFile
        encounter_file = db.execute(
            select(EncounterFile)
            .where(EncounterFile.uuid == uuid)
        ).scalar_one_or_none()

        if encounter_file:
            # Construct path for encounter file
            image_path = os.path.join(
                current_app.config.get('IMAGE_DIR', 'files/images'),
                f"{encounter_file.id}_{encounter_file.uuid}_{encounter_file.filename}"
            )
            
            # Determine file extension
            file_extension = os.path.splitext(encounter_file.filename)[1] or '.jpg'
            
            # Check if file exists
            if os.path.exists(image_path):
                # Serve file with UUID as filename to prevent exposing original filename
                return send_file(image_path, as_attachment=True, download_name=f"{uuid}{file_extension}")
            else:
                return jsonify({"error": "Image file not found on disk"}), 404
        
        # Image not found in database
        return jsonify({"error": "Image not found"}), 404