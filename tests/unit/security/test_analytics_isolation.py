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
        self, client, hospital_data, hosp_a_data_manager, hosp_b_data_manager, db_session
    ):
        """Data manager should only see encounters from their hospital."""
        # Create encounters for both hospitals using factory
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

        # Login as hospital A data manager
        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        response = client.get("/analytics/encounters")
        assert response.status_code == 200
        html = response.data.decode()

        # Should see hospital A data
        assert "PATIENT_A" in html or "Hospital A" in html
        # Should NOT see hospital B data
        assert "PATIENT_B" not in html

    def test_global_admin_sees_all_encounters(
        self, client, master_admin, hospital_data, db_session
    ):
        """Global admin should see all encounters."""
        # Create encounters for both hospitals using factory
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

        client.post(
            "/login",
            data={"username": master_admin.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        response = client.get("/analytics/encounters")
        assert response.status_code == 200
        html = response.data.decode()

        # Should see both hospitals
        assert "PATIENT_A" in html or "Hospital A" in html
        assert "PATIENT_B" in html or "Hospital B" in html


class TestImageResultsIsolation:
    """Test /analytics/images route isolation."""

    def test_user_sees_only_own_hospital_images(
        self, client, hospital_data, hosp_a_data_manager, db_session, test_metadata
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

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

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
        self, client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User should not be able to view encounters from other hospitals."""
        # Create encounter for hospital B
        encounter_b = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            patient_id="PATIENT_B",
        )

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Try to access hospital B's encounter
        response = client.get(f"/analytics/encounter/view/{encounter_b.id}")

        # Should return 404 (not found or access denied)
        assert response.status_code == 404

    def test_own_hospital_encounter_view_allowed(
        self, client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User should be able to view encounters from their hospital."""
        # Create encounter for hospital A
        encounter_a = TestDataFactory.create_patient_encounter(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            patient_id="PATIENT_A",
        )

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Access hospital A's encounter
        response = client.get(f"/analytics/encounter/view/{encounter_a.id}")

        # Should succeed
        assert response.status_code == 200


class TestDirectViewIsolation:
    """Test /analytics/direct/view/<uuid> route isolation."""

    def test_cross_hospital_direct_view_forbidden(
        self, client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User should not be able to view direct uploads from other hospitals."""
        # Create direct upload for hospital B
        direct_b = TestDataFactory.create_direct_image_upload(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            filename="direct_b.jpg",
        )

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Try to access hospital B's direct upload
        response = client.get(f"/analytics/direct/view/{direct_b.uuid}")

        # Should return 404
        assert response.status_code == 404

    def test_own_hospital_direct_view_allowed(
        self, client, hospital_data, hosp_a_data_manager, db_session
    ):
        """User should be able to view direct uploads from their hospital."""
        # Create direct upload for hospital A
        direct_a = TestDataFactory.create_direct_image_upload(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            filename="direct_a.jpg",
        )

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Access hospital A's direct upload
        response = client.get(f"/analytics/direct/view/{direct_a.uuid}")

        # Should succeed
        assert response.status_code == 200


class TestTaskDetailsIsolation:
    """Test /analytics/viewTaskDetails/<id> route isolation."""

    def test_cross_hospital_task_view_forbidden(
        self, client, hospital_data, hosp_a_data_manager, db_session, test_metadata
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
            filename="image_b.jpg",
        )
        task_b = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            encounter_file_id=file_b.id,
        )

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Try to access hospital B's task
        response = client.get(f"/analytics/viewTaskDetails/{task_b.id}")

        # Should return 404
        assert response.status_code == 404

    def test_own_hospital_task_view_allowed(
        self, client, hospital_data, hosp_a_data_manager, db_session, test_metadata
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
            filename="image_a.jpg",
        )
        task_a = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            encounter_file_id=file_a.id,
        )

        client.post(
            "/login",
            data={"username": hosp_a_data_manager.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Access hospital A's task
        response = client.get(f"/analytics/viewTaskDetails/{task_a.id}")

        # Should succeed
        assert response.status_code == 200


class TestGlobalAdminBypass:
    """Test that global admins can access all data."""

    def test_global_admin_can_view_all_hospitals(
        self, client, master_admin, hospital_data, db_session, test_metadata
    ):
        """Global admin should bypass hospital scoping."""
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
            filename="direct_b.jpg",
        )
        task_b = TestDataFactory.create_grading_task(
            db_session,
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            disease_id=test_metadata['diseases']['dr'].id,
            encounter_file_id=file_b.id,
        )

        client.post(
            "/login",
            data={"username": master_admin.username, "password": "Test@2026"},
            follow_redirects=True,
        )

        # Should be able to view encounter from hospital B
        response = client.get(f"/analytics/encounter/view/{encounter_b.id}")
        assert response.status_code == 200

        # Should be able to view direct upload from hospital B
        response = client.get(f"/analytics/direct/view/{direct_b.uuid}")
        assert response.status_code == 200

        # Should be able to view task from hospital B
        response = client.get(f"/analytics/viewTaskDetails/{task_b.id}")
        assert response.status_code == 200
