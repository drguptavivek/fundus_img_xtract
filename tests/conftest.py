import pytest
from models import (
    Session, DirectImageUpload, EncounterFile, PatientEncounters, 
    Disease, LabUnit, Hospital, Camera, Area, ZipFile
)
import uuid
from datetime import datetime


@pytest.fixture
def setup_test_data():
    """Create test data for task creation service tests."""
    db = Session()
    try:
        # Create test hospital
        hospital = Hospital(name="Test Hospital")
        db.add(hospital)
        db.flush()
        
        # Create test lab unit
        lab_unit = LabUnit(name="Test Lab Unit", hospital_id=hospital.id)
        db.add(lab_unit)
        db.flush()
        
        # Create test camera
        camera = Camera(name="Test Camera")
        db.add(camera)
        db.flush()
        
        # Create test area
        area = Area(name="Test Area")
        db.add(area)
        db.flush()
        
        # Create test diseases
        disease = Disease(name="Test Disease")
        db.add(disease)
        db.flush()
        
        dr_disease = Disease(name="Diabetic Retinopathy")
        db.add(dr_disease)
        db.flush()
        
        glaucoma_disease = Disease(name="Glaucoma")
        db.add(glaucoma_disease)
        db.flush()
        
        # Create test zip file
        zip_file = ZipFile(
            zip_filename="test.zip",
            md5_hash="test_hash"
        )
        db.add(zip_file)
        db.flush()
        
        # Create test encounter
        encounter = PatientEncounters(
            zip_file_id=zip_file.id,
            name="Test Patient",
            patient_id="TEST001",
            capture_date="2023-01-01"
        )
        db.add(encounter)
        db.flush()
        
        # Create test encounter file
        encounter_file = EncounterFile(
            patient_encounter_id=encounter.id,
            filename="test_image.png",
            file_type="image/png",
            uuid=str(uuid.uuid4())
        )
        db.add(encounter_file)
        db.flush()
        
        # Add encounter file to encounter
        encounter.encounter_files = [encounter_file]
        
        # Create test direct image upload
        direct_image = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            filename="direct_test.png",
            folder_rel="test_folder",
            file_hash="direct_test_hash",
            uploader_id=1,  # Assuming a default user ID
            hospital_id=hospital.id,
            lab_unit_id=lab_unit.id,
            camera_id=camera.id,
            disease_id=disease.id,
            area_id=area.id,
            is_mydriatic=False
        )
        db.add(direct_image)
        db.flush()
        
        db.commit()
        
        test_data = {
            'hospital': hospital,
            'lab_unit': lab_unit,
            'camera': camera,
            'area': area,
            'disease': disease,
            'dr_disease': dr_disease,
            'glaucoma_disease': glaucoma_disease,
            'zip_file': zip_file,
            'encounter': encounter,
            'encounter_file': encounter_file,
            'direct_image': direct_image
        }
        
        yield db, test_data
        
    finally:
        # Cleanup
        db.rollback()
        db.close()