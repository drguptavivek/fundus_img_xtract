
import pytest
from flask import url_for
from models import PatientEncounters, User, Role, LabUnit, Hospital, ZipFile
from auth.utils import utcnow
from tests.helpers.factories import UserFactory, CoreEntityFactory
from datetime import datetime

class TestScreeningsIsolation:
    @pytest.fixture
    def setup_data(self, db_session):
        # Create hospitals using factory (safely handles existence)
        h1 = CoreEntityFactory.create_hospital(db_session, name="H1", hospital_id=101)
        h2 = CoreEntityFactory.create_hospital(db_session, name="H2", hospital_id=102)
        
        # Create lab units
        l1 = CoreEntityFactory.create_lab_unit(db_session, name="L1", hospital_id=h1.id, lab_unit_id=101)
        l2 = CoreEntityFactory.create_lab_unit(db_session, name="L2", hospital_id=h2.id, lab_unit_id=102)
        
        # Create users
        # User 1: assigned to L1
        u1 = UserFactory.create_with_hospital(
            db_session, 
            role_name="ophthalmologist", 
            hospital_id=h1.id, 
            lab_unit_ids=[l1.id],
            username="user_h1",
            password="password"
        )
        
        # User 2: assigned to L2 (for negative tests)
        u2 = UserFactory.create_with_hospital(
            db_session, 
            role_name="ophthalmologist", 
            hospital_id=h2.id, 
            lab_unit_ids=[l2.id],
            username="user_h2",
            password="password"
        )
        
        # Create ZipFiles (one per encounter due to unique constraint)
        z1 = ZipFile(zip_filename="test1.zip", md5_hash="hash1", upload_date=utcnow())
        z2 = ZipFile(zip_filename="test2.zip", md5_hash="hash2", upload_date=utcnow())
        db_session.add_all([z1, z2])
        db_session.flush()

        # Create encounters
        # E1 belongs to L1
        e1 = PatientEncounters(
            patient_id="P1", 
            name="Patient One", 
            lab_unit_id=l1.id, 
            capture_date=utcnow(),
            zip_file_id=z1.id
        )
        # E2 belongs to L2
        e2 = PatientEncounters(
            patient_id="P2", 
            name="Patient Two", 
            lab_unit_id=l2.id, 
            capture_date=utcnow(),
            zip_file_id=z2.id
        )
        db_session.add_all([e1, e2])
        db_session.commit()
        
        return {"h1": h1, "h2": h2, "l1": l1, "l2": l2, "u1": u1, "u2": u2, "e1": e1, "e2": e2}

    def test_list_screenings_scopes_by_hospital(self, client, app, setup_data):
        """User from H1 should only see screenings from H1."""
        # Login as User H1
        client.post("/auth/login", data={
            "username": "user_h1",
            "password": "password"
        }, follow_redirects=True)
        
        # Use simple path, assuming standard flask behavior
        response = client.get("/screenings/", follow_redirects=True)
        assert response.status_code == 200
        content = response.get_data(as_text=True)
        
        # Should see E1 (same lab)
        assert "Patient One" in content
        assert "P1" in content
        
        # Should NOT see E2 (different hospital)
        assert "Patient Two" not in content
        assert "P2" not in content

    def test_screening_detail_access_control(self, client, app, setup_data):
        """User cannot access detail of screening from another hospital."""
        client.post("/auth/login", data={"username": "user_h1", "password": "password"})
        
        # Access allowed encounter (E1)
        resp_ok = client.get(f"/screenings/{setup_data['e1'].id}")
        assert resp_ok.status_code == 200
        
        # Access denied encounter (E2)
        resp_forbidden = client.get(f"/screenings/{setup_data['e2'].id}")
        assert resp_forbidden.status_code == 403

    def test_reprocess_pdf_access_control(self, client, app, setup_data, db_session):
        """User cannot reprocess PDF for another hospital."""
        # Grant admin/data_manager role to u1 to bypass global role checks
        from models import Role
        
        # Use fixture db_session
        dm_role = db_session.query(Role).filter_by(name="data_manager").first()
        if not dm_role:
            dm_role = Role(name="data_manager")
            db_session.add(dm_role)
            db_session.flush()
        
        # Re-fetch user in this session context
        u1 = db_session.get(User, setup_data["u1"].id)
        if dm_role not in u1.roles:
            u1.roles.append(dm_role)
        db_session.commit()

        client.post("/auth/login", data={"username": "user_h1", "password": "password"})
        
        # Try to reprocess E2 (different hospital checks)
        resp = client.post(f"/screenings/reprocess_pdf/{setup_data['e2'].id}", follow_redirects=True)
        
        # Should be forbidden because u1 has L1, E2 is L2.
        assert resp.status_code == 403

    def test_delete_reports_access_control(self, client, app, setup_data, db_session):
        """User cannot delete reports for another hospital."""
        # Ensure role is set
        from models import Role
        
        dm_role = db_session.query(Role).filter_by(name="data_manager").first()
        if not dm_role:
            dm_role = Role(name="data_manager")
            db_session.add(dm_role)
            db_session.flush()
            
        u1 = db_session.get(User, setup_data["u1"].id)
        if dm_role not in u1.roles:
            u1.roles.append(dm_role)
        db_session.commit()

        client.post("/auth/login", data={"username": "user_h1", "password": "password"})
        
        resp = client.post(f"/screenings/delete_reports/{setup_data['e2'].id}", follow_redirects=True)
        assert resp.status_code == 403

