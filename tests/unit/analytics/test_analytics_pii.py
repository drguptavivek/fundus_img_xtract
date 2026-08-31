import pytest
import uuid
from analytics.utils import build_encounter_result_payload
from analytics.encounterUtils import get_encounter_summary
from models import PatientEncounters, LabUnit, Hospital, User, Role, ZipFile

def test_build_encounter_result_payload_always_masks_pii(app):
    """Verify that build_encounter_result_payload always masks PII."""
    with app.app_context():
        # Mock encounter object
        class MockEncounter:
            def __init__(self):
                self.id = 1
                self.name = "John Doe"
                self.patient_id = "PID12345"
                self.glaucoma_results_cleaned = []
                self.dr_reports = []
                self.encounter_files = []
                self.encounter_set_images = []
                self.lab_unit = None
 
        encounters = [MockEncounter()]
        task_details = []
        
        # Test (should mask regardless of any flags if they existed, but we removed them)
        payload = build_encounter_result_payload(encounters, task_details)
        assert payload[0]["patient_name"] == "Anonymous"
        assert payload[0]["patient_id"].startswith("P****")

def test_get_encounter_summary_always_masks_pii(db_session, app):
    """Verify get_encounter_summary masks PII for ALL users (same hospital and cross-hospital)."""
    with app.app_context():
        # Find existing hospitals and users
        hospitals = db_session.query(Hospital).limit(2).all()
        if len(hospitals) < 2:
            pytest.skip("Need at least 2 hospitals in seed")
            
        h1, h2 = hospitals[0], hospitals[1]
        
        lu1 = db_session.query(LabUnit).filter_by(hospital_id=h1.id).first()
        if not lu1:
            pytest.skip(f"No LabUnit for hospital {h1.name}")
            
        users = db_session.query(User).limit(2).all()
        if len(users) < 2:
            pytest.skip("Need at least 2 users in seed")
        
        u_same, u_cross = users[0], users[1]
        u_same.hospital_id = h1.id
        u_cross.hospital_id = h2.id

        # Assign lab units so hospital scoping can match on them
        u_same.lab_units = [lu1]

        # Roles decide access under lean authorization; give u_same the
        # data_manager analytics role rather than relying on whichever seed
        # users this query happens to return.
        dm_role = db_session.query(Role).filter_by(name='data_manager').one()
        if dm_role not in u_same.roles:
            u_same.roles.append(dm_role)
        # u_cross is a global admin (cross-hospital viewer). The lean
        # authorization contract grants access via roles, not the dead
        admin_role = db_session.query(Role).filter_by(name='admin').one()
        if admin_role not in u_cross.roles:
            u_cross.roles.append(admin_role)
        
        db_session.flush()

        # Create one unique encounter using a VERY high ID to avoid collisions
        UID = 3000000 + int(uuid.uuid4().int % 100000)
        z = ZipFile(id=UID, zip_filename=f"pii_mand_{uuid.uuid4().hex[:6]}.zip", md5_hash=uuid.uuid4().hex)
        db_session.add(z)
        db_session.flush()
        
        enc = PatientEncounters(
            id=UID,
            name="Secret Patient",
            patient_id="SECRET999",
            capture_date="2023-01-01",
            lab_unit_id=lu1.id,
            zip_file_id=z.id
        )
        db_session.add(enc)
        db_session.flush()
        
        # Test same-hospital access (MUST BE MASKED NOW)
        summary = get_encounter_summary(enc.id, u_same)
        assert summary is not None
        assert summary["encounter_name"] == "Anonymous"
        assert summary["encounter_patient_id"].startswith("P****")
        
        # Test cross-hospital access (MUST BE MASKED)
        summary = get_encounter_summary(enc.id, u_cross)
        assert summary is not None
        assert summary["encounter_name"] == "Anonymous"
        assert summary["encounter_patient_id"].startswith("P****")

def test_admin_always_sees_masked_pii_in_analytics(db_session, app):
    """Verify master admin also sees masked PII in analytics."""
    with app.app_context():
        # Find any hospital and lab unit
        lu1 = db_session.query(LabUnit).first()
        if not lu1:
             pytest.skip("No LabUnits found in seed")
        
        admin = db_session.query(User).filter_by(is_master_admin=True).first()
        if not admin:
            # Create a master admin if not found (unlikely in seed)
            admin = User(username=f"temp_admin_{uuid.uuid4().hex[:4]}", is_master_admin=True)
            db_session.add(admin)
            db_session.flush()

        UID = 4000000 + int(uuid.uuid4().int % 100000)
        z = ZipFile(id=UID, zip_filename=f"pii_admin_{uuid.uuid4().hex[:6]}.zip", md5_hash=uuid.uuid4().hex)
        db_session.add(z)
        db_session.flush()
        
        enc = PatientEncounters(
            id=UID,
            name="Admin Secret",
            patient_id="ADMIN123",
            capture_date="2023-01-01",
            lab_unit_id=lu1.id,
            zip_file_id=z.id
        )
        db_session.add(enc)
        db_session.flush()
        
        # Admin same-hospital access (should be masked in analytics)
        summary = get_encounter_summary(enc.id, admin)
        assert summary is not None
        assert summary["encounter_name"] == "Anonymous"
        assert summary["encounter_patient_id"].startswith("P****")
