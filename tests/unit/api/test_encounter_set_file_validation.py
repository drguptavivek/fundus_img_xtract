"""
Test-Driven Development Tests for EncounterSet File Upload Validation

Tests file extension, magic bytes, and MIME type validation to prevent:
- Remote Code Execution (RCE)
- Malicious file uploads
- File type spoofing
"""

import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock
from api.encounter_set import upload_encounter_set_image
from models import PatientEncounters, EncounterSetImage
from auth.decorators import token_auth_required
from db_transaction_manager import transaction_scope


class TestFileExtensionValidation:
    """Test file extension whitelist validation"""

    @pytest.fixture
    def valid_jwt_token(self):
        """Generate valid JWT token for testing"""
        from api.encounter_set import generate_mobile_token
        return generate_mobile_token(hospital_id=1, lab_unit_id=1, allowed_diseases=[1])

    @pytest.fixture
    def test_client(self, app):
        """Flask test client"""
        return app.test_client()

    # =========================================================================
    # VALID EXTENSIONS - SHOULD SUCCEED
    # =========================================================================

    @pytest.mark.parametrize("ext,mime", [
        ('.jpg', 'image/jpeg'),
        ('.jpeg', 'image/jpeg'),
        ('.png', 'image/png'),
        ('.gif', 'image/gif'),
        ('.bmp', 'image/bmp'),
        ('.JPG', 'image/jpeg'),  # Case insensitive
        ('.PNG', 'image/png'),
    ])
    def test_valid_extensions_accepted(self, test_client, valid_jwt_token, ext, mime):
        """Test that valid image extensions are accepted"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (f'image{ext}', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, mime)  # JPEG magic bytes
            }
        )
        # Should return 201 Created (successful upload)
        assert response.status_code == 201, f"Extension {ext} should be accepted"
        assert 'encounter_uuid' in response.json
        assert 'image_uuid' in response.json

    # =========================================================================
    # INVALID EXTENSIONS - SHOULD FAIL
    # =========================================================================

    @pytest.mark.parametrize("ext,description", [
        ('.php', 'PHP executable'),
        ('.exe', 'Windows executable'),
        ('.sh', 'Shell script'),
        ('.bat', 'Batch file'),
        ('.aspx', 'ASP.NET'),
        ('.jsp', 'Java Server Page'),
        ('.py', 'Python script'),
        ('.js', 'JavaScript'),
        ('.zip', 'ZIP archive'),
        ('.rar', 'RAR archive'),
        ('.pdf', 'PDF document'),
        ('.doc', 'Word document'),
        ('.txt', 'Text file'),
        ('', 'No extension'),
        ('.unknown', 'Unknown extension'),
    ])
    def test_invalid_extensions_rejected(self, test_client, valid_jwt_token, ext, description):
        """Test that invalid file extensions are rejected"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (f'malicious{ext}', b'malicious content', 'application/octet-stream')
            }
        )
        # Should return 400 Bad Request
        assert response.status_code == 400, f"Extension {ext} ({description}) should be rejected"
        assert 'Invalid file format' in response.json.get('error', '')

    # =========================================================================
    # MAGIC BYTE VALIDATION - VERIFY ACTUAL FILE CONTENT
    # =========================================================================

    class MagicBytes:
        """Common file magic bytes (signatures)"""
        JPEG = b'\xFF\xD8\xFF\xE0'  # JPEG SOI marker
        JPEG_ALT = b'\xFF\xD8\xFF\xE1'  # JPEG EXIF
        PNG = b'\x89PNG\r\n\x1a\n'
        GIF87 = b'GIF87a'
        GIF89 = b'GIF89a'
        BMP = b'BM'
        FAKE_JPEG = b'This looks like JPEG but isnt'
        EXECUTABLE = b'MZ'  # Windows PE executable
        ELF = b'\x7fELF'  # Linux executable

    @pytest.mark.parametrize("magic_bytes,mime,is_valid", [
        (MagicBytes.JPEG + b'\x00' * 100, 'image/jpeg', True),
        (MagicBytes.JPEG_ALT + b'\x00' * 100, 'image/jpeg', True),
        (MagicBytes.PNG + b'\x00' * 100, 'image/png', True),
        (MagicBytes.GIF87 + b'\x00' * 100, 'image/gif', True),
        (MagicBytes.GIF89 + b'\x00' * 100, 'image/gif', True),
        (MagicBytes.BMP + b'\x00' * 100, 'image/bmp', True),
        # Invalid magic bytes
        (MagicBytes.FAKE_JPEG, 'image/jpeg', False),
        (MagicBytes.EXECUTABLE + b'\x00' * 100, 'image/jpeg', False),
        (MagicBytes.ELF + b'\x00' * 100, 'image/jpeg', False),
        (b'random data', 'image/jpeg', False),
    ])
    def test_magic_byte_validation(self, test_client, valid_jwt_token, magic_bytes, mime, is_valid):
        """Test that file magic bytes are validated to verify actual content"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('image.jpg', magic_bytes, mime)
            }
        )

        if is_valid:
            assert response.status_code == 201, "Valid magic bytes should be accepted"
        else:
            assert response.status_code == 400, "Invalid magic bytes should be rejected"
            assert 'Invalid image' in response.json.get('error', '')

    def test_magic_bytes_priority_over_extension(self, test_client, valid_jwt_token):
        """Test that magic bytes take priority over file extension"""
        # File with .jpg extension but EXE magic bytes should be rejected
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('shell.jpg', self.MagicBytes.EXECUTABLE + b'\x00' * 100, 'image/jpeg')
            }
        )
        # Should reject based on magic bytes, not extension
        assert response.status_code == 400, "Executable magic bytes should be rejected despite .jpg extension"

    # =========================================================================
    # MIME TYPE VALIDATION - CHECK CONTENT TYPE
    # =========================================================================

    @pytest.mark.parametrize("extension,valid_mimes", [
        ('.jpg', ['image/jpeg', 'image/jpg']),
        ('.jpeg', ['image/jpeg', 'image/jpg']),
        ('.png', ['image/png']),
        ('.gif', ['image/gif']),
        ('.bmp', ['image/bmp']),
    ])
    def test_mime_type_validation(self, test_client, valid_jwt_token, extension, valid_mimes):
        """Test that MIME types are validated for each extension"""
        # Test with valid MIME
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (f'image{extension}', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, valid_mimes[0])
            }
        )
        assert response.status_code == 201, f"Valid MIME {valid_mimes[0]} should be accepted"

        # Test with invalid MIME for extension
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': (f'image{extension}', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, 'application/pdf')
            }
        )
        assert response.status_code == 400, "Invalid MIME type should be rejected"

    # =========================================================================
    # EDGE CASES
    # =========================================================================

    def test_filename_without_extension(self, test_client, valid_jwt_token):
        """Test that files without extension are rejected"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('image', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, 'image/jpeg')
            }
        )
        assert response.status_code == 400, "Files without extension should be rejected"

    def test_double_extension_attack(self, test_client, valid_jwt_token):
        """Test that double extensions (e.g., image.jpg.php) are rejected"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('image.jpg.php', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, 'image/jpeg')
            }
        )
        # Should reject .php extension (last extension checked)
        assert response.status_code == 400

    def test_null_byte_injection(self, test_client, valid_jwt_token):
        """Test that null byte injection is prevented"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('image\x00.php.jpg', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, 'image/jpeg')
            }
        )
        # Should reject (filename validation)
        assert response.status_code in [400, 422]

    def test_case_insensitive_extension_check(self, test_client, valid_jwt_token):
        """Test that extension check is case-insensitive"""
        # Uppercase extension should work
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('IMAGE.JPG', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, 'image/jpeg')
            }
        )
        assert response.status_code == 201, "Uppercase extensions should be accepted"

        # Mixed case invalid extension should fail
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('shell.PhP', b'malicious', 'image/jpeg')
            }
        )
        assert response.status_code == 400, "Invalid extensions should be rejected (case insensitive)"

    # =========================================================================
    # SECURITY - COMMON ATTACK VECTORS
    # =========================================================================

    def test_reject_php_shell(self, test_client, valid_jwt_token):
        """Test that PHP shells are rejected"""
        php_shell = b'<?php system($_GET["cmd"]); ?>'
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('shell.php', php_shell, 'application/x-php')
            }
        )
        assert response.status_code == 400, "PHP files should be rejected"

    def test_reject_aspx_shell(self, test_client, valid_jwt_token):
        """Test that ASPX shells are rejected"""
        aspx_shell = b'<%@ Page Language="C#" %><% System.Diagnostics.Process.Start("cmd.exe"); %>'
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('shell.aspx', aspx_shell, 'application/x-aspx')
            }
        )
        assert response.status_code == 400, "ASPX files should be rejected"

    def test_reject_windows_executable(self, test_client, valid_jwt_token):
        """Test that Windows executables are rejected"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('malware.exe', b'MZ' + b'\x00' * 100, 'application/x-msdownload')
            }
        )
        assert response.status_code == 400, "EXE files should be rejected"

    # =========================================================================
    # ERROR MESSAGES - SHOULD NOT LEAK INFORMATION
    # =========================================================================

    def test_error_messages_dont_leak_system_info(self, test_client, valid_jwt_token):
        """Test that error messages don't leak system information"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('shell.php', b'malicious', 'application/x-php')
            }
        )
        assert response.status_code == 400
        error_msg = response.json.get('error', '').lower()
        # Should not contain system paths, versions, etc.
        assert '/var/www' not in error_msg
        assert 'python' not in error_msg or 'version' not in error_msg
        # Should contain helpful user message
        assert 'invalid' in error_msg or 'rejected' in error_msg

    # =========================================================================
    # STORED FILE - VERIFY SAFE FILENAME USED
    # =========================================================================

    def test_stored_file_has_safe_filename(self, test_client, valid_jwt_token, db):
        """Test that stored file has safe filename, not user-provided one"""
        response = test_client.post(
            '/api/v1/encounter-set/upload',
            headers={'Authorization': f'Bearer {valid_jwt_token}'},
            data={
                'patient_id': 'TEST001',
                'patient_name': 'Test Patient',
                'spatial_position': '5',
                'file': ('my_image_with_long_name.jpg', b'\xFF\xD8\xFF\xE0' + b'\x00' * 100, 'image/jpeg')
            }
        )
        assert response.status_code == 201

        # Get the image UUID
        image_uuid = response.json['image_uuid']

        # Verify stored filename is NOT the user-provided filename
        with transaction_scope() as session:
            img = session.query(EncounterSetImage).filter_by(uuid=image_uuid).first()
            assert img is not None

            # Stored filename should be safe (just UUID + extension)
            # Should NOT be 'my_image_with_long_name.jpg'
            assert img.original_filename != 'my_image_with_long_name.jpg', \
                "Stored filename should not be user-provided name"

            # Verify file path is safe
            assert '..' not in img.original_filename, "Path traversal in filename"
            assert '/' not in img.original_filename, "Path traversal in filename"
            assert '\x00' not in img.original_filename, "Null bytes in filename"
