import pytest
from uuid import uuid4
from flask import url_for
from unittest.mock import patch, MagicMock
from contextlib import contextmanager
from models import Job, JobItem, User, Disease, LabUnit, GradingTask, Grade, DiseaseGrading
from job_store import db_get_job_payload
from utils.log_sanitize import sanitize_log_value

@pytest.fixture
def test_setup(db_session, client, master_admin):
    # Setup necessary models
    lu = db_session.query(LabUnit).first()
    if not lu:
        from models import Hospital
        h = Hospital(name="Test Hospital")
        db_session.add(h)
        db_session.flush()
        lu = LabUnit(name="Test Lab", hospital_id=h.id)
        db_session.add(lu)
        db_session.flush()
    
    disease = db_session.query(Disease).first()
    if not disease:
        disease = Disease(name="DR")
        db_session.add(disease)
        db_session.flush()
        
    return lu, disease, master_admin

def test_job_payload_masking_for_export(db_session, test_setup):
    lu, disease, admin = test_setup
    
    # Create an export job
    job = Job(
        token="export_token",
        upload_type="discrepancy_export",
        uploader_username="testuser@example.com",
        rejected_summary="Error in patient_123_report.pdf",
        lab_unit_id=lu.id
    )
    db_session.add(job)
    db_session.flush()
    
    item = JobItem(
        job_id=job.id,
        filename="patient_456_image.jpg",
        state="error",
        detail="Failed to process patient_456 metadata",
        uploader_username="testuser@example.com"
    )
    db_session.add(item)
    db_session.commit()
    
    payload = db_get_job_payload("export_token")
    
    assert payload["uploader_username"] == sanitize_log_value("testuser@example.com")
    assert payload["rejected_summary"] == sanitize_log_value("Error in patient_123_report.pdf")
    assert payload["items"][0]["filename"] == sanitize_log_value("patient_456_image.jpg")
    assert payload["items"][0]["detail"] == sanitize_log_value("Failed to process patient_456 metadata")
    assert payload["items"][0]["uploader_username"] == sanitize_log_value("testuser@example.com")

def test_job_payload_preserves_pii_for_upload(db_session, test_setup):
    lu, disease, admin = test_setup
    
    # Create an upload job
    job = Job(
        token="upload_token",
        upload_type="direct image",
        uploader_username="uploader@example.com",
        rejected_summary="Invalid file: sensitive_report.pdf",
        lab_unit_id=lu.id
    )
    db_session.add(job)
    db_session.flush()
    
    item = JobItem(
        job_id=job.id,
        filename="sensitive_patient_image.jpg",
        state="error",
        detail="Error processing sensitive_patient_image.jpg",
        uploader_username="uploader@example.com"
    )
    db_session.add(item)
    db_session.commit()
    
    payload = db_get_job_payload("upload_token")
    
    # uploader_username is ALWAYS sanitized
    assert payload["uploader_username"] == sanitize_log_value("uploader@example.com")
    
    # Others are preserved for troubleshooting
    assert payload["rejected_summary"] == "Invalid file: sensitive_report.pdf"
    assert payload["items"][0]["filename"] == "sensitive_patient_image.jpg"
    assert payload["items"][0]["detail"] == "Error processing sensitive_patient_image.jpg"

def test_mask_text_emails_filter():
    """Verify that the email masking filter works as expected."""
    from utils.log_sanitize import mask_text_emails
    
    # Test cases
    # mask_text_emails preserves first 2 chars of local part and the full domain
    assert mask_text_emails("Contact: user@example.com") == "Contact: us***@example.com"
    assert "user@example.com" not in mask_text_emails("Contact: user@example.com")
    
    # Test with multiple emails
    text = "Emails: a@b.net and xyz@y.org"
    masked = mask_text_emails(text)
    # 'a' is <= 2 chars, so becomes '***'
    assert "***@b.net" in masked
    # 'xyz' is > 2 chars, so becomes 'xy***'
    assert "xy***@y.org" in masked
    # Test plain text without emails
    assert mask_text_emails("No emails here") == "No emails here"
