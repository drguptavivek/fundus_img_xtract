"""
Custom Assertions for Testing

Provides custom assertion helpers for common test scenarios.
"""

from typing import Dict, List, Any


def assert_has_keys(data: Dict, required_keys: List[str], message: str = None):
    """Assert that a dictionary has all required keys"""
    missing_keys = [key for key in required_keys if key not in data]
    if missing_keys:
        msg = message or f"Missing required keys: {missing_keys}"
        raise AssertionError(msg)


def assert_response_success(response, expected_status=200):
    """Assert that a Flask response is successful"""
    assert response.status_code == expected_status, \
        f"Expected status {expected_status}, got {response.status_code}. Response: {response.get_data(as_text=True)}"


def assert_response_error(response, expected_status=400):
    """Assert that a Flask response is an error"""
    assert response.status_code >= expected_status, \
        f"Expected error status >= {expected_status}, got {response.status_code}"


def assert_json_response(response, expected_keys: List[str] = None):
    """Assert that response is valid JSON with expected keys"""
    assert response.content_type == 'application/json' or 'application/json' in response.content_type, \
        f"Expected JSON response, got {response.content_type}"
    
    data = response.get_json()
    assert data is not None, "Response JSON is None"
    
    if expected_keys:
        assert_has_keys(data, expected_keys)
    
    return data


def assert_redirects_to(response, expected_location: str):
    """Assert that response is a redirect to expected location"""
    assert response.status_code in [301, 302, 303, 307, 308], \
        f"Expected redirect status, got {response.status_code}"
    
    assert expected_location in response.location, \
        f"Expected redirect to '{expected_location}', got '{response.location}'"


def assert_flash_message(response, expected_message: str = None, category: str = None):
    """Assert that a flash message was set (requires session access)"""
    # This is a placeholder - actual implementation depends on how flash messages are tested
    pass


def assert_user_has_role(user, role_name: str):
    """Assert that a user has a specific role"""
    assert user.has_role(role_name), \
        f"User {user.username} does not have role '{role_name}'"


def assert_user_has_permission(db_session, user_id: int, disease_id: int, 
                               lab_unit_id: int, permission_type: str):
    """Assert that a user has a specific grading permission"""
    from models import UserDiseaseUnitRole
    
    permission = db_session.query(UserDiseaseUnitRole).filter_by(
        user_id=user_id,
        disease_id=disease_id,
        lab_unit_id=lab_unit_id
    ).first()
    
    assert permission is not None, \
        f"No permission found for user_id={user_id}, disease_id={disease_id}, lab_unit_id={lab_unit_id}"
    
    permission_value = getattr(permission, permission_type, None)
    assert permission_value is True, \
        f"Permission {permission_type} is {permission_value}, expected True"


def assert_rate_limited(response):
    """Assert that response indicates rate limiting"""
    assert response.status_code == 429, \
        f"Expected rate limit status 429, got {response.status_code}"
    
    # Check for rate limit indication in response
    if response.content_type and 'application/json' in response.content_type:
        data = response.get_json()
        assert 'rate limit' in str(data).lower(), \
            "Response does not indicate rate limiting"
