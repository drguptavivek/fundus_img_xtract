"""
Unit tests for Export File Encryption (AES-256-GCM).

Test IDs from PII_Exposure_Control_Policy.md:
- PII-ENC-001: Export encryption with correct password succeeds
- PII-ENC-002: Export decryption with wrong password fails
- PII-ENC-003: Encrypted files maintain data integrity

Bead: 5N-3 (fundus_img_xtract-o25)
"""

import pytest
import os
import tempfile
from pathlib import Path

from utils.encryption import (
    generate_export_key,
    encrypt_export_file,
    decrypt_export_file,
    EncryptionError
)


class TestExportEncryption:
    """Tests for export file encryption utilities."""
    
    @pytest.fixture
    def test_file(self, tmp_path):
        """Create a temporary test file with known content."""
        test_file = tmp_path / "test_export.csv"
        test_content = b"patient_id,patient_name,diagnosis\n001,John Doe,DR\n002,Jane Smith,Glaucoma\n"
        test_file.write_bytes(test_content)
        return test_file, test_content
    
    def test_generate_export_key_creates_unique_keys(self):
        """Different passwords should generate different keys."""
        key1, salt1 = generate_export_key("password1")
        key2, salt2 = generate_export_key("password2")
        
        assert key1 != key2
        assert salt1 != salt2
        assert len(key1) == 32  # 256 bits
        assert len(salt1) == 32
    
    def test_generate_export_key_with_same_salt_reproducible(self):
        """Same password and salt should generate same key."""
        password = "test_password"
        salt = b"a" * 32
        
        key1, _ = generate_export_key(password, salt)
        key2, _ = generate_export_key(password, salt)
        
        assert key1 == key2
    
    def test_encrypt_export_file_creates_encrypted_file(self, test_file):
        """Encryption should create encrypted file."""
        file_path, original_content = test_file
        password = "secure_password_123"
        
        encrypted_path = encrypt_export_file(str(file_path), password)
        
        assert os.path.exists(encrypted_path)
        assert encrypted_path == str(file_path) + '.enc'
        
        # Encrypted content should be different from original
        with open(encrypted_path, 'rb') as f:
            encrypted_content = f.read()
        
        assert encrypted_content != original_content
        assert len(encrypted_content) > len(original_content)  # Has salt, nonce, tag
        
        # Clean up
        os.remove(encrypted_path)
    
    def test_encrypt_decrypt_roundtrip_preserves_data(self, test_file):
        """Encrypt then decrypt should preserve original data."""
        file_path, original_content = test_file
        password = "my_secure_password"
        
        # Encrypt
        encrypted_path = encrypt_export_file(str(file_path), password)
        
        # Decrypt
        decrypted_path = decrypt_export_file(encrypted_path, password)
        
        # Verify decrypted content matches original
        with open(decrypted_path, 'rb') as f:
            decrypted_content = f.read()
        
        assert decrypted_content == original_content
        
        # Clean up
        os.remove(encrypted_path)
        os.remove(decrypted_path)
    
    def test_decrypt_with_wrong_password_fails(self, test_file):
        """Decryption with wrong password should fail."""
        file_path, _ = test_file
        correct_password = "correct_password"
        wrong_password = "wrong_password"
        
        # Encrypt with correct password
        encrypted_path = encrypt_export_file(str(file_path), correct_password)
        
        # Try to decrypt with wrong password
        with pytest.raises(EncryptionError) as exc_info:
            decrypt_export_file(encrypted_path, wrong_password)
        
        assert "wrong password or corrupted file" in str(exc_info.value).lower()
        
        # Clean up
        os.remove(encrypted_path)
    
    def test_decrypt_corrupted_file_fails(self, tmp_path):
        """Decryption of corrupted file should fail."""
        # Create a corrupted "encrypted" file
        corrupted_file = tmp_path / "corrupted.enc"
        corrupted_file.write_bytes(b"not_a_valid_encrypted_file")
        
        with pytest.raises(EncryptionError) as exc_info:
            decrypt_export_file(str(corrupted_file), "any_password")
        
        assert "too small" in str(exc_info.value).lower()
    
    def test_encrypt_with_custom_output_path(self, test_file):
        """Encryption should respect custom output path."""
        file_path, _ = test_file
        custom_output = str(file_path.parent / "custom_encrypted.bin")
        password = "test_password"
        
        encrypted_path = encrypt_export_file(str(file_path), password, custom_output)
        
        assert encrypted_path == custom_output
        assert os.path.exists(custom_output)
        
        # Clean up
        os.remove(custom_output)
    
    def test_decrypt_with_custom_output_path(self, test_file):
        """Decryption should respect custom output path."""
        file_path, original_content = test_file
        custom_output = str(file_path.parent / "custom_decrypted.csv")
        password = "test_password"
        
        # Encrypt
        encrypted_path = encrypt_export_file(str(file_path), password)
        
        # Decrypt with custom output
        decrypted_path = decrypt_export_file(encrypted_path, password, custom_output)
        
        assert decrypted_path == custom_output
        assert os.path.exists(custom_output)
        
        # Verify content
        with open(custom_output, 'rb') as f:
            assert f.read() == original_content
        
        # Clean up
        os.remove(encrypted_path)
        os.remove(custom_output)
    
    def test_encrypt_large_file(self, tmp_path):
        """Encryption should handle larger files."""
        # Create a 1MB test file
        large_file = tmp_path / "large_export.csv"
        large_content = b"data," * 250000  # ~1MB
        large_file.write_bytes(large_content)
        
        password = "test_password"
        
        # Encrypt and decrypt
        encrypted_path = encrypt_export_file(str(large_file), password)
        decrypted_path = decrypt_export_file(encrypted_path, password)
        
        # Verify
        with open(decrypted_path, 'rb') as f:
            assert f.read() == large_content
        
        # Clean up
        os.remove(encrypted_path)
        os.remove(decrypted_path)
    
    def test_encrypt_empty_file(self, tmp_path):
        """Encryption should handle empty files."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_bytes(b"")
        
        password = "test_password"
        
        # Encrypt and decrypt
        encrypted_path = encrypt_export_file(str(empty_file), password)
        decrypted_path = decrypt_export_file(encrypted_path, password)
        
        # Verify
        with open(decrypted_path, 'rb') as f:
            assert f.read() == b""
        
        # Clean up
        os.remove(encrypted_path)
        os.remove(decrypted_path)
    
    def test_encrypted_file_format(self, test_file):
        """Encrypted file should have correct format (salt + nonce + ciphertext)."""
        file_path, _ = test_file
        password = "test_password"
        
        encrypted_path = encrypt_export_file(str(file_path), password)
        
        with open(encrypted_path, 'rb') as f:
            data = f.read()
        
        # Should have at least: 32 bytes salt + 12 bytes nonce + 16 bytes tag + data
        assert len(data) >= 60
        
        # First 32 bytes should be salt (random, not all zeros)
        salt = data[:32]
        assert salt != b'\x00' * 32
        
        # Next 12 bytes should be nonce (random, not all zeros)
        nonce = data[32:44]
        assert nonce != b'\x00' * 12
        
        # Clean up
        os.remove(encrypted_path)
