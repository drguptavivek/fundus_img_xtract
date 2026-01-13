"""
Test data factories for creating valid model instances in tests.

These factories handle all required fields and relationships to create
valid test data that satisfies database constraints.
"""

import hashlib
from datetime import date, datetime, timezone
from typing import Optional
from models import (
    ZipFile,
    PatientEncounters,
    EncounterFile,
    DirectImageUpload,
    GradingTask,
    LabUnit,
)


class TestDataFactory:
    """Factory for creating test data with all required fields."""
    
    _counter = 0
    
    @classmethod
    def _get_unique_id(cls) -> int:
        """Get a unique counter for generating unique values."""
        cls._counter += 1
        return cls._counter
    
    @classmethod
    def create_zip_file(
        cls,
        db_session,
        zip_filename: Optional[str] = None,
        md5_hash: Optional[str] = None,
    ) -> ZipFile:
        """
        Create a ZipFile instance with all required fields.
        
        Args:
            db_session: Database session
            zip_filename: Optional filename (auto-generated if not provided)
            md5_hash: Optional MD5 hash (auto-generated if not provided)
            
        Returns:
            ZipFile instance
        """
        unique_id = cls._get_unique_id()
        
        if not zip_filename:
            zip_filename = f"test_zip_{unique_id}.zip"
        
        if not md5_hash:
            # Generate a unique MD5 hash
            md5_hash = hashlib.md5(f"test_data_{unique_id}".encode()).hexdigest()
        
        zip_file = ZipFile(
            zip_filename=zip_filename,
            md5_hash=md5_hash,
            upload_date=date.today(),
        )
        db_session.add(zip_file)
        db_session.flush()
        return zip_file
    
    @classmethod
    def create_patient_encounter(
        cls,
        db_session,
        lab_unit_id: int,
        patient_id: Optional[str] = None,
        name: Optional[str] = None,
        capture_date: Optional[str] = None,
        capture_date_dt: Optional[date] = None,
        zip_file: Optional[ZipFile] = None,
    ) -> PatientEncounters:
        """
        Create a PatientEncounters instance with all required fields.
        
        Args:
            db_session: Database session
            lab_unit_id: Lab unit ID (required)
            patient_id: Patient ID (auto-generated if not provided)
            name: Patient name (auto-generated if not provided)
            capture_date: Capture date string (auto-generated if not provided)
            capture_date_dt: Capture date (defaults to today)
            zip_file: Associated ZipFile (auto-created if not provided)
            
        Returns:
            PatientEncounters instance
        """
        unique_id = cls._get_unique_id()
        
        # Create zip file if not provided
        if not zip_file:
            zip_file = cls.create_zip_file(db_session)
        
        if not patient_id:
            patient_id = f"TEST_PATIENT_{unique_id}"
        
        if not name:
            name = f"Test Patient {unique_id}"
        
        if not capture_date_dt:
            capture_date_dt = date.today()
        
        if not capture_date:
            capture_date = capture_date_dt.isoformat()
        
        encounter = PatientEncounters(
            zip_file_id=zip_file.id,
            patient_id=patient_id,
            name=name,
            capture_date=capture_date,
            capture_date_dt=capture_date_dt,
            lab_unit_id=lab_unit_id,
        )
        db_session.add(encounter)
        db_session.flush()
        return encounter
    
    @classmethod
    def create_encounter_file(
        cls,
        db_session,
        patient_encounter_id: int,
        lab_unit_id: int,
        filename: Optional[str] = None,
        file_type: str = "image",
    ) -> EncounterFile:
        """
        Create an EncounterFile instance.
        
        Args:
            db_session: Database session
            patient_encounter_id: Patient encounter ID
            lab_unit_id: Lab unit ID
            filename: Filename (auto-generated if not provided)
            file_type: File type (default: "image")
            
        Returns:
            EncounterFile instance
        """
        unique_id = cls._get_unique_id()
        
        if not filename:
            filename = f"test_image_{unique_id}.jpg"
        
        encounter_file = EncounterFile(
            patient_encounter_id=patient_encounter_id,
            lab_unit_id=lab_unit_id,
            filename=filename,
            file_type=file_type,
        )
        db_session.add(encounter_file)
        db_session.flush()
        return encounter_file
    
    @classmethod
    def create_direct_image_upload(
        cls,
        db_session,
        lab_unit_id: int,
        uploader_id: int,
        hospital_id: int,
        camera_id: int,
        disease_id: int,
        area_id: int,
        filename: Optional[str] = None,
        folder_rel: Optional[str] = None,
        file_hash: Optional[str] = None,
    ) -> DirectImageUpload:
        """
        Create a DirectImageUpload instance with all required fields.
        
        Args:
            db_session: Database session
            lab_unit_id: Lab unit ID (required)
            uploader_id: Uploader user ID (required)
            hospital_id: Hospital ID (required)
            camera_id: Camera ID (required)
            disease_id: Disease ID (required)
            area_id: Area ID (required)
            filename: Filename (auto-generated if not provided)
            folder_rel: Relative folder path (auto-generated if not provided)
            file_hash: File hash (auto-generated if not provided)
            
        Returns:
            DirectImageUpload instance
        """
        unique_id = cls._get_unique_id()
        
        if not filename:
            filename = f"direct_upload_{unique_id}.jpg"
        
        if not folder_rel:
            # Create a valid POSIX-style relative path (no leading slash)
            folder_rel = f"files/direct_uploads/test_{unique_id}"
        
        if not file_hash:
            # Generate a unique MD5 hash
            file_hash = hashlib.md5(f"direct_file_{unique_id}".encode()).hexdigest()
        
        direct_upload = DirectImageUpload(
            lab_unit_id=lab_unit_id,
            uploader_id=uploader_id,
            hospital_id=hospital_id,
            camera_id=camera_id,
            disease_id=disease_id,
            area_id=area_id,
            filename=filename,
            folder_rel=folder_rel,
            file_hash=file_hash,
        )
        db_session.add(direct_upload)
        db_session.flush()
        return direct_upload
    
    @classmethod
    def create_grading_task(
        cls,
        db_session,
        lab_unit_id: int,
        disease_id: int,
        encounter_file_id: Optional[int] = None,
        direct_image_upload_id: Optional[int] = None,
        state: str = "pending",
    ) -> GradingTask:
        """
        Create a GradingTask instance.
        
        Args:
            db_session: Database session
            lab_unit_id: Lab unit ID
            disease_id: Disease ID
            encounter_file_id: Encounter file ID (one of encounter_file_id or direct_image_upload_id required)
            direct_image_upload_id: Direct image upload ID
            state: Task state (default: "pending")
            
        Returns:
            GradingTask instance
        """
        task = GradingTask(
            lab_unit_id=lab_unit_id,
            disease_id=disease_id,
            encounter_file_id=encounter_file_id,
            direct_image_upload_id=direct_image_upload_id,
            state=state,
        )
        db_session.add(task)
        db_session.flush()
        return task
