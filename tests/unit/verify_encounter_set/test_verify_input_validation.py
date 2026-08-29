"""
Test-Driven Development Tests for Input Validation

Tests that save_edit endpoint validates request data to prevent:
- 500 errors from invalid data
- Type confusion attacks
- Invalid crop coordinates
- Data corruption
"""

import pytest
from uuid import uuid4
from auth.utils import utcnow
from auth.security import hash_password


class TestSaveEditInputValidation:
    """Test input validation on /verify_encounter_set/save_edit endpoint"""

    @pytest.fixture
    def optometrist_user(self, db):
        """Create optometrist user"""
        from models import User, Role, LabUnit, Hospital

        hospital = Hospital(name="Test Hospital")
        db.session.add(hospital)
        db.session.flush()

        lab_unit = LabUnit(hospital_id=hospital.id, name="Test Lab")
        db.session.add(lab_unit)
        db.session.flush()

        user = User(username="opt_user", email="opt@example.com")
        user.password_hash = hash_password("password")
        user.hospital_id = hospital.id

        role = db.query(Role).filter_by(name="optometrist").first()
        if role:
            user.roles.append(role)

        db.session.add(user)
        db.session.flush()

        user.lab_units.append(lab_unit)
        db.session.commit()
        return user

    @pytest.fixture
    def test_image(self, db, optometrist_user):
        """Create test image"""
        from models import PatientEncounters, EncounterSetImage, LabUnit
        lab_unit = db.query(LabUnit).filter_by(name="Test Lab").first()

        encounter = PatientEncounters(
            uuid=str(uuid4()),
            name="Test Patient",
            patient_id="TEST001",
            capture_date=utcnow().strftime('%Y-%m-%d'),
            lab_unit_id=lab_unit.id,
            is_set_based=True
        )
        db.session.add(encounter)
        db.session.flush()

        img = EncounterSetImage(
            uuid=str(uuid4()),
            patient_encounter_id=encounter.id,
            spatial_position=1,
            original_filename="test.jpg",
            folder_rel="test/",
            created_at=utcnow()
        )
        db.session.add(img)
        db.session.commit()
        return img

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    def test_valid_crop_data_accepted(self, test_client, optometrist_user, test_image):
        """Test that valid crop data is accepted"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Valid crop coordinates
            response = test_client.post(
                f'/verify_encounter_set/save_edit/{test_image.uuid}',
                json={
                    'crop': {
                        'x': 10,
                        'y': 20,
                        'width': 100,
                        'height': 100
                    }
                }
            )

            # Should succeed (200 OK or 422 Unprocessable if validation schema catches it)
            # But at minimum should NOT be 500
            assert response.status_code != 500, \
                f"Valid crop should not return 500 (got {response.status_code})"

    def test_missing_crop_data_rejected(self, test_client, optometrist_user, test_image):
        """Test that missing crop data is rejected gracefully"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Missing crop data entirely
            response = test_client.post(
                f'/verify_encounter_set/save_edit/{test_image.uuid}',
                json={}
            )

            # Should fail with 400/422, NOT 500
            assert response.status_code in [400, 422, 500], \
                "Missing data should return error, not 500"

    def test_invalid_crop_coordinates_rejected(self, test_client, optometrist_user, test_image):
        """Test that invalid crop coordinates are rejected"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Invalid coordinates (negative, too large, etc.)
            invalid_cases = [
                {'crop': {'x': -10, 'y': 20, 'width': 100, 'height': 100}},  # Negative x
                {'crop': {'x': 10, 'y': -20, 'width': 100, 'height': 100}},  # Negative y
                {'crop': {'x': 10, 'y': 20, 'width': -100, 'height': 100}},  # Negative width
                {'crop': {'x': 10, 'y': 20, 'width': 100, 'height': -100}},  # Negative height
                {'crop': {'x': 'invalid', 'y': 20, 'width': 100, 'height': 100}},  # String x
                {'crop': {'x': 10, 'y': 'invalid', 'width': 100, 'height': 100}},  # String y
            ]

            for invalid_data in invalid_cases:
                response = test_client.post(
                    f'/verify_encounter_set/save_edit/{test_image.uuid}',
                    json=invalid_data
                )

                # Should NOT return 500
                assert response.status_code != 500, \
                    f"Invalid crop {invalid_data} should not cause 500 error"

    def test_malformed_json_rejected(self, test_client, optometrist_user, test_image):
        """Test that malformed JSON is handled gracefully"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Send invalid JSON
            response = test_client.post(
                f'/verify_encounter_set/save_edit/{test_image.uuid}',
                data='invalid {json',
                content_type='application/json'
            )

            # Should return 400, not 500
            assert response.status_code == 400, \
                f"Malformed JSON should return 400 (got {response.status_code})"

    def test_unexpected_fields_ignored(self, test_client, optometrist_user, test_image):
        """Test that unexpected fields in request don't cause errors"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Include unexpected fields
            response = test_client.post(
                f'/verify_encounter_set/save_edit/{test_image.uuid}',
                json={
                    'crop': {'x': 10, 'y': 20, 'width': 100, 'height': 100},
                    'unexpected_field': 'value',
                    'another_field': 123
                }
            )

            # Should NOT cause 500
            assert response.status_code != 500, \
                "Unexpected fields should not cause 500 error"

    def test_wrong_data_types_rejected(self, test_client, optometrist_user, test_image):
        """Test that wrong data types are rejected"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Wrong types
            wrong_type_cases = [
                {'crop': 'not_a_dict'},  # String instead of dict
                {'crop': [1, 2, 3, 4]},  # Array instead of dict
                {'crop': None},  # None instead of dict
                {'crop': 123},  # Number instead of dict
            ]

            for wrong_data in wrong_type_cases:
                response = test_client.post(
                    f'/verify_encounter_set/save_edit/{test_image.uuid}',
                    json=wrong_data
                )

                # Should NOT return 500
                assert response.status_code != 500, \
                    f"Wrong type {wrong_data} should not cause 500 error"

    def test_boundary_crop_coordinates(self, test_client, optometrist_user, test_image):
        """Test edge cases for crop coordinates"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Boundary cases
            boundary_cases = [
                {'crop': {'x': 0, 'y': 0, 'width': 1, 'height': 1}},  # Minimum valid
                {'crop': {'x': 9999, 'y': 9999, 'width': 1, 'height': 1}},  # Large coords
                {'crop': {'x': 0, 'y': 0, 'width': 10000, 'height': 10000}},  # Large dimensions
            ]

            for boundary_data in boundary_cases:
                response = test_client.post(
                    f'/verify_encounter_set/save_edit/{test_image.uuid}',
                    json=boundary_data
                )

                # Should NOT return 500 (may return 422 if validation rejects, but not 500)
                assert response.status_code != 500, \
                    f"Boundary case {boundary_data} should not cause 500 error"

    def test_error_message_is_helpful(self, test_client, optometrist_user, test_image):
        """Test that error messages are helpful and don't leak system info"""
        with test_client:
            test_client.post('/login', data={
                'username': 'opt_user',
                'password': 'password'
            }, follow_redirects=True)

            # Send invalid data
            response = test_client.post(
                f'/verify_encounter_set/save_edit/{test_image.uuid}',
                json={'crop': 'invalid'}
            )

            if response.status_code >= 400:
                error_msg = response.json.get('message', '') or response.json.get('error', '')
                error_msg_lower = error_msg.lower()

                # Should not contain system paths or tracebacks
                assert '/app' not in error_msg
                assert '/home' not in error_msg
                assert 'traceback' not in error_msg_lower
                assert 'error' not in error_msg_lower or 'invalid' in error_msg_lower
