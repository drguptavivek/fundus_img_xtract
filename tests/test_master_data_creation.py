"""Test master data creation for Hospitals, LabUnits, Diseases, Camera, and Area."""

import pytest
import sys
import os
# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Session, Hospital, LabUnit, Camera, Disease, Area
from sqlalchemy import select
from tests.test_setup import setup_test_environment


class TestMasterDataCreation:
    """Test cases for creating master data."""

    @classmethod
    def setup_class(cls):
        """Set up test environment before running tests."""
        cls.test_env = setup_test_environment()

    def test_hospitals_created(self):
        """Test that hospitals are created correctly."""
        with Session() as db:
            hospitals = db.execute(select(Hospital)).scalars().all()
            # Should have at least 3 hospitals as per requirements
            assert len(hospitals) >= 3
            
            # Check for specific hospitals
            hospital_names = [h.name for h in hospitals]
            assert 'City Hospital' in hospital_names
            assert 'University Medical Center' in hospital_names
            assert 'Community Eye Clinic' in hospital_names

    def test_lab_units_created(self):
        """Test that lab units are created correctly."""
        with Session() as db:
            lab_units = db.execute(select(LabUnit)).scalars().all()
            # Should have at least 6 lab units as per requirements
            assert len(lab_units) >= 6
            
            # Check that lab units are associated with hospitals
            for lab_unit in lab_units:
                assert lab_unit.hospital_id is not None
                assert lab_unit.hospital is not None

    def test_cameras_created(self):
        """Test that cameras are created correctly."""
        with Session() as db:
            cameras = db.execute(select(Camera)).scalars().all()
            # Should have at least 5 cameras as per requirements
            assert len(cameras) >= 5
            
            # Check for specific cameras
            camera_names = [c.name for c in cameras]
            assert 'Topcon NW400' in camera_names
            assert 'Zeiss Cirrus HD-OCT' in camera_names
            assert 'NIDEK AFC-300' in camera_names

    def test_diseases_created(self):
        """Test that diseases are created correctly."""
        with Session() as db:
            diseases = db.execute(select(Disease)).scalars().all()
            # Should have at least 5 diseases as per requirements
            assert len(diseases) >= 5
            
            # Check for specific diseases
            disease_names = [d.name for d in diseases]
            assert 'Glaucoma' in disease_names
            assert 'Diabetic Retinopathy' in disease_names
            assert 'Age-related Macular Degeneration' in disease_names

    def test_areas_created(self):
        """Test that areas are created correctly."""
        with Session() as db:
            areas = db.execute(select(Area)).scalars().all()
            # Should have at least 4 areas as per requirements
            assert len(areas) >= 4
            
            # Check for specific areas
            area_names = [a.name for a in areas]
            assert 'Urban' in area_names
            assert 'Suburban' in area_names
            assert 'Rural' in area_names
            assert 'Remote' in area_names