# api/image_metadata.py
from flask import jsonify
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import api_bp
from auth.roles import roles_required
from models import Session, EncounterFile, DirectImageUpload, EncounterFilePDF, PatientEncounters, LabUnit


@api_bp.route('/images/<uuid>/metadata', methods=['GET'])
@roles_required("admin", "data_manager", "ophthalmologist", "optometrist", "resident")
def get_image_metadata_by_uuid(uuid: str):
    """
    Get metadata for a specific image by its UUID.
    Does not return file paths or original filenames for security.
    
    Args:
        uuid (str): UUID of the image
        
    Returns:
        JSON response with image metadata only
    """
    with Session() as db:
        # Try to find the image in DirectImageUpload
        direct_image = db.execute(
            select(DirectImageUpload)
            .options(
                selectinload(DirectImageUpload.hospital),
                selectinload(DirectImageUpload.lab_unit),
                selectinload(DirectImageUpload.disease),
                selectinload(DirectImageUpload.camera),
                selectinload(DirectImageUpload.area),
                selectinload(DirectImageUpload.uploader)
            )
            .where(DirectImageUpload.uuid == uuid)
        ).scalar_one_or_none()

        if direct_image:
            # Return metadata without file paths
            return jsonify({
                "type": "direct_upload",
                "uuid": direct_image.uuid,
                "source": "DirectUpload",
                "has_edited": direct_image.has_edited,
                "is_mydriatic": direct_image.is_mydriatic,
                "created_at": direct_image.created_at.isoformat() if direct_image.created_at else None,
                "hospital": {
                    "id": direct_image.hospital.id,
                    "name": direct_image.hospital.name
                } if direct_image.hospital else None,
                "lab_unit": {
                    "id": direct_image.lab_unit.id,
                    "name": direct_image.lab_unit.name
                } if direct_image.lab_unit else None,
                "disease": {
                    "id": direct_image.disease.id,
                    "name": direct_image.disease.name
                } if direct_image.disease else None,
                "camera": {
                    "id": direct_image.camera.id,
                    "name": direct_image.camera.name
                } if direct_image.camera else None,
                "area": {
                    "id": direct_image.area.id,
                    "name": direct_image.area.name
                } if direct_image.area else None,
                "uploader": {
                    "id": direct_image.uploader.id,
                    "full_name": direct_image.uploader.full_name
                } if direct_image.uploader else None,
                "capture_date": direct_image.patient_encounter.capture_date_dt.isoformat() if 
                               (direct_image.patient_encounter and direct_image.patient_encounter.capture_date_dt) else None
            })
        
        # If not found in DirectImageUpload, try EncounterFile
        encounter_file = db.execute(
            select(EncounterFile)
            .options(
                selectinload(EncounterFile.patient_encounter)
                .selectinload(PatientEncounters.lab_unit)
                .selectinload(LabUnit.hospital)
            )
            .where(EncounterFile.uuid == uuid)
        ).scalar_one_or_none()

        if encounter_file:
            # Get hospital and lab unit info from patient encounter
            hospital = None
            lab_unit = None
            capture_date = None
            
            if encounter_file.patient_encounter:
                if encounter_file.patient_encounter.lab_unit:
                    lab_unit = encounter_file.patient_encounter.lab_unit
                    if lab_unit.hospital:
                        hospital = lab_unit.hospital
                capture_date = encounter_file.patient_encounter.capture_date_dt
                
            return jsonify({
                "type": "encounter_file",
                "uuid": encounter_file.uuid,
                "source": "RemedioZip",
                "filename": encounter_file.filename,
                "file_type": encounter_file.file_type,
                "eye_side": encounter_file.eye_side,
                "created_at": encounter_file.created_at.isoformat() if getattr(encounter_file, 'created_at', None) else None,
                "hospital": {
                    "id": hospital.id,
                    "name": hospital.name
                } if hospital else None,
                "lab_unit": {
                    "id": lab_unit.id,
                    "name": lab_unit.name
                } if lab_unit else None,
                "capture_date": capture_date.isoformat() if capture_date else None
            })
        
        # If not found in EncounterFile, try EncounterFilePDF
        pdf_file = db.execute(
            select(EncounterFilePDF)
            .options(
                selectinload(EncounterFilePDF.patient_encounter)
                .selectinload(PatientEncounters.lab_unit)
                .selectinload(LabUnit.hospital)
            )
            .where(EncounterFilePDF.uuid == uuid)
        ).scalar_one_or_none()

        if pdf_file:
            # Get hospital and lab unit info from patient encounter
            hospital = None
            lab_unit = None
            capture_date = None
            
            if pdf_file.patient_encounter:
                if pdf_file.patient_encounter.lab_unit:
                    lab_unit = pdf_file.patient_encounter.lab_unit
                    if lab_unit.hospital:
                        hospital = lab_unit.hospital
                capture_date = pdf_file.patient_encounter.capture_date_dt
                
            return jsonify({
                "type": "encounter_pdf",
                "uuid": pdf_file.uuid,
                "source": "RemedioZip",
                "filename": pdf_file.filename,
                "file_type": pdf_file.file_type,
                "eye_side": pdf_file.eye_side,
                "created_at": pdf_file.created_at.isoformat() if getattr(pdf_file, 'created_at', None) else None,
                "hospital": {
                    "id": hospital.id,
                    "name": hospital.name
                } if hospital else None,
                "lab_unit": {
                    "id": lab_unit.id,
                    "name": lab_unit.name
                } if lab_unit else None,
                "capture_date": capture_date.isoformat() if capture_date else None
            })
        
        # Image not found
        return jsonify({"error": "Image not found"}), 404