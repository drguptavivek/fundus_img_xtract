
import pytest
from datetime import datetime, timezone
from models import PatientEncounters, GradingTask, DirectImageUpload, User, Hospital, LabUnit, Camera, Disease, Area
from authz.behaviors import clinical_rows, upload_rows
from services.uploads.access import upload_columns
from tasks.access import task_columns

@pytest.fixture
def test_metadata(db_session, test_lab_units):
    """Get-or-create basic metadata (the names are seeded and unique)."""
    camera = db_session.query(Camera).filter_by(name="Test Camera").first()
    if camera is None:
        camera = Camera(name="Test Camera")
        db_session.add(camera)
    disease = db_session.query(Disease).filter_by(name="Test Disease").first()
    if disease is None:
        disease = Disease(name="Test Disease")
        db_session.add(disease)
    area = db_session.query(Area).filter_by(name="Test Area").first()
    if area is None:
        area = Area(name="Test Area")
        db_session.add(area)
    db_session.flush()
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
        lab_b = db.merge(test_lab_units['lab_b1'])
        site_admin_hospital_a = db.merge(site_admin_hospital_a)
        
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
        scoped_query = upload_rows(
            db,
            query,
            site_admin_hospital_a,
            upload_columns(DirectImageUpload),
        )
        
        results = scoped_query.all()
        assert img_b.id not in [r.id for r in results], "Site Admin A saw an image from Hospital B!"

    def test_review_task_isolation_for_site_admin(self, db_session, test_hospitals, site_admin_hospital_a, test_lab_units, test_metadata):
        """Site admin should only see review tasks (state='final') from their own hospital."""
        db = db_session
        lab_b = db.merge(test_lab_units['lab_b1'])
        site_admin_hospital_a = db.merge(site_admin_hospital_a)
        
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
        scoped_query = clinical_rows(
            db,
            query,
            site_admin_hospital_a,
            task_columns(GradingTask),
        )
        
        results = scoped_query.all()
        assert task_b.id not in [r.id for r in results], "Site Admin A saw a review task from Hospital B!"
