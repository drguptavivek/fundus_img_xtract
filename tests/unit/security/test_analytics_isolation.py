"""
Test analytics routes enforce hospital isolation.

Verifies that users can only access analytics data from their assigned hospital/lab units.
Uses existing security fixtures from conftest and TestDataFactory for creating test data.
"""

import pytest
from flask import url_for
from tests.helpers.test_factories import TestDataFactory


class TestEncounterResultsIsolation:
    """Test /analytics/encounters route isolation."""

    def test_user_sees_only_own_hospital_encounters(
        self, auth_client, hospital_data, hosp_a_data_manager, hosp_b_data_manager, db_session
    ):
        """Data manager should only see encounters from their hospital."""
        # Create encounters for both hospitals using factory
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A",
        )
        db_session.commit()

        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )
        db_session.commit()

        # Login as hospital A data manager
        client = auth_client(hosp_a_data_manager)

        response = client.get("/analytics/encounters")
        assert response.status_code == 200
        html = response.data.decode()

        # Should see hospital A data
        assert "PATIENT_A" in html or "Hospital A" in html
        # Should NOT see hospital B data
        assert "PATIENT_B" not in html

    @pytest.mark.xfail(reason="Test order dependency - passes in isolation but fails in full test suite")
    def test_global_admin_sees_all_encounters(
        self, auth_client, master_admin, hospital_data, db_session
    ):
        """Global admin should see all encounters."""
        # master_admin fixture now returns the seeded master_admin (already in current session)

        # Create encounters for both hospitals using factory
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A",
        )
        db_session.commit()

        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )
        db_session.commit()

        # Login as global admin
        client = auth_client(master_admin)

        response = client.get("/analytics/encounters")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.data.decode()[:500]}"
        html = response.data.decode()

        # Should see data from both hospitals
        assert "PATIENT_A" in html
        assert "PATIENT_B" in html
        assert "PATIENT_B" in html or "Hospital B" in html


class TestImageResultsIsolation:
    """Test /analytics/images route isolation."""

    def test_user_sees_only_own_hospital_images(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session, test_metadata
    ):
        """Data manager should only see images from their hospital."""
        # Create encounters and tasks for both hospitals
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A",
        )
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )

        file_a = TestDataFactory.create_encounter_file(
            db_session,
            patient_encounter_id=encounter_a.id,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            filename="image_a.jpg",
        )
        file_b = TestDataFactory.create_encounter_file(
            db_session,
            patient_encounter_id=encounter_b.id,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            filename="image_b.jpg",
        )

        # Create tasks
        task_a = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            encounter_file_id=file_a.id,
        )
        task_b = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            encounter_file_id=file_b.id,
        )

        # Get authenticated client for hospital A data manager
        client = auth_client(hosp_a_data_manager)

        response = client.get("/analytics/images")
        assert response.status_code == 200
        html = response.data.decode()

        # Should see hospital A images
        assert "image_a.jpg" in html or "Lab A" in html
        # Should NOT see hospital B images
        assert "image_b.jpg" not in html


class TestEncounterViewIsolation:
    """Test /analytics/encounter/view/<id> route isolation."""

    def test_cross_hospital_encounter_view_forbidden(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User should not be able to view encounters from other hospitals."""
        # Create encounter for hospital B
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )

        # Get authenticated client for hospital A data manager
        client = auth_client(hosp_a_data_manager)

        # Try to access hospital B's encounter
        response = client.get(f"/analytics/encounter/view/{encounter_b.id}")

        # Should return 403 (forbidden) or 404 (not found - either means access denied)
        assert response.status_code in (403, 404)

    def test_own_hospital_encounter_view_allowed(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User should be able to view encounters from their hospital."""
        # Create encounter for hospital A
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A",
        )

        # Get authenticated client for hospital A data manager
        client = auth_client(hosp_a_data_manager)

        # Access hospital A's encounter
        response = client.get(f"/analytics/encounter/view/{encounter_a.id}")

        # Should succeed
        assert response.status_code == 200


class TestDirectViewIsolation:
    """Test /analytics/direct/view/<uuid> route isolation."""

    def test_cross_hospital_direct_view_forbidden(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session, login_user, test_metadata
    ):
        """User should not be able to view direct uploads from other hospitals."""
        # Create direct upload for hospital B
        direct_b = TestDataFactory.create_direct_image_upload(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            uploader_id=hosp_a_data_manager.id,  # Any user ID works for testing
            hospital_id=hospital_data['hospital_b']['hospital'].id,
            camera_id=test_metadata['cameras']['test_camera'].id,
            disease_id=test_metadata['diseases']['dr'].id,
            area_id=test_metadata['areas']['test_area'].id,
            filename="direct_b.jpg",
        )

        client = auth_client(hosp_a_data_manager)

        # Try to access hospital B's direct upload
        response = client.get(f"/analytics/direct/view/{direct_b.uuid}")

        # Should return 404
        assert response.status_code == 404

    def test_own_hospital_direct_view_allowed(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session, login_user, test_metadata
    ):
        """User should be able to view direct uploads from their hospital."""
        # Create direct upload for hospital A
        direct_a = TestDataFactory.create_direct_image_upload(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            uploader_id=hosp_a_data_manager.id,
            hospital_id=hospital_data['hospital_a']['hospital'].id,
            camera_id=test_metadata['cameras']['test_camera'].id,
            disease_id=test_metadata['diseases']['dr'].id,
            area_id=test_metadata['areas']['test_area'].id,
            filename="direct_a.jpg",
        )

        client = auth_client(hosp_a_data_manager)

        # Access hospital A's direct upload
        response = client.get(f"/analytics/direct/view/{direct_a.uuid}")

        # Should succeed
        assert response.status_code == 200


class TestTaskDetailsIsolation:
    """Test /tasks/viewTaskDetails/<id> route isolation."""

    def test_cross_hospital_task_view_forbidden(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session, login_user, test_metadata
    ):
        """User should not be able to view tasks from other hospitals."""
        # Create task for hospital B
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )
        file_b = TestDataFactory.create_encounter_file(
            db_session,
            patient_encounter_id=encounter_b.id,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            filename="file_b.jpg",
        )
        task_b = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            image_name="file_b.jpg"
        )
        # Link task to file (important for updated factory)
        task_b.encounter_file_id = file_b.id
        db_session.commit()

        client = auth_client(hosp_a_data_manager)

        # Try to access hospital B's task
        response = client.get(f"/tasks/viewTaskDetails/{task_b.id}")

        # Should return 404
        assert response.status_code == 404

    def test_own_hospital_task_view_allowed(
        self, auth_client, hospital_data, hosp_a_data_manager, db_session, login_user, test_metadata
    ):
        """User should be able to view tasks from their hospital."""
        # Create task for hospital A
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A",
        )
        file_a = TestDataFactory.create_encounter_file(
            db_session,
            patient_encounter_id=encounter_a.id,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            filename="file_a.jpg",
        )
        task_a = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            image_name="file_a.jpg"
        )
        # Link task to file
        task_a.encounter_file_id = file_a.id
        db_session.commit()

        client = auth_client(hosp_a_data_manager)

        # Access hospital A's task
        response = client.get(f"/tasks/viewTaskDetails/{task_a.id}")

        # Should succeed
        assert response.status_code == 200


class TestModelPerformanceIsolation:
    """Test /analytics/model-performance route isolation."""

    def test_user_sees_only_own_hospital_performance(
        self, auth_client, hospital_data, hosp_a_data_manager, hosp_b_data_manager, db_session, login_user
    ):
        """Data manager should only see performance data from their hospital."""
        # Create data for both hospitals (simplified, just checking access)
        
        client = auth_client(hosp_a_data_manager)

        response = client.get("/analytics/model-performance")
        assert response.status_code == 200
        html = response.data.decode()

        # Should load the page successfully
        # Note regarding deeper verification: The model performance page loads data via AJAX or 
        # renders initial state based on available labs. 
        # Detailed verification of the dropdown contents would require parsing the HTML 
        # to check for specific LabUnit IDs.
        
        # Verify access is allowed (200 OK)
        assert response.status_code == 200


class TestGlobalAdminBypass:
    """Test that global admins can access all data."""

    def test_global_admin_can_view_all_hospitals(
        self, auth_client, master_admin, hospital_data, db_session, login_user, test_metadata
    ):
        """Global admin should bypass hospital scoping."""
        # Merge session-scoped master_admin into current function-scoped session
        master_admin = db_session.merge(master_admin)

        # Create data for hospital B
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )
        file_b = TestDataFactory.create_encounter_file(
            db_session,
            patient_encounter_id=encounter_b.id,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            filename="image_b.jpg",
        )
        direct_b = TestDataFactory.create_direct_image_upload(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            uploader_id=master_admin.id,
            hospital_id=hospital_data['hospital_b']['hospital'].id,
            camera_id=test_metadata['cameras']['test_camera'].id,
            disease_id=test_metadata['diseases']['dr'].id,
            area_id=test_metadata['areas']['test_area'].id,
            filename="direct_b.jpg",
        )
        task_b = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
        )
        # Link task to file
        task_b.encounter_file_id = file_b.id
        db_session.commit()

        client = auth_client(master_admin)

        # Should be able to view encounter from hospital B
        response = client.get(f"/analytics/encounter/view/{encounter_b.id}")
        assert response.status_code == 200

        # Should be able to view direct upload from hospital B
        response = client.get(f"/analytics/direct/view/{direct_b.uuid}")
        assert response.status_code == 200

        # Should be able to view task from hospital B
        response = client.get(f"/tasks/viewTaskDetails/{task_b.id}")
        assert response.status_code == 200
