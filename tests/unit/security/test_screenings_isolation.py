
import pytest
from tests.helpers.test_factories import TestDataFactory
from models import EncounterSetImage

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

    def test_screenings_render_encounter_set_images(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session
    ):
        """Set-based screenings should render EncounterSet image media URLs."""
        encounter = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_SET",
            name="Set Based Patient"
        )
        encounter.is_set_based = True
        encounter.zip_file_id = None
        encounter.metadata_json = {
            "encounter": {"remidio_exam_id": "REMIDIO-EXAM-1"},
            "remidio_exam_row_id": 123,
        }
        image = EncounterSetImage(
            patient_encounter_id=encounter.id,
            spatial_position=1,
            original_filename="set_image.jpg",
            folder_rel="files/encounter_sets/test",
            visible_to_grader=True,
        )
        db_session.add(image)
        db_session.flush()

        user = db_session.merge(hosp_a_data_manager)
        client = auth_client(user)

        list_response = client.get("/screenings/", follow_redirects=True)
        assert list_response.status_code == 200
        list_content = list_response.data.decode()
        assert f"/media/encounter_set/img/{image.uuid}/thumbnail" in list_content
        assert "Remidio API" in list_content
        assert "EncounterSet" in list_content

        detail_response = client.get(f"/screenings/{encounter.id}")
        assert detail_response.status_code == 200
        detail_content = detail_response.data.decode()
        assert f"/media/encounter_set/img/{image.uuid}" in detail_content
        assert "Remidio API" in detail_content
        assert "EncounterSet" in detail_content

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
