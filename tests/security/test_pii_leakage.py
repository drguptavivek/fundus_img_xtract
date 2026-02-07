
import pytest
from flask import url_for
from models import (
    GradingTask, EncounterFile, PatientEncounters, Disease, 
    LabUnit, User, ZipFile, Hospital
)
from datetime import datetime, timezone

@pytest.mark.security
def test_cross_hospital_grading_pii_isolation(app, db_session, seed_test_database):
    """
    Verify that cross-hospital grading does not leak PII.
    
    Scenario:
    1. Hospital A has a PatientEncounter with PII (Name, PatientID).
    2. Ophthalmologist from Hospital B accesses the grading task.
    3. The response MUST NOT contain the patient name or ID.
    """
    # 1. Setup Data in Hospital A
    hosp_a_user = db_session.query(User).filter_by(username='site_admin_a').first()
    # Create Hospital B Grader manually
    from auth.security import hash_password
    from models import Role
    ophth_role = db_session.query(Role).filter_by(name='ophthalmologist').first()
    hosp_b = db_session.query(Hospital).filter_by(name='Hospital B').first()
    
    hosp_b_grader = User(
        username='ophthalmologist_hospital_b',
        password_hash=hash_password('Test@123'),
        hospital_id=hosp_b.id,
        is_master_admin=False,
        roles=[ophth_role]
    )
    db_session.add(hosp_b_grader)
    db_session.flush()
    lab_a = db_session.query(LabUnit).filter_by(name='Lab A1').first()
    disease = db_session.query(Disease).filter_by(name='Test Disease').first()
    
    # Create a Dummy ZipFile (required for PatientEncounter FK)
    zip_file = ZipFile(
        zip_filename="pii_test.zip",
        md5_hash="piihash123"
    )
    db_session.add(zip_file)
    db_session.flush()

    # Create Patient Encounter with PII
    pii_name = "SECRET_PATIENT_NAME"
    pii_id = "SECRET_MRN_12345"
    
    encounter = PatientEncounters(
        zip_file_id=zip_file.id,
        name=pii_name,              # <--- PII
        patient_id=pii_id,          # <--- PII
        capture_date="2023-01-01",
        lab_unit_id=lab_a.id
    )
    db_session.add(encounter)
    db_session.flush()

    # Create Encounter File
    enc_file = EncounterFile(
        patient_encounter_id=encounter.id,
        filename="eye_image.jpg",
        file_type="jpg",
        lab_unit_id=lab_a.id
    )
    db_session.add(enc_file)
    db_session.flush()

    # Create Grading Task
    task = GradingTask(
        encounter_file_id=enc_file.id,
        disease_id=disease.id,
        lab_unit_id=lab_a.id,
        state='pending'
    )
    db_session.add(task)
    db_session.commit()
    
    # 2. Grant Cross-Hospital Access (via UserDiseaseUnitRole)
    # The grader is in Hospital B, task is in Hospital A.
    # This simulates the "Shared Grader Pool" workflow.
    from models import UserDiseaseUnitRole
    role_assignment = UserDiseaseUnitRole(
        user_id=hosp_b_grader.id,
        disease_id=disease.id,
        lab_unit_id=lab_a.id,  # Granting access to Lab A's tasks
        can_grade_resident=True
    )
    db_session.add(role_assignment)
    db_session.commit()

    # Refresh objects
    db_session.refresh(task)
    db_session.refresh(hosp_b_grader)

    # 3. Simulate Access
    from flask_login import FlaskLoginClient
    app.test_client_class = FlaskLoginClient
    
    # Generate URL with context
    with app.test_request_context():
        url = url_for('grading.dual_grading_task', task_uuid=task.uuid, slot_type='resident')
    
    with app.test_client(user=hosp_b_grader) as client:
        # Access the dual grading page
        response = client.get(url, follow_redirects=True)
        
        assert response.status_code == 200, f"Grading page failed to load: {response.text}"
        
        # 4. Assert PII Absense
        content = response.data.decode('utf-8')
        
        # Check against PII
        assert pii_name not in content, "CRITICAL: Patient Name leaked in grading interface!"
        assert pii_id not in content, "CRITICAL: Patient ID leaked in grading interface!"
        
        # Verify legitimate data is present
        if task.uuid not in content:
            import re
            # Check for flash messages
            if "alert-danger" in content or "alert-warning" in content:
                m = re.search(r'alert alert-(?:danger|warning)[^>]*>\s*(?:<[^>]+>\s*)*([^<]+)', content)
                msg = m.group(1).strip() if m else "Unknown Error"
                pytest.fail(f"Access Denied: {msg}")
            
            # Print title to see where we are
            m_title = re.search(r'<title>(.*?)</title>', content)
            title = m_title.group(1) if m_title else "No Title"
            print(f"DEBUG: Page Content:\n{content}")
            pytest.fail(f"Task UUID not found. Page Title: {title}")

        assert task.uuid in content, "Task UUID should be visible"
        assert disease.name in content, "Disease name should be visible"


class TestProcessPDFsPIILeakage:
    """Test that process_pdfs logging does not leak PII."""

    def test_log_functions_mask_pii_in_filenames(self, capsys):
        """
        Verify log_success and log_error mask PII in filenames.
        Filename format: {patient_id}_{patient_name}_{date}_{type}_Page{n}.pdf
        """
        from process_pdfs import log_success, log_error
        from unittest.mock import patch, MagicMock

        # PII Filenames
        pii_name = "JohnDoe"
        pii_id = "123456"
        filename = f"{pii_id}_{pii_name}_2025-01-01_DR_Page1.pdf"
        
        # We expect the log to contain ID (maybe masked) but definitely NOT the name "JohnDoe"
        # Or if ID is shown, name should be "Anonymous" or removed.
        
        # Patch open to avoid writing to real log files
        with patch("builtins.open", MagicMock()):
            log_success(filename, "Processed successfully")
            log_error(filename, "Processing failed")
        
        captured = capsys.readouterr()
        
        # Strict check: Name must NOT be in output
        assert pii_name not in captured.out, f"PII Name '{pii_name}' leaked in stdout logging!"
        
        # Also check that we didn't just suppress the log entirely
        assert "SUCCESS" in captured.out or "ERROR" in captured.out


class TestExportPIILeakage:
    """Test that data exports do not leak PII."""
    
    def test_export_payload_excludes_pii_filenames(self):
        """
        Verify that _build_task_payload replaces original PII filenames with UUIDs.
        """
        from review.discrepancy_export import _build_task_payload, ExportTaskRow

        # Create a mock row with a PII filename
        pii_filename = "JohnDoe_12345_Screening.jpg"
        row = ExportTaskRow(
            task_id=1,
            task_uuid="uuid-1",
            disease="DR",
            lab_unit="Lab1",
            hospital="Hosp1",
            state="final",
            consensus_status="consensus",
            consensus_method="manual",
            final_impression="No DR",
            grading_details_json="[]",
            ai_review_comments=[],
            ai_review_statuses=[],
            image_uuid="img-uuid-10",
            encounter_file_id=10,
            encounter_file_uuid="img-uuid-10",
            encounter_filename=pii_filename, # <--- PII here
            encounter_upload_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            direct_image_upload_id=None,
            direct_image_uuid=None,
            direct_filename=None,
            direct_edited_filename=None,
            direct_folder_rel=None
        )

        payload = _build_task_payload([row])
        
        assert len(payload) == 1
        data = payload[0]
        
        # 1. Verify PII filename is NOT in the output
        assert pii_filename not in data.values(), "PII filename leaked in export data values!"
        
        # 2. Verify 'image_filename' uses the UUID
        assert data['image_filename'] == "img-uuid-10.jpg"
        
        # 3. Verify 'task_id', 'disease' are present
        assert data['task_id'] == 1
        assert data['disease'] == "DR"
