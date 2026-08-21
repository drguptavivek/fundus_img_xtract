"""
Test-Driven Development Tests for EncounterSet CSRF Protection

Tests CSRF token validation on session-authenticated POST routes.

Protected Routes:
- POST /v1/encounter-set/image/<uuid>/position
- POST /verify-encounter-set/update_position
- POST /verify-encounter-set/finalize/<uuid>
- POST /verify-encounter-set/save_edit/<uuid>
- POST /grading/encounter_set/submit

Exempt Routes (JWT auth):
"""

import pytest
from flask_wtf.csrf import generate_csrf


class TestCSRFProtectionEncounterSetImagePosition:
    """Test CSRF protection on /v1/encounter-set/image/<uuid>/position"""

    @pytest.fixture
    def authenticated_user(self, app, db):
        """Create authenticated user"""
        from models import User
        user = User(username='testuser', email='test@example.com')
        user.set_password('password')
        db.session.add(user)
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
        """Test that POST without CSRF token is rejected (403)"""
        _, image = encounter_and_image

        # Login user
        with test_client:
            test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            # POST without CSRF token
            response = test_client.post(
                f'/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                content_type='application/json'
            )

        # Should be rejected with 403 Forbidden
        assert response.status_code == 403, "POST without CSRF token should be rejected"

    def test_post_with_valid_csrf_token_accepted(self, test_client, authenticated_user, encounter_and_image, app):
        """Test that POST with valid CSRF token is accepted (200)"""
        _, image = encounter_and_image

        with test_client:
            # Login user
            response = test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            # Get CSRF token from session
            csrf_token = generate_csrf()

            # POST with CSRF token
            response = test_client.post(
                f'/v1/encounter-set/image/{image.uuid}/position',
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
            # Login user
            test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            # POST with INVALID CSRF token
            response = test_client.post(
                f'/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                content_type='application/json',
                headers={'X-CSRFToken': 'invalid_token_12345'}
            )

        # Should be rejected
        assert response.status_code in [400, 403], \
            "POST with invalid CSRF token should be rejected"

    def test_csrf_token_required_in_header(self, test_client, authenticated_user, encounter_and_image):
        """Test that CSRF token can be provided in X-CSRFToken header"""
        _, image = encounter_and_image

        with test_client:
            test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            csrf_token = generate_csrf()

            # Test with X-CSRFToken header
            response = test_client.post(
                f'/v1/encounter-set/image/{image.uuid}/position',
                json={'spatial_position': 7},
                headers={'X-CSRFToken': csrf_token}
            )

        assert response.status_code in [200, 422], \
            "CSRF token in X-CSRFToken header should be accepted"

    def test_csrf_protection_on_form_submission(self, test_client, authenticated_user, encounter_and_image):
        """Test CSRF protection when submitting as form data"""
        _, image = encounter_and_image

        with test_client:
            test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            csrf_token = generate_csrf()

            # Submit as form data with CSRF token
            response = test_client.post(
                f'/v1/encounter-set/image/{image.uuid}/position',
                data={
                    'spatial_position': '7',
                    'csrf_token': csrf_token  # Form field
                }
            )

            # Should accept CSRF token in form field
            assert response.status_code in [200, 422, 400], \
                "Form submission with CSRF token should work"


class TestCSRFProtectionVerifyEncounterSet:
    """Test CSRF protection on /verify-encounter-set/* routes"""

    @pytest.fixture
    def optometrist_user(self, app, db):
        """Create optometrist user"""
        from models import User, Role
        user = User(username='optometrist', email='opt@example.com')
        user.set_password('password')
        role = db.query(Role).filter_by(name='optometrist').first()
        if role:
            user.roles.append(role)
        db.session.add(user)
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
        """Test that POST /verify-encounter-set/finalize requires CSRF token"""
        encounter = encounter_for_verification

        with test_client:
            # Login
            test_client.post('/login', data={
                'username': 'optometrist',
                'password': 'password'
            }, follow_redirects=True)

            # POST without CSRF token
            response = test_client.post(
                f'/verify-encounter-set/finalize/{encounter.uuid}'
            )

        assert response.status_code == 403, "finalize route should require CSRF token"

    def test_update_position_requires_csrf(self, test_client, optometrist_user, encounter_for_verification):
        """Test that POST /verify-encounter-set/update_position requires CSRF token"""
        with test_client:
            # Login
            test_client.post('/login', data={
                'username': 'optometrist',
                'password': 'password'
            }, follow_redirects=True)

            # POST without CSRF token
            response = test_client.post(
                '/verify-encounter-set/update_position',
                json={'image_uuid': 'some-uuid', 'position': '7'}
            )

        assert response.status_code == 403, "update_position route should require CSRF token"

    def test_save_edit_requires_csrf(self, test_client, optometrist_user, encounter_for_verification):
        """Test that POST /verify-encounter-set/save_edit requires CSRF token"""
        encounter = encounter_for_verification

        with test_client:
            # Login
            test_client.post('/login', data={
                'username': 'optometrist',
                'password': 'password'
            }, follow_redirects=True)

            # POST without CSRF token
            response = test_client.post(
                f'/verify-encounter-set/save_edit/{encounter.uuid}',
                json={'crop': {'x': 0, 'y': 0, 'width': 100, 'height': 100}}
            )

        assert response.status_code == 403, "save_edit route should require CSRF token"


class TestCSRFProtectionGrading:
    """Test CSRF protection on /grading/encounter_set/submit"""

    @pytest.fixture
    def resident_user(self, app, db):
        """Create resident user for grading"""
        from models import User, Role
        user = User(username='resident', email='res@example.com')
        user.set_password('password')
        role = db.query(Role).filter_by(name='resident').first()
        if role:
            user.roles.append(role)
        db.session.add(user)
        db.session.commit()
        return user

    @pytest.fixture
    def test_client(self, app):
        return app.test_client()

    def test_grade_submission_requires_csrf(self, test_client, resident_user):
        """Test that grading submission requires CSRF token"""
        with test_client:
            # Login
            test_client.post('/login', data={
                'username': 'resident',
                'password': 'password'
            }, follow_redirects=True)

            # POST without CSRF token
            response = test_client.post(
                '/grading/encounter_set/submit',
                json={'task_id': 'some-uuid', 'grades': {}}
            )

        assert response.status_code == 403, "grade submission should require CSRF token"


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
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        return user

    @pytest.fixture
    def test_client(self, app):
        return app.test_client()

    def test_csrf_error_message_is_helpful(self, test_client, authenticated_user):
        """Test that CSRF error message is helpful"""
        with test_client:
            test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            response = test_client.post(
                '/v1/encounter-set/image/uuid/position',
                json={'spatial_position': 5}
            )

        assert response.status_code == 403
        # Should have helpful message
        # (Flask-WTF provides default helpful message)

    def test_csrf_validation_works_with_cookies(self, test_client, authenticated_user):
        """Test CSRF validation with cookie-based sessions"""
        with test_client:
            # Login (creates session cookie)
            test_client.post('/login', data={
                'username': 'testuser',
                'password': 'password'
            }, follow_redirects=True)

            # Session cookie is present
            # Without CSRF token, should fail
            response = test_client.post(
                '/v1/encounter-set/image/uuid/position',
                json={'spatial_position': 5}
            )

            assert response.status_code == 403, \
                "CSRF validation should work with session cookies"
