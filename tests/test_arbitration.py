"""Test arbitration functionality."""

import pytest
from flask import url_for
from models import User, Role, Session, EncounterFile, DirectImageUpload
from auth.security import hash_password
from sqlalchemy import select


class TestArbitrationFunctionality:
    """Test cases for arbitration functionality."""

    def test_arbitration_dashboard_requires_authentication(self, client):
        """Test that arbitration dashboard requires authentication."""
        response = client.get('/dual-grading/arbitration')
        # Should redirect to login
        assert response.status_code == 302
        assert '/login' in response.location

    def test_arbitration_dashboard_requires_proper_role(self, client, auth_client):
        """Test that arbitration dashboard requires proper role."""
        # Create a user without proper role
        with Session() as db:
            user_role = Role(name='contributor')
            db.add(user_role)
            db.flush()
            
            test_user = User(
                username='testuser_arbitration',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(user_role)
            db.add(test_user)
            db.commit()

        # Login as regular user
        auth_client.login('testuser_arbitration', 'testpassword')
        
        # Try to access arbitration dashboard
        response = client.get('/dual-grading/arbitration')
        # Should be forbidden
        assert response.status_code in [403, 302]

    def test_arbitration_dashboard_loads(self, client, auth_client):
        """Test that arbitration dashboard loads for authorized users."""
        # Create a user with ophthalmologist role
        with Session() as db:
            ophthalmologist_role = Role(name='ophthalmologist')
            db.add(ophthalmologist_role)
            db.flush()
            
            test_user = User(
                username='ophthalmologist_arbitration',
                password_hash=hash_password('testpassword'),
                is_active=True
            )
            test_user.roles.append(ophthalmologist_role)
            db.add(test_user)
            db.commit()

        # Login as ophthalmologist
        auth_client.login('ophthalmologist_arbitration', 'testpassword')
        
        # Access arbitration dashboard
        response = client.get('/dual-grading/arbitration')
        # May return 404 if no data, but should not be forbidden
        assert response.status_code in [200, 404]

    def test_encounter_file_arbitration_flag(self):
        """Test the arbitration flag for encounter files."""
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
            assert encounter.is_arbitration == False
            
            # Test setting arbitration flag
            encounter.is_arbitration = True
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            assert encounter.is_arbitration == True
            
            # Test resetting arbitration flag
            encounter.is_arbitration = False
            db.add(encounter)
            db.commit()
            
            # Refresh and check
            db.refresh(encounter)
            assert encounter.is_arbitration == False
        finally:
            db.close()

    def test_direct_upload_arbitration_flag(self):
        """Test the arbitration flag for direct image uploads."""
        # Get a session
        db = Session()
        
        try:
            # Create test master data
            from models import Hospital, LabUnit, Camera, Disease, Area
            
            hospital = Hospital(name='Test Hospital for Arbitration')
            db.add(hospital)
            db.flush()
            
            lab_unit = LabUnit(name='Test Lab Unit for Arbitration', hospital_id=hospital.id)
            db.add(lab_unit)
            db.flush()
            
            camera = Camera(name='Test Camera for Arbitration')
            db.add(camera)
            db.flush()
            
            disease = Disease(name='Test Disease for Arbitration')
            db.add(disease)
            db.flush()
            
            area = Area(name='Test Area for Arbitration')
            db.add(area)
            db.flush()
            
            # Create a test direct image upload
            direct_upload = DirectImageUpload(
                filename='test_image_arbitration.jpg',
                folder_rel='test_folder_arbitration',
                file_hash='test_hash_arbitration_123456',
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
            assert direct_upload.is_arbitration == False
            
            # Test setting arbitration flag
            direct_upload.is_arbitration = True
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            assert direct_upload.is_arbitration == True
            
            # Test resetting arbitration flag
            direct_upload.is_arbitration = False
            db.add(direct_upload)
            db.commit()
            
            # Refresh and check
            db.refresh(direct_upload)
            assert direct_upload.is_arbitration == False
        finally:
            db.close()