
import pytest
from datetime import datetime, timezone
from models import PatientEncounters, GradingTask, DirectImageUpload, User, Hospital, LabUnit, Camera, Disease, Area
from utils.hospital_scoping import apply_scoping

@pytest.fixture
def test_metadata(db_session, test_lab_units):
    """Create basic metadata for images/tasks."""
    camera = Camera(name="Test Camera")
    disease = Disease(name="Test Disease")
    area = Area(name="Test Area")
    db_session.add_all([camera, disease, area])
    db_session.commit()
    return {"camera": camera, "disease": disease, "area": area}

@pytest.mark.security
class TestQueryIsolation:
    """
    TDD Tests for Phase 3: Query Updates (Images, Tasks, Analytics).
    Verifies that queries correctly filter by hospital/lab unit.
    """

    def test_image_query_isolation_for_site_admin(self, db_session, test_hospitals, site_admin_hospital_a, test_lab_units, test_metadata):
        """Site admin should only see images from their own hospital."""
        db = db_session
        lab_b = test_lab_units['lab_b1']
        
        # Create an image in Hospital B
        img_b = DirectImageUpload(
            filename="hospital_b_image.jpg",
            folder_rel="files/direct_uploads/test",
            file_hash="fakehash",
            lab_unit_id=lab_b.id,
            hospital_id=lab_b.hospital_id,
            uploader_id=site_admin_hospital_a.id, 
            camera_id=test_metadata["camera"].id,
            disease_id=test_metadata["disease"].id,
            area_id=test_metadata["area"].id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(img_b)
        db.commit()

        # Query using site_admin_hospital_a
        query = db.query(DirectImageUpload)
        scoped_query = apply_scoping(query, DirectImageUpload, site_admin_hospital_a, 'upload')
        
        results = scoped_query.all()
        assert img_b.id not in [r.id for r in results], "Site Admin A saw an image from Hospital B!"

    def test_review_task_isolation_for_site_admin(self, db_session, test_hospitals, site_admin_hospital_a, test_lab_units, test_metadata):
        """Site admin should only see review tasks (state='final') from their own hospital."""
        db = db_session
        lab_b = test_lab_units['lab_b1']
        
        # Create an image in Hospital B first (to associate with task)
        img_b = DirectImageUpload(
            filename="hospital_b_task_image.jpg",
            folder_rel="files/direct_uploads/test",
            file_hash="fakehash2",
            lab_unit_id=lab_b.id,
            hospital_id=lab_b.hospital_id,
            uploader_id=site_admin_hospital_a.id,
            camera_id=test_metadata["camera"].id,
            disease_id=test_metadata["disease"].id,
            area_id=test_metadata["area"].id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(img_b)
        db.commit()

        # Create a task in Hospital B
        task_b = GradingTask(
            direct_image_upload_id=img_b.id,
            lab_unit_id=lab_b.id,
            disease_id=test_metadata["disease"].id,
            state='final',
            created_at=datetime.now(timezone.utc)
        )
        db.add(task_b)
        db.commit()

        # Query using site_admin_hospital_a
        query = db.query(GradingTask)
        scoped_query = apply_scoping(query, GradingTask, site_admin_hospital_a, 'review')
        
        results = scoped_query.all()
        assert task_b.id not in [r.id for r in results], "Site Admin A saw a review task from Hospital B!"

    def test_grading_task_preserved_cross_hospital(self, db_session, test_hospitals, site_admin_hospital_a, test_lab_units, test_metadata):
        """Ophthalmologist can see grading tasks from other hospitals if eligible."""
        db = db_session
        lab_b = test_lab_units['lab_b1']
        
        # Create image in Hospital B
        img_b = DirectImageUpload(
            filename="hospital_b_grading_image.jpg",
            folder_rel="files/direct_uploads/test",
            file_hash="fakehash3",
            lab_unit_id=lab_b.id,
            hospital_id=lab_b.hospital_id,
            uploader_id=site_admin_hospital_a.id,
            camera_id=test_metadata["camera"].id,
            disease_id=test_metadata["disease"].id,
            area_id=test_metadata["area"].id,
            created_at=datetime.now(timezone.utc)
        )
        db.add(img_b)
        db.commit()

        # Create a task in Hospital B
        task_b = GradingTask(
            direct_image_upload_id=img_b.id,
            lab_unit_id=lab_b.id,
            disease_id=test_metadata["disease"].id,
            state='pending',
            created_at=datetime.now(timezone.utc)
        )
        db.add(task_b)
        db.commit()

        # Query using site_admin_hospital_a (who is also an ophthalmologist)
        query = db.query(GradingTask)
        scoped_query = apply_scoping(query, GradingTask, site_admin_hospital_a, 'grading')
        
        results = scoped_query.all()
        # This SHOULD be allowed based on policy (cross-hospital grading)
        assert task_b.id in [r.id for r in results], "Ophthalmologist A could NOT see grading task from Hospital B!"
