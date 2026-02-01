"""
Test-Driven Development Tests for File Size Limits

Tests that oversized files are rejected before processing to prevent:
- Disk space exhaustion (DoS)
- Memory exhaustion
- Slow uploads
"""

import pytest
from io import BytesIO


class TestFileSizeLimits:
    """Test file size validation on upload"""

    @pytest.fixture
    def valid_jwt_token(self):
        """Generate valid JWT token for testing"""
        from api.encounter_set import generate_mobile_token
        return generate_mobile_token(hospital_id=1, lab_unit_id=1, allowed_diseases=[1])

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    def test_small_file_accepted(self, test_client, valid_jwt_token):
        """Test that small files (< 50MB) are accepted"""
        # Create 5MB file
        small_file = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (5 * 1024 * 1024))
        small_file.seek(0)

        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (small_file, 'image.jpg', 'image/jpeg')
            }
        )

        # Should succeed (201 Created)
        assert response.status_code == 201, f"Small file should be accepted (got {response.status_code})"

    def test_max_size_file_accepted(self, test_client, valid_jwt_token):
        """Test that file at MAX_FILE_SIZE (50MB) is accepted"""
        # Create exactly 50MB file
        max_size = 50 * 1024 * 1024
        large_file = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (max_size - 4))
        large_file.seek(0)

        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (large_file, 'image.jpg', 'image/jpeg')
            }
        )

        # Should succeed or fail with reason other than "too large"
        if response.status_code != 201:
            assert 'size' not in response.json.get('error', '').lower() or \
                   'large' not in response.json.get('error', '').lower(), \
                "Should not reject 50MB file due to size"

    def test_oversized_file_rejected(self, test_client, valid_jwt_token):
        """Test that oversized files (> 50MB) are rejected with 413"""
        # Create 51MB file (1MB over limit)
        oversized = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (51 * 1024 * 1024))
        oversized.seek(0)

        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (oversized, 'image.jpg', 'image/jpeg')
            }
        )

        # Should be rejected with 413 Payload Too Large
        assert response.status_code == 413, \
            f"Oversized file should return 413 (got {response.status_code})"
        assert 'size' in response.json.get('error', '').lower() or \
               'large' in response.json.get('error', '').lower(), \
            "Error message should mention file size"

    def test_very_large_file_rejected(self, test_client, valid_jwt_token):
        """Test that extremely large files (100MB+) are rejected"""
        # Create 100MB file
        very_large = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (100 * 1024 * 1024))
        very_large.seek(0)

        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (very_large, 'image.jpg', 'image/jpeg')
            }
        )

        # Should be rejected
        assert response.status_code == 413, "Very large file should be rejected"

    def test_empty_file_still_validated(self, test_client, valid_jwt_token):
        """Test that empty files are still validated for type/magic bytes"""
        empty_file = BytesIO(b'')
        empty_file.seek(0)

        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (empty_file, 'image.jpg', 'image/jpeg')
            }
        )

        # Should be rejected for invalid image (not magic byte error, but file validation)
        assert response.status_code in [400, 413], \
            "Empty file should be rejected"

    def test_error_message_includes_size_info(self, test_client, valid_jwt_token):
        """Test that error message for oversized files is helpful"""
        oversized = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (60 * 1024 * 1024))
        oversized.seek(0)

        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (oversized, 'image.jpg', 'image/jpeg')
            }
        )

        assert response.status_code == 413
        error_msg = response.json.get('message', '') or response.json.get('error', '')
        error_msg = error_msg.lower()

        # Should mention limits or size
        assert '50mb' in error_msg or 'mb' in error_msg or 'size' in error_msg, \
            f"Error message should mention size limit: {error_msg}"

    def test_multiple_files_size_check(self, test_client, valid_jwt_token):
        """Test that size checking works for each file independently"""
        # Create 2 files: one small, one large
        small = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (5 * 1024 * 1024))
        small.seek(0)

        large = BytesIO(b'\xFF\xD8\xFF\xE0' + b'\x00' * (60 * 1024 * 1024))
        large.seek(0)

        # Upload small - should succeed
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (small, 'image1.jpg', 'image/jpeg')
            }
        )
        assert response.status_code == 201

        # Upload large - should fail
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '6',
                'file': (large, 'image2.jpg', 'image/jpeg')
            }
        )
        assert response.status_code == 413
