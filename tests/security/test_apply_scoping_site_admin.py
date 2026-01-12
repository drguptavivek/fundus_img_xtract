import pytest
from sqlalchemy import select
from models import DirectImageUpload, User, Camera, Disease, Area, LabUnit
from utils.hospital_scoping import apply_scoping

@pytest.mark.security
def test_apply_scoping_site_admin_no_lab_units(db_session, seed_test_database):
    """Test that apply_scoping allows Site Admins without lab units to see all hospital data."""
    from datetime import datetime, timezone
    
    # Get fresh instances from current session to avoid DetachedInstanceError
    user = db_session.query(User).filter_by(username='site_admin_a').first()
    assert user is not None, "Site admin user should exist"
    
    camera = db_session.query(Camera).filter_by(name="Test Camera").first()
    disease = db_session.query(Disease).filter_by(name="Test Disease").first()
    area = db_session.query(Area).filter_by(name="Test Area").first()
    
    # Get fresh lab unit instances
    lab_a = db_session.query(LabUnit).filter_by(name='Lab A1').first()
    lab_b = db_session.query(LabUnit).filter_by(name='Lab B1').first()
    
    # Create images in both hospitals
    img_a = DirectImageUpload(
        filename="hospital_a_image.jpg",
        folder_rel="files/direct_uploads/test",
        file_hash="hash_a",
        lab_unit_id=lab_a.id,
        hospital_id=lab_a.hospital_id,
        uploader_id=user.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        created_at=datetime.now(timezone.utc)
    )
    
    img_b = DirectImageUpload(
        filename="hospital_b_image.jpg",
        folder_rel="files/direct_uploads/test",
        file_hash="hash_b",
        lab_unit_id=lab_b.id,
        hospital_id=lab_b.hospital_id,
        uploader_id=user.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        created_at=datetime.now(timezone.utc)
    )
    
    db_session.add_all([img_a, img_b])
    db_session.commit()
    
    # Verify user setup
    assert user.hospital_id == 1, "Site admin should have hospital_id=1"
    assert user.has_role('local_admin'), "Site admin should have local_admin role"
    assert len(list(user.lab_units)) == 0, "Site admin should have no lab units"
    
    # Test apply_scoping
    q = select(DirectImageUpload)
    q = apply_scoping(q, DirectImageUpload, user, 'upload')
    results = db_session.execute(q).scalars().all()
    
    filenames = [img.filename for img in results]
    
    # Site admin should see Hospital A image
    assert "hospital_a_image.jpg" in filenames, f"Site Admin should see Hospital A image. Got: {filenames}"
    
    # Site admin should NOT see Hospital B image
    assert "hospital_b_image.jpg" not in filenames, f"Site Admin should NOT see Hospital B image. Got: {filenames}"
