
import pytest
from flask import url_for
from sqlalchemy import select, func
from werkzeug.security import generate_password_hash

from models import (
    User, Role, DirectImageUpload, DirectImageVerify, GradingTask, 
    LabUnit, Hospital, Camera, Disease, Area
)
from tests.helpers.test_factories import TestDataFactory

class TestAnonymizationWorkflow:
    """
    Integration tests for the Optometrist PII Anonymization Workflow.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self, db_session, hospital_data):
        self.hospital_a = hospital_data['hospital_a']['hospital']
        self.lab_unit_a = hospital_data['hospital_a']['lab_units'][0]
        
        # Helper for get_or_create
        def get_or_create(model, **kwargs):
            instance = db_session.execute(select(model).filter_by(**kwargs)).scalar_one_or_none()
            if instance:
                return instance
            instance = model(**kwargs)
            db_session.add(instance)
            db_session.flush()
            return instance

        # Create Helpers
        self.camera = get_or_create(Camera, name="Test Camera")
        self.disease = get_or_create(Disease, name="Test Disease")
        self.area = get_or_create(Area, name="Test Area")
        
        db_session.flush() # get IDs
        
        # Create Users
        from uuid import uuid4
        uid = str(uuid4())[:8]
        
        # Helper to get/create role
        def get_role(name):
            return get_or_create(Role, name=name)

        # Optometrist
        self.optometrist = User(
            username=f"optom_{uid}",
            email=f"optom_{uid}@test.com",
            password_hash=generate_password_hash("Test@2026"),
            is_active=True,
            hospital_id=self.hospital_a.id 
        )
        self.optometrist.roles.append(get_role("optometrist"))
        self.optometrist.lab_units.append(self.lab_unit_a)
        db_session.add(self.optometrist)
        
        # Uploader
        self.uploader = User(
            username=f"upload_{uid}",
            email=f"upload_{uid}@test.com",
            password_hash=generate_password_hash("Test@2026"),
            is_active=True,
            hospital_id=self.hospital_a.id
        )
        self.uploader.roles.append(get_role("fileUploader"))
        self.uploader.lab_units.append(self.lab_unit_a)
        db_session.add(self.uploader)
        
        # Resident
        self.resident = User(
            username=f"resid_{uid}",
            email=f"resid_{uid}@test.com",
            password_hash=generate_password_hash("Test@2026"),
            is_active=True,
            hospital_id=self.hospital_a.id
        )
        self.resident.roles.append(get_role("resident"))
        self.resident.lab_units.append(self.lab_unit_a)
        db_session.add(self.resident)

        db_session.commit() # Commit to ensure roles/users are persisted

    def create_upload(self, db_session, filename="test_image.jpg", verified=False):
        """Helper to create a DirectImageUpload"""
        upload = DirectImageUpload(
            uuid=TestDataFactory._get_unique_id(), # use counter as uuid seed if needed, or simple str
            filename=filename,
            file_hash="dummy_hash",
            uploader_id=self.uploader.id,
            hospital_id=self.hospital_a.id,
            lab_unit_id=self.lab_unit_a.id,
            camera_id=self.camera.id,
            disease_id=self.disease.id,
            area_id=self.area.id,
            folder_rel="files/direct_uploads/test_mock"
        )
        # Fix UUID handling: Model expects UUID object usually, but let's check.
        # Factories used _random_uuid() which wasn't shown. 
        # using uuid4()
        from uuid import uuid4
        upload.uuid = uuid4()
        
        db_session.add(upload)
        db_session.flush()
        
        if verified:
            verify = DirectImageVerify(
                image_upload_id=upload.id,
                verified_status='verified',
                verified_by_id=self.optometrist.id,
                verified_at=func.now()
            )
            db_session.add(verify)
            db_session.flush()
            
        return upload

    def test_access_control(self, auth_client, db_session):
        """Verify only optometrists (and authorized roles) can access the dashboard."""
        client = auth_client(db_session.merge(self.resident))
        resp = client.get(url_for('preprocess.anonymization_dashboard'))
        assert resp.status_code == 403 or "You do not have permission" in resp.text or resp.status_code == 302
        
        client = auth_client(db_session.merge(self.optometrist))
        resp = client.get(url_for('preprocess.anonymization_dashboard'))
        assert resp.status_code == 200

    def test_dashboard_kpis_and_listing(self, auth_client, db_session):
        u1 = self.create_upload(db_session, "unverified.jpg", verified=False)
        u2 = self.create_upload(db_session, "verified.jpg", verified=True)
        db_session.commit()

        client = auth_client(db_session.merge(self.optometrist))
        resp = client.get(url_for('preprocess.anonymization_dashboard'))
        assert resp.status_code == 200
        assert "unverified.jpg" in resp.text or "Anonymize" in resp.text
        
    def test_verify_action_creates_task(self, auth_client, db_session):
        upload = self.create_upload(db_session, "to_verify.jpg", verified=False)
        db_session.commit()
        
        client = auth_client(db_session.merge(self.optometrist))
        url = url_for('preprocess.anonymize_image', uuid=upload.uuid)
        resp = client.post(url, data={
            'verified_status': 'verified',
            'remarks': 'Test Verification'
        }, follow_redirects=True)
        
        assert resp.status_code == 200
        
        verification = db_session.execute(
            select(DirectImageVerify).where(DirectImageVerify.image_upload_id == upload.id)
        ).scalar_one()
        assert verification.verified_status == 'verified'
        
        task = db_session.execute(
            select(GradingTask).where(GradingTask.direct_image_upload_id == upload.id)
        ).scalar_one_or_none()
        assert task is not None
        assert task.state == 'pending'

    def test_unverify_removes_task(self, auth_client, db_session):
        upload = self.create_upload(db_session, "verified_to_undo.jpg", verified=True)
        task = GradingTask(
            direct_image_upload_id=upload.id,
            disease_id=self.disease.id,
            lab_unit_id=self.lab_unit_a.id,
            state='pending'
        )
        db_session.add(task)
        db_session.commit()
        
        client = auth_client(db_session.merge(self.optometrist))
        url = url_for('preprocess.anonymize_image', uuid=upload.uuid)
        resp = client.post(url, data={'remarks': 'Undo'}, follow_redirects=True)
        
        assert resp.status_code == 200
        
        verification = db_session.execute(
            select(DirectImageVerify).where(DirectImageVerify.image_upload_id == upload.id)
        ).scalar_one()
        assert verification.verified_status == 'unverified'
        
        task_check = db_session.execute(
            select(GradingTask).where(GradingTask.direct_image_upload_id == upload.id)
        ).scalar_one_or_none()
        assert task_check is None
