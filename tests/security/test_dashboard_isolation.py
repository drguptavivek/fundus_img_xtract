
import pytest
from flask import url_for
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area, User
from datetime import datetime, timezone

@pytest.mark.security
def test_direct_upload_dashboard_isolation_manual(app, db_session, seed_test_database):
    """Test dashboard isolation and access for site admin."""
    # Get fresh instances from current session to avoid DetachedInstanceError
    user = db_session.query(User).filter_by(username='site_admin_a').first()
    assert user is not None, "Site admin user should exist"
    
    camera = db_session.query(Camera).filter_by(name="Test Camera").first()
    disease = db_session.query(Disease).filter_by(name="Test Disease").first()
    area = db_session.query(Area).filter_by(name="Test Area").first()
    
    # Get fresh lab unit instances
    lab_a = db_session.query(LabUnit).filter_by(name='Lab A1').first()
    lab_b = db_session.query(LabUnit).filter_by(name='Lab B1').first()
    
    # Ensure user has role explicitly
    from models import Role
    admin_role = db_session.query(Role).filter_by(name='local_admin').first()
    if admin_role not in user.roles:
        user.roles.append(admin_role)
    
    # Assign lab units to user to avoid redirect in dashboard
    if lab_a not in user.lab_units:
        user.lab_units.append(lab_a)
    if lab_b not in user.lab_units:
        user.lab_units.append(lab_b)
    
    # Create an image in Hospital B (External)
    img_b = DirectImageUpload(
        filename="secret_hosp_b.jpg",
        folder_rel="files/direct_uploads/test",
        file_hash="hashb",
        lab_unit_id=lab_b.id,
        hospital_id=lab_b.hospital_id,
        uploader_id=user.id, 
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        created_at=datetime.now(timezone.utc)
    )
    # Create an image in Hospital A (Self)
    img_a = DirectImageUpload(
        filename="my_hosp_a.jpg",
        folder_rel="files/direct_uploads/test",
        file_hash="hasha",
        lab_unit_id=lab_a.id,
        hospital_id=lab_a.hospital_id,
        uploader_id=user.id,
        camera_id=camera.id,
        disease_id=disease.id,
        area_id=area.id,
        created_at=datetime.now(timezone.utc)
    )
    db_session.add_all([img_b, img_a])
    db_session.commit()
    
    # Refresh user to ensure it's attached to current session
    db_session.refresh(user)
    
    # DEBUG: Verify images were actually created in the database
    print(f"\n=== PRE-REQUEST DEBUG ===")
    all_images = db_session.query(DirectImageUpload).all()
    print(f"Total images in database: {len(all_images)}")
    for img in all_images:
        print(f"  - {img.filename} (hospital_id={img.hospital_id}, lab_unit_id={img.lab_unit_id})")
    print(f"User hospital_id: {user.hospital_id}")
    print(f"User has local_admin role: {user.has_role('local_admin')}")
    print(f"=== END PRE-REQUEST DEBUG ===\n")
    
    # Use Flask-Login test client with proper authentication
    from flask_login import FlaskLoginClient
    app.test_client_class = FlaskLoginClient
    
    with app.test_client(user=user) as client:
        with app.test_request_context():
            dashboard_url = url_for('direct_uploads.dashboard')
        
        response = client.get(dashboard_url, follow_redirects=True)
        assert response.status_code == 200, f"Dashboard returned {response.status_code}"
        
        # Isolation check: should NOT see Hospital B image
        assert b"secret_hosp_b.jpg" not in response.data, "Site Admin A saw Hospital B image in dashboard!"
        
        # Visibility check: SHOULD see Hospital A image
        assert b"my_hosp_a.jpg" in response.data, "Site Admin A could NOT see their own Hospital A image in dashboard!"
