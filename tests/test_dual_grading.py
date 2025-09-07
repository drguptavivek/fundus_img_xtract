"""Test dual grading functionality."""

import pytest
from flask import url_for
from models import User, Role, Session, EncounterFile, DirectImageUpload
from auth.security import hash_password
from sqlalchemy import select


class TestDualGradingFunctionality:
    """Test cases for dual grading functionality."""

    def test_dual_grading_dashboard_requires_authentication(self, client):
        """Test that dual grading dashboard requires authentication."""
        response = client.get('/dual-grading/')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_dual_grading_dashboard_requires_proper_role(self, client, auth_client):
        """Test that dual grading dashboard requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_dual_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_dual_grading', 'testpassword')
        
        # Try to access dual grading dashboard
        response = client.get('/dual-grading/')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_dual_grading_dashboard_loads(self, client, auth_client):
        """Test that dual grading dashboard loads for authorized users."""
        # Create a user with ophthalmologist role
        with Session() as db:
            ophthalmologist_role = Role(name='ophthalmologist')
            db.add(ophthalmologist_role)
            db.flush()
            
            test_user = User(
                username='ophthalmologist_dual_grading',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(ophthalmologist_role)
            db.add(test_user)
            db.commit()

        # Login as ophthalmologist
        auth_client.login('ophthalmologist_dual_grading', 'testpassword')
        
        # Access dual grading dashboard
        response = client.get('/dual-grading/')
        # May return 404 if no data, but should not be forbidden
        assert response.status_code in [200, 404]

    def test_locking_mechanism(self):
        """Test the locking mechanism for dual grading."""
        # Get a session
        db = Session()
        
        try:
            # Create a test encounter file
            encounter = EncounterFile(
                patient_encounter_id=1,
                filename='test_image.jpg',
                file_type='image'
            )
            db.add(encounter)
            db.commit()
            
            # Refresh and check initial state
            db.refresh(encounter)
            assert encounter.is_locked == False
            
            # Test locking
            encounter.is_locked = True
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            assert encounter.is_locked == True
            
            # Test unlocking
            encounter.is_locked = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            assert encounter.is_locked == False
        finally:
            db.close()

    def test_direct_upload_locking_mechanism(self):
        """Test the locking mechanism for direct image uploads."""
        # Get a session
        db = Session()
        
        try:
            # Create test master data
            from models import Hospital, LabUnit, Camera, Disease, Area
            
            hospital = Hospital(name='Test Hospital')
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name='Test Lab Unit', hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name='Test Camera')
            db.add(camera)
            db.flush()
            
            disease = Disease(name='Test Disease')
            db.add(disease)
            db.flush()
            
            area = Area(name='Test Area')
            db.add(area)
            db.flush()
            
            # Create a test direct image upload
            direct_upload = DirectImageUpload(
                filename='test_image.jpg',
                folder_rel='test_folder',
                file_hash='test_hash_123456',
                uploader_id=1,
                hospital_id=hospital.id,
                lab_unit_id=lab_unit.id,
                camera_id=camera.id,
                disease_id=disease.id,
                area_id=area.id,
                is_mydriatic=False
            )
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check initial state
            db.refresh(direct_upload)
            assert direct_upload.is_locked == False
            
            # Test locking
            direct_upload.is_locked = True
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            assert direct_upload.is_locked == True
            
            # Test unlocking
            direct_upload.is_locked = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            assert direct_upload.is_locked == False
        finally:
            db.close()