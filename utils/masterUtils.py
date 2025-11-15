"""
Master utility functions for retrieving core entities like diseases, hospitals, lab units, etc.
"""

from typing import List, Dict, Any, Optional
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from db_transaction_manager import get_db_session
from models import Disease, DiseaseGrading, Hospital, LabUnit, Area, Camera


def get_all_diseases() -> List[Dict[str, Any]]:
    """
    Get all diseases in the system.
    
    Returns:
        List of dictionaries containing disease information
    """
    with get_db_session() as db:
        diseases = db.query(Disease).all()
        return [
            {
                'id': disease.id,
                'name': disease.name
            }
            for disease in diseases
        ]


def get_disease_gradings(disease_id: int) -> List[Dict[str, Any]]:
    """
    Get all active gradings for a specific disease.
    
    Args:
        disease_id: The ID of the disease
        
    Returns:
        List of dictionaries containing disease grading information
    """
    with get_db_session() as db:
        gradings = db.query(DiseaseGrading).filter(
            DiseaseGrading.disease_id == disease_id,
            DiseaseGrading.is_active == True
        ).order_by(DiseaseGrading.display_order).all()
        
        return [
            {
                'id': grading.id,
                'disease_id': grading.disease_id,
                'impression': grading.impression,
                'display_order': grading.display_order,
                'is_active': grading.is_active,
                'guidelines': grading.guidelines
            }
            for grading in gradings
        ]


def fetch_active_disease_gradings(db, disease_id: int):
    """
    Fetch all active disease gradings for a disease, ordered by display order.
    
    Args:
        db: Database session
        disease_id: The ID of the disease
        
    Returns:
        List of active DiseaseGrading objects ordered by display order
    """
    return (
        db.query(DiseaseGrading)
        .options(selectinload(DiseaseGrading.features))
        .filter(
            DiseaseGrading.disease_id == disease_id,
            DiseaseGrading.is_active == True,
        )
        .order_by(DiseaseGrading.display_order)
        .all()
    )


def get_all_hospitals() -> List[Dict[str, Any]]:
    """
    Get all hospitals in the system.
    
    Returns:
        List of dictionaries containing hospital information
    """
    with get_db_session() as db:
        hospitals = db.query(Hospital).all()
        return [
            {
                'id': hospital.id,
                'name': hospital.name
            }
            for hospital in hospitals
        ]


def get_all_lab_units() -> List[Dict[str, Any]]:
    """
    Get all lab units in the system.
    
    Returns:
        List of dictionaries containing lab unit information
    """
    with get_db_session() as db:
        lab_units = db.query(LabUnit).options(selectinload(LabUnit.hospital)).all()
        return [
            {
                'id': lab_unit.id,
                'name': lab_unit.name,
                'hospital_id': lab_unit.hospital_id,
                'hospital_name': lab_unit.hospital.name if lab_unit.hospital else None
            }
            for lab_unit in lab_units
        ]


def get_hosp_lab_units(hospital_id: int) -> List[Dict[str, Any]]:
    """
    Get all lab units for a specific hospital.
    
    Args:
        hospital_id: The ID of the hospital
        
    Returns:
        List of dictionaries containing lab unit information
    """
    with get_db_session() as db:
        lab_units = db.query(LabUnit).filter(
            LabUnit.hospital_id == hospital_id
        ).all()
        return [
            {
                'id': lab_unit.id,
                'name': lab_unit.name,
                'hospital_id': lab_unit.hospital_id
            }
            for lab_unit in lab_units
        ]


def get_all_areas() -> List[Dict[str, Any]]:
    """
    Get all areas in the system.
    
    Returns:
        List of dictionaries containing area information
    """
    with get_db_session() as db:
        areas = db.query(Area).all()
        return [
            {
                'id': area.id,
                'name': area.name
            }
            for area in areas
        ]


def get_all_cameras() -> List[Dict[str, Any]]:
    """
    Get all cameras in the system.
    
    Returns:
        List of dictionaries containing camera information
    """
    with get_db_session() as db:
        cameras = db.query(Camera).all()
        return [
            {
                'id': camera.id,
                'name': camera.name
            }
            for camera in cameras
        ]
