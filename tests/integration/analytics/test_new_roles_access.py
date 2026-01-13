
import pytest
from models import User

@pytest.mark.integration
class TestNewRolesAccess:
    """Verify that new roles (dataset_creator, analytics_viewer) have access to intended routes."""

    def test_analytics_viewer_access(self, app, db_session, analytics_viewer_global):
        """Verify analytics_viewer can access dashboard routes."""
        # Re-fetch user to ensure it's in the current session
        user = db_session.query(User).filter_by(id=analytics_viewer_global.id).first()
        
        # Use FlaskLoginClient's support for user= parameter
        with app.test_client(user=user) as client:
            # Test routes (direct paths)
            paths = [
                '/analytics/encounters',
                '/analytics/encounters-simple',
                '/analytics/image-results',
                '/analytics/images-without-tasks',
                '/analytics/encounter-files/kpi',
                '/analytics/direct-uploads/kpi',
                '/analytics/model-performance'
            ]
            
            for path in paths:
                response = client.get(path)
                assert response.status_code == 200, f"Access denied to {path} for analytics_viewer (status: {response.status_code})"

    def test_dataset_creator_access(self, app, db_session, dataset_creator_global):
        """Verify dataset_creator can access curation routes."""
        user = db_session.query(User).filter_by(id=dataset_creator_global.id).first()
        
        with app.test_client(user=user) as client:
            paths = [
                '/analytics/dataset-curation'
            ]
            
            for path in paths:
                response = client.get(path)
                assert response.status_code == 200, f"Access denied to {path} for dataset_creator (status: {response.status_code})"

    def test_dataset_creator_denied_other_analytics(self, app, db_session, dataset_creator_global):
        """Verify dataset_creator is DENIED access to dashboards they are NOT in."""
        user = db_session.query(User).filter_by(id=dataset_creator_global.id).first()
        
        with app.test_client(user=user) as client:
            path = '/analytics/model-performance'
            response = client.get(path)
            # Should be 403 Forbidden
            assert response.status_code == 403, f"Access SHOULD BE denied to {path} for dataset_creator (status: {response.status_code})"

    def test_optometrist_denied_analytics(self, app, db_session, hosp_a_optometrist):
        """Verify a regular optometrist is DENIED access to analytics."""
        user = db_session.query(User).filter_by(id=hosp_a_optometrist.id).first()
        
        with app.test_client(user=user) as client:
            path = '/analytics/encounters'
            response = client.get(path)
            # Should be 403 Forbidden
            assert response.status_code == 403, f"Access SHOULD BE denied to {path} for optometrist (status: {response.status_code})"
