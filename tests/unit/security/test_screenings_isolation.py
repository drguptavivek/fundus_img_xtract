
import pytest
from tests.helpers.test_factories import TestDataFactory

class TestScreeningsIsolation:
    """Test /screenings route isolation."""

    def test_list_screenings_scopes_by_hospital(
        self, auth_client, hospital_data, hosp_a_data_manager, hosp_b_data_manager, db_session
    ):
        """User from H1 should only see screenings from H1."""
        db_session.expunge_all()
        # Create encounters for both hospitals
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A", 
            name="Patient One (Hosp A)"
        )


        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
            name="Patient Two (Hosp B)"
        )


        # Login as Hospital A user
        user = db_session.merge(hosp_a_data_manager)
        client = auth_client(user)
        
        response = client.get("/screenings/", follow_redirects=True)
        assert response.status_code == 200
        content = response.data.decode()
        
        # Should see Hospital A patient
        assert "PATIENT_A" in content
        
        # Should NOT see Hospital B patient
        assert "PATIENT_B" not in content

    def test_screening_detail_access_control(
        self, auth_client, hospital_data, hosp_a_data_manager, hosp_b_data_manager, db_session
    ):
        """User cannot access detail of screening from another hospital."""
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A"
        )


        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B"
        )


        # Login as Hospital A user
        user = db_session.merge(hosp_a_data_manager)
        client = auth_client(user)
        
        # Access allowed encounter (A)
        resp_ok = client.get(f"/screenings/{encounter_a.id}")
        assert resp_ok.status_code == 200
        
        # Access denied encounter (B)
        resp_forbidden = client.get(f"/screenings/{encounter_b.id}")
        assert resp_forbidden.status_code == 403

    def test_reprocess_pdf_access_control(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User cannot reprocess PDF for another hospital."""
        # Hospital B encounter
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B"
        )


        # Login as Hospital A user
        # Login as Hospital A user
        user = db_session.merge(hosp_a_data_manager)
        client = auth_client(user)
        
        # Try to reprocess E2 (different hospital)
        resp = client.post(f"/screenings/reprocess_pdf/{encounter_b.id}", follow_redirects=True)
        
        # Should be forbidden
        assert resp.status_code == 403

    def test_delete_reports_access_control(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User cannot delete reports for another hospital."""
        # Hospital B encounter
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B"
        )


        # Login as Hospital A user
        # Login as Hospital A user
        user = db_session.merge(hosp_a_data_manager)
        client = auth_client(user)
        
        resp = client.post(f"/screenings/delete_reports/{encounter_b.id}", follow_redirects=True)
        assert resp.status_code == 403
