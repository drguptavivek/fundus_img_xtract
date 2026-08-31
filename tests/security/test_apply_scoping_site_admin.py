import pytest
from sqlalchemy import select
from models import DirectImageUpload
from authz.behaviors import upload_rows
from services.uploads.access import upload_columns
from tests.helpers.factories import UserFactory

@pytest.mark.security
def test_apply_scoping_site_admin_no_lab_units(db_session, core_test_data):
    """Test that apply_scoping allows Site Admins without lab units to see all hospital data."""
    from datetime import datetime, timezone
    
    hospital_a = db_session.merge(core_test_data["hospital_a"])
    lab_a = db_session.merge(core_test_data["lab_a1"])
    lab_b = db_session.merge(core_test_data["lab_b1"])
    camera = db_session.merge(core_test_data["camera"])
    disease = db_session.merge(core_test_data["glaucoma"])
    area = db_session.merge(core_test_data["area"])
    user = UserFactory.create_with_hospital(
        db_session,
        "local_admin",
        hospital_a.id,
        [],
        username="lean_site_admin_without_labs",
    )
    
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
    assert user.hospital_id == hospital_a.id
    assert user.has_role('local_admin'), "Site admin should have local_admin role"
    assert len(list(user.lab_units)) == 0, "Site admin should have no lab units"
    
    # Test the named upload behaviour.
    q = select(DirectImageUpload)
    q = upload_rows(db_session, q, user, upload_columns(DirectImageUpload))
    results = db_session.execute(q).scalars().all()
    
    filenames = [img.filename for img in results]
    
    # Site admin should see Hospital A image
    assert "hospital_a_image.jpg" in filenames, f"Site Admin should see Hospital A image. Got: {filenames}"
    
    # Site admin should NOT see Hospital B image
    assert "hospital_b_image.jpg" not in filenames, f"Site Admin should NOT see Hospital B image. Got: {filenames}"
