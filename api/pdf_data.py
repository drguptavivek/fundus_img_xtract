# api/pdf_data.py
import os
from flask import jsonify, send_file, current_app
from sqlalchemy import select

from . import api_bp
from auth.roles import roles_required
from models import Session, EncounterFilePDF


@api_bp.route('/pdfs/<uuid>/data', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist", "optometrist", "resident")
def get_pdf_data_by_uuid(uuid: str):
    """
    Serve PDF data for a specific PDF by its UUID.
    
    Args:
        uuid (str): UUID of the PDF
        
    Returns:
        PDF file data with UUID as filename
    """
    with Session() as db:
        # Try to find the PDF in EncounterFilePDF
        pdf_file = db.execute(
            select(EncounterFilePDF)
            .where(EncounterFilePDF.uuid == uuid)
        ).scalar_one_or_none()

        if pdf_file:
            # Construct path for PDF file
            pdf_path = os.path.join(
                current_app.config.get('PDF_DIR', 'files/pdfs'),
                f"{pdf_file.id}_{pdf_file.uuid}_{pdf_file.filename}"
            )
            
            # Check if file exists
            if os.path.exists(pdf_path):
                # Serve file with UUID as filename to prevent exposing original filename
                return send_file(pdf_path, as_attachment=True, download_name=f"{uuid}.pdf")
            else:
                return jsonify({"error": "PDF file not found on disk"}), 404
        
        # PDF not found in database
        return jsonify({"error": "PDF not found"}), 404