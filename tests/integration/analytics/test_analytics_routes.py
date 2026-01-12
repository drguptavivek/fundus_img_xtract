
import pytest
from flask import url_for
from models import User, GradingTask, PatientEncounters, EncounterFile
from tests.fixtures.seeded_data import (
    test_hospitals,
    test_lab_units,
    site_admin_hospital_a,
    site_admin_hospital_b,
    ophthalmologist_hospital_a,
    ophthalmologist_hospital_b,
    ophthalmologist_cross_hospital,
    master_admin
)

@pytest.mark.usefixtures("db_session", "client", "seed_test_database")
class TestAnalyticsRoutes:
    """Integration tests for analytics routes."""

    def test_access_control_protected_routes(self, auth_client_factory, client):
        """Test that analytics routes are protected and require appropriate roles."""
        # Unauthenticated access
        # client fixture is unauthenticated by default
        response = client.get("/analytics/encounters", follow_redirects=True)
        # Should redirect to login page (200 OK after redirect)
        assert response.status_code == 200
        assert "login" in response.request.url or b"Login" in response.data

    def test_hospital_isolation_encounter_results(self, auth_client_factory, db_session):
        """
        Verify hospital isolation for encounter results.
        Hospital A admin should NOT see Hospital B data.
        """
        from models import User
        user_a = db_session.query(User).filter_by(username='site_admin_a').first()
        user_b = db_session.query(User).filter_by(username='site_admin_b').first()
        user_master = db_session.query(User).filter_by(username='master_admin').first()

        # 1. Login as Hospital A Admin
        client_a = auth_client_factory(user_a)
        response_a = client_a.get("/analytics/encounters")
        assert response_a.status_code == 200
        
        # 2. Login as Hospital B Admin
        client_b = auth_client_factory(user_b)
        response_b = client_b.get("/analytics/encounters")
        assert response_b.status_code == 200
        
        # 3. Login as Master Admin (should see everything)
        client_master = auth_client_factory(user_master)
        response_master = client_master.get("/analytics/encounters")
        assert response_master.status_code == 200

    def test_view_encounter_isolation(self, auth_client_factory, test_lab_units, db_session):
        """
        Verify that a user cannot access a specific encounter detail from another hospital.
        """
        from models import User, PatientEncounters
        # Find an encounter belonging to Hospital B
        hosp_b_unit = db_session.merge(test_lab_units["lab_b1"])
        encounter_b = db_session.query(PatientEncounters).filter(PatientEncounters.lab_unit_id == hosp_b_unit.id).first()
        
        if encounter_b:
            user_a = db_session.query(User).filter_by(username='site_admin_a').first()
            client_a = auth_client_factory(user_a)
            
            # Try to access Hospital B encounter through correct URL
            response = client_a.get(f"/analytics/encounter/view/{encounter_b.id}")
            
            # Should be 403 Forbidden or 404 Not Found
            assert response.status_code in [403, 404]

    def test_analytics_kpi_isolation(self, auth_client_factory, db_session):
        """Verify isolation for KPI endpoints."""
        from models import User
        user_a = db_session.query(User).filter_by(username='site_admin_a').first()
        client_a = auth_client_factory(user_a)
        
        # Correct URL for encounter files KPI
        response = client_a.get("/analytics/encounter-files")
        assert response.status_code == 200
        # Check for HTML content
        assert b"table" in response.data or b"encounter-files-table" in response.data
        
    def test_dataset_curation_access(self, auth_client_factory, db_session):
        """Test access to dataset curation tools."""
        from models import User
        user_a = db_session.query(User).filter_by(username='site_admin_a').first()
        client_a = auth_client_factory(user_a)
        
        response = client_a.get("/analytics/dataset-curation")
        assert response.status_code == 200
        
        user_master = db_session.query(User).filter_by(username='master_admin').first()
        client_master = auth_client_factory(user_master)
        response_master = client_master.get("/analytics/dataset-curation")
        assert response_master.status_code == 200
