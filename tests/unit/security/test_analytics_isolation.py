"""
Test analytics routes enforce hospital isolation.

Verifies that users can only access analytics data from their assigned hospital/lab units.
Uses existing security fixtures from conftest.
"""

import pytest
from flask import url_for


class TestEncounterResultsIsolation:
    """Test /analytics/encounters route isolation."""

    def test_user_sees_only_own_hospital_encounters(
        self, client, hospital_data, hosp_a_data_manager, hosp_b_data_manager, db_session
    ):
        """Data manager should only see encounters from their hospital."""
        from models import PatientEncounters, EncounterFile
        from auth.utils import utcnow

        # Create encounters for both hospitals
        encounter_a = PatientEncounters(
            patient_id="PATIENT_A",
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            capture_date_dt=utcnow().date(),
        )
        encounter_b = PatientEncounters(
            patient_id="PATIENT_B",
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add_all([encounter_a, encounter_b])
        db_session.flush()

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
        from models import PatientEncounters
        from auth.utils import utcnow

        # Create encounters for both hospitals
        encounter_a = PatientEncounters(
            patient_id="PATIENT_A",
            lab_unit_id=hospital_data['hospital_a']['lab_units'][0].id,
            capture_date_dt=utcnow().date(),
        )
        encounter_b = PatientEncounters(
            patient_id="PATIENT_B",
            lab_unit_id=hospital_data['hospital_b']['lab_units'][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add_all([encounter_a, encounter_b])
        db_session.flush()

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
        from models import PatientEncounters, EncounterFile, GradingTask
        from auth.utils import utcnow

        # Create encounters and tasks for both hospitals
        encounter_a = PatientEncounters(
            patient_id="PATIENT_A",
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        encounter_b = PatientEncounters(
            patient_id="PATIENT_B",
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add_all([encounter_a, encounter_b])
        db_session.flush()

        file_a = EncounterFile(
            patient_encounter_id=encounter_a.id,
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            filename="image_a.jpg",
            file_type="image",
        )
        file_b = EncounterFile(
            patient_encounter_id=encounter_b.id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            filename="image_b.jpg",
            file_type="image",
        )
        db_session.add_all([file_a, file_b])
        db_session.flush()

        # Create tasks
        task_a = GradingTask(
            encounter_file_id=file_a.id,
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            disease_id=test_metadata["diseases"]["dr"].id,
            state="pending",
        )
        task_b = GradingTask(
            encounter_file_id=file_b.id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            disease_id=test_metadata["diseases"]["dr"].id,
            state="pending",
        )
        db_session.add_all([task_a, task_b])
        db_session.flush()

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
        from models import PatientEncounters
        from auth.utils import utcnow

        # Create encounter for hospital B
        encounter_b = PatientEncounters(
            patient_id="PATIENT_B",
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add(encounter_b)
        db_session.flush()

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
        from models import PatientEncounters
        from auth.utils import utcnow

        # Create encounter for hospital A
        encounter_a = PatientEncounters(
            patient_id="PATIENT_A",
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add(encounter_a)
        db_session.flush()

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
        from models import DirectImageUpload

        # Create direct upload for hospital B
        direct_b = DirectImageUpload(
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            filename="direct_b.jpg",
            verification_status="verified",
        )
        db_session.add(direct_b)
        db_session.flush()

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
        from models import DirectImageUpload

        # Create direct upload for hospital A
        direct_a = DirectImageUpload(
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            filename="direct_a.jpg",
            verification_status="verified",
        )
        db_session.add(direct_a)
        db_session.flush()

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
        from models import PatientEncounters, EncounterFile, GradingTask
        from auth.utils import utcnow

        # Create task for hospital B
        encounter_b = PatientEncounters(
            patient_id="PATIENT_B",
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add(encounter_b)
        db_session.flush()

        file_b = EncounterFile(
            patient_encounter_id=encounter_b.id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            filename="image_b.jpg",
            file_type="image",
        )
        db_session.add(file_b)
        db_session.flush()

        task_b = GradingTask(
            encounter_file_id=file_b.id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            disease_id=test_metadata["diseases"]["dr"].id,
            state="pending",
        )
        db_session.add(task_b)
        db_session.flush()

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
        from models import PatientEncounters, EncounterFile, GradingTask
        from auth.utils import utcnow

        # Create task for hospital A
        encounter_a = PatientEncounters(
            patient_id="PATIENT_A",
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add(encounter_a)
        db_session.flush()

        file_a = EncounterFile(
            patient_encounter_id=encounter_a.id,
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            filename="image_a.jpg",
            file_type="image",
        )
        db_session.add(file_a)
        db_session.flush()

        task_a = GradingTask(
            encounter_file_id=file_a.id,
            lab_unit_id=hospital_data["hospital_a"]["lab_units"][0].id,
            disease_id=test_metadata["diseases"]["dr"].id,
            state="pending",
        )
        db_session.add(task_a)
        db_session.flush()

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
        from models import PatientEncounters, EncounterFile, DirectImageUpload, GradingTask
        from auth.utils import utcnow

        # Create data for hospital B
        encounter_b = PatientEncounters(
            patient_id="PATIENT_B",
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            capture_date_dt=utcnow().date(),
        )
        db_session.add(encounter_b)
        db_session.flush()

        file_b = EncounterFile(
            patient_encounter_id=encounter_b.id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            filename="image_b.jpg",
            file_type="image",
        )
        db_session.add(file_b)
        db_session.flush()

        direct_b = DirectImageUpload(
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            filename="direct_b.jpg",
            verification_status="verified",
        )
        db_session.add(direct_b)
        db_session.flush()

        task_b = GradingTask(
            encounter_file_id=file_b.id,
            lab_unit_id=hospital_data["hospital_b"]["lab_units"][0].id,
            disease_id=test_metadata["diseases"]["dr"].id,
            state="pending",
        )
        db_session.add(task_b)
        db_session.flush()

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
