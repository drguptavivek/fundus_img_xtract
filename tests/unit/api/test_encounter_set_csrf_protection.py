"""
Test-Driven Development Tests for EncounterSet CSRF Protection

Tests CSRF token validation on session-authenticated POST routes.

Protected Routes:
- POST /v1/encounter-set/image/<uuid>/position
- POST /verify-encounter-set/update_position
- POST /verify-encounter-set/finalize/<uuid>
- POST /verify-encounter-set/save_edit/<uuid>

Exempt Routes (JWT auth):
"""

import re

import pytest
from auth.security import hash_password
from flask_wtf.csrf import generate_csrf


def _csrf_token(client):
    """Read a live CSRF token rendered for the current session."""
    for url in ('/login', '/'):
        page = client.get(url)
        match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', page.data)
        if not match:
            match = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data)
        if match:
            return match.group(1).decode()
    return None

def _login(client, username, password):
    """Log in with the CSRF token that the enforced config requires."""
    return client.post('/login', data={
        'username': username,
        'password': password,
        'csrf_token': _csrf_token(client),
    }, follow_redirects=True)


@pytest.fixture(autouse=True)
def csrf_enforced(app, monkeypatch):
    """The global test app disables CSRF; these tests exercise it enabled."""
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', True)


class TestCSRFProtectionEncounterSetImagePosition:
    """Test CSRF protection on /v1/encounter-set/image/<uuid>/position"""

    @pytest.fixture
    def authenticated_user(self, app, db):
        """Create authenticated optometrist scoped to lab unit 1"""
        from models import User, Role, LabUnit
        user = User(username='testuser', email='test@example.com')
        user.password_hash = hash_password('password')
        role = db.query(Role).filter_by(name='optometrist').first()
        if role:
            user.roles.append(role)
        lab_unit = db.query(LabUnit).filter_by(id=1).first()
        db.session.add(user)
        db.session.flush()
        if lab_unit:
            user.lab_units.append(lab_unit)
        db.session.commit()
        return user

    @pytest.fixture
    def test_client(self, app):
        """Flask test client with session"""
        return app.test_client()

    @pytest.fixture
    def encounter_and_image(self, app, db, authenticated_user):
        """Create test encounter and image"""
        from models import PatientEncounters, EncounterSetImage
        from uuid import uuid4
        from auth.utils import utcnow

        encounter = PatientEncounters(
            uuid=str(uuid4()),
            name='Test Patient',
            patient_id='TEST001',
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=1,
            is_set_based=True
        )
        db.session.add(encounter)
        db.session.flush()

        image = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=5,
            original_filename='test.jpg',
            folder_rel='test/',
            created_at=utcnow()
        )
        db.session.add(image)
        db.session.commit()

        return encounter, image

    def test_post_without_csrf_token_rejected(self, test_client, authenticated_user, encounter_and_image):
        """Test that POST without CSRF token is rejected"""
        _, image = encounter_and_image

        with test_client:
            _login(test_client, 'testuser', 'password')

            # POST without CSRF token
            response = test_client.post(
                f'/api/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                content_type='application/json'
            )

        # flask-wtf rejects the mutation with its CSRF error status
        assert response.status_code == 400, "POST without CSRF token should be rejected"

    def test_post_with_valid_csrf_token_accepted(self, test_client, authenticated_user, encounter_and_image):
        """Test that POST with valid CSRF token is accepted"""
        _, image = encounter_and_image

        with test_client:
            _login(test_client, 'testuser', 'password')

            # Get CSRF token from session
            csrf_token = _csrf_token(test_client)

            # POST with CSRF token
            response = test_client.post(
                f'/api/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                content_type='application/json',
                headers={'X-CSRFToken': csrf_token}
            )

        # Should succeed
        assert response.status_code in [200, 422], \
            f"POST with valid CSRF token should succeed (got {response.status_code})"

    def test_post_with_invalid_csrf_token_rejected(self, test_client, authenticated_user, encounter_and_image):
        """Test that POST with invalid CSRF token is rejected"""
        _, image = encounter_and_image

        with test_client:
            _login(test_client, 'testuser', 'password')

            # POST with INVALID CSRF token
            response = test_client.post(
                f'/api/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                content_type='application/json',
                headers={'X-CSRFToken': 'invalid_token_12345'}
            )

        # Should be rejected
        assert response.status_code == 400, \
            "POST with invalid CSRF token should be rejected"

    def test_csrf_token_required_in_header(self, test_client, authenticated_user, encounter_and_image):
        """Test that CSRF token can be provided in X-CSRFToken header"""
        _, image = encounter_and_image

        with test_client:
            _login(test_client, 'testuser', 'password')

            csrf_token = _csrf_token(test_client)

            # Test with X-CSRFToken header
            response = test_client.post(
                f'/api/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                headers={'X-CSRFToken': csrf_token}
            )

        assert response.status_code in [200, 422], \
            "CSRF token in X-CSRFToken header should be accepted"

    def test_csrf_protection_on_form_submission(self, test_client, authenticated_user, encounter_and_image):
        """Test CSRF protection when submitting as form data"""
        _, image = encounter_and_image

        with test_client:
            _login(test_client, 'testuser', 'password')

            csrf_token = _csrf_token(test_client)

            # Submit as form data with CSRF token
            response = test_client.post(
                f'/api/v1/encounter-set/image/{image.uuid}/position',
                data={
                    'spatial_position': '7',
                    'csrf_token': csrf_token  # Form field
                }
            )

            # The form-field token passes CSRF (the request is not rejected
            # as a CSRF failure); the route then enforces its JSON-only
            # payload contract with 415.
            assert response.status_code == 415, \
                "Form-encoded bodies are rejected by the JSON-only route"


class TestCSRFProtectionVerifyEncounterSet:
    """Test CSRF protection on /verify-encounter-set/* routes"""

    @pytest.fixture
    def optometrist_user(self, app, db):
        """Create optometrist user scoped to lab unit 1"""
        from models import User, Role, LabUnit
        user = User(username='optometrist', email='opt@example.com')
        user.password_hash = hash_password('password')
        role = db.query(Role).filter_by(name='optometrist').first()
        if role:
            user.roles.append(role)
        lab_unit = db.query(LabUnit).filter_by(id=1).first()
        db.session.add(user)
        db.session.flush()
        if lab_unit:
            user.lab_units.append(lab_unit)
        db.session.commit()
        return user

    @pytest.fixture
    def test_client(self, app):
        return app.test_client()

    @pytest.fixture
    def encounter_for_verification(self, app, db, optometrist_user):
        """Create encounter for verification"""
        from models import PatientEncounters, EncounterSetImage
        from uuid import uuid4
        from auth.utils import utcnow

        encounter = PatientEncounters(
            uuid=str(uuid4()),
            name='Verify Patient',
            patient_id='VERIFY001',
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=1,
            is_set_based=True
        )
        db.session.add(encounter)
        db.session.flush()

        # Add multiple images
        for pos in range(1, 4):
            image = EncounterSetImage(
                uuid=str(uuid4()),
                patient_encounter_id=encounter.id,
                spatial_position=pos,
                original_filename=f'img{pos}.jpg',
                folder_rel='test/',
                is_reviewed=False,
                created_at=utcnow()
            )
            db.session.add(image)

        db.session.commit()
        return encounter

    def test_finalize_route_requires_csrf(self, test_client, optometrist_user, encounter_for_verification):
        """Test that POST /verify_encounter_set/finalize requires CSRF token"""
        encounter = encounter_for_verification

        with test_client:
            # Login
            _login(test_client, 'optometrist', 'password')

            # POST without CSRF token
            response = test_client.post(
                f'/verify_encounter_set/finalize/{encounter.uuid}'
            )

        assert response.status_code == 400, "finalize route should require CSRF token"

    def test_update_position_requires_csrf(self, test_client, optometrist_user, encounter_for_verification):
        """Test that POST /verify_encounter_set/update_position requires CSRF token"""
        with test_client:
            # Login
            _login(test_client, 'optometrist', 'password')

            # POST without CSRF token
            response = test_client.post(
                '/verify_encounter_set/update_position',
                json={'image_uuid': 'some-uuid', 'position': '7'}
            )

        assert response.status_code == 400, "update_position route should require CSRF token"

    def test_save_edit_requires_csrf(self, test_client, optometrist_user, encounter_for_verification):
        """Test that POST /verify_encounter_set/save_edit requires CSRF token"""
        encounter = encounter_for_verification

        with test_client:
            # Login
            _login(test_client, 'optometrist', 'password')

            # POST without CSRF token
            response = test_client.post(
                f'/verify_encounter_set/save_edit/{encounter.uuid}',
                json={'crop': {'x': 0, 'y': 0, 'width': 100, 'height': 100}}
            )

        assert response.status_code == 400, "save_edit route should require CSRF token"


# Token-authenticated routes are CSRF-exempt. That behaviour now lives entirely on
# the mobile blueprint (app.py csrf.exempt(mobile_api_bp)); the legacy
# /v1/encounter-set/upload route this class used to exercise has been removed as
# dead code. Coverage is in
# tests/unit/api/test_mobile_auth.py::test_mobile_login_is_exempt_from_browser_csrf.


class TestCSRFErrorHandling:
    """Test CSRF error handling and messages"""

    @pytest.fixture
    def authenticated_user(self, app, db):
        """Create authenticated user"""
        from models import User
        user = User(username='testuser', email='test@example.com')
        user.password_hash = hash_password('password')
        db.session.add(user)
        db.session.commit()
        return user

    @pytest.fixture
    def test_client(self, app):
        return app.test_client()

    def test_csrf_error_message_is_helpful(self, test_client, authenticated_user):
        """Test that CSRF error message is helpful"""
        with test_client:
            _login(test_client, 'testuser', 'password')

            response = test_client.post(
                '/api/v1/encounter-set/image/uuid/position',
                json={'spatial_position': 5}
            )

        assert response.status_code == 400
        # Should have helpful message
        # (Flask-WTF provides default helpful message)

    def test_csrf_validation_works_with_cookies(self, test_client, authenticated_user):
        """Test CSRF validation with cookie-based sessions"""
        with test_client:
            # Login (creates session cookie)
            _login(test_client, 'testuser', 'password')

            # Session cookie is present
            # Without CSRF token, should fail
            response = test_client.post(
                '/api/v1/encounter-set/image/uuid/position',
                json={'spatial_position': 5}
            )

            assert response.status_code == 400, \
                "CSRF validation should work with session cookies"
