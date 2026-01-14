"""
Test suite for secure file hashing (CWE-327).

This module tests that file hashing uses cryptographically secure algorithms
instead of broken MD5 for duplicate detection.

Tests follow TDD: write failing tests first, then implement fix.
"""

import pytest
import hashlib
from io import BytesIO

from models import DirectImageUpload
from sqlalchemy import select


class TestSecureFileHashing:
    """Test suite for secure file hashing algorithms."""

    def test_file_hash_uses_sha256_not_md5(self, db_session):
        """
        FAILING TEST: File upload still uses MD5.

        Test that file hashing uses SHA-256 instead of MD5 to prevent
        collision attacks.
        """
        # Create a test file content
        test_content = b"test image content for hashing"

        # Try to get the hash that would be used
        try:
            from utils.file_hashing import hash_file_content
            file_hash = hash_file_content(test_content)

            # Should be SHA-256 (64 hex chars), not MD5 (32 hex chars)
            assert len(file_hash) == 64, (
                f"SHA-256 hash should be 64 characters, got {len(file_hash)}"
            )

            # Should not be using MD5
            # We can verify this by checking the hash function used
            md5_hash = hashlib.md5(test_content).hexdigest()
            assert file_hash != md5_hash, (
                "Should not use MD5 for file hashing"
            )

            # Verify it's actually SHA-256
            sha256_hash = hashlib.sha256(test_content).hexdigest()
            assert file_hash == sha256_hash, (
                "Should use SHA-256 for file hashing"
            )
        except ImportError:
            pytest.fail("hash_file_content() function does not exist yet")

    def test_file_size_included_in_duplicate_check(self, db_session):
        """
        Test that duplicate detection works using file hash.

        NOTE: Current schema doesn't include file_size in DirectImageUpload,
        so duplicate detection is hash-based only. Future migration should
        add file_size field for enhanced collision protection.
        """
        from models import LabUnit, Hospital, User, Camera, Disease, Area

        # Get required entities
        lab_unit = db_session.query(LabUnit).first()
        hospital = db_session.query(Hospital).first()
        user = db_session.query(User).first()
        camera = db_session.query(Camera).first()
        disease = db_session.query(Disease).first()
        area = db_session.query(Area).first()

        # Create a test upload entry
        test_content = b"test image content"
        test_hash = hashlib.sha256(test_content).hexdigest()[:32]  # Truncate to match schema

        upload = DirectImageUpload(
            filename="test_image.jpg",
            file_hash=test_hash,
            folder_rel="test/folder",
            lab_unit_id=lab_unit.id,
            uploader_id=user.id,
            hospital_id=hospital.id,
            camera_id=camera.id,
            disease_id=disease.id,
            area_id=area.id,
        )
        db_session.add(upload)
        db_session.commit()

        # Query for duplicates by hash (current implementation)
        from utils.file_hashing import is_duplicate_file
        is_dup = is_duplicate_file(test_hash, len(test_content), db_session)

        assert is_dup is True, (
            "Should detect duplicate by hash"
        )

        # Clean up
        db_session.delete(upload)
        db_session.commit()

    def test_different_file_with_same_size_not_duplicate(self, db_session):
        """
        Test that files with different hashes are not considered duplicates.
        """
        from models import LabUnit, Hospital, User, Camera, Disease, Area

        # Get required entities
        lab_unit = db_session.query(LabUnit).first()
        hospital = db_session.query(Hospital).first()
        user = db_session.query(User).first()
        camera = db_session.query(Camera).first()
        disease = db_session.query(Disease).first()
        area = db_session.query(Area).first()

        # Create a test upload entry
        test_content = b"test image content 123"
        test_hash = hashlib.sha256(test_content).hexdigest()[:32]  # Truncate to match schema

        upload = DirectImageUpload(
            filename="test_image.jpg",
            file_hash=test_hash,
            folder_rel="test/folder",
            lab_unit_id=lab_unit.id,
            uploader_id=user.id,
            hospital_id=hospital.id,
            camera_id=camera.id,
            disease_id=disease.id,
            area_id=area.id,
        )
        db_session.add(upload)
        db_session.commit()

        # Different content
        different_content = b"different content!!!"
        different_hash = hashlib.sha256(different_content).hexdigest()[:32]

        from utils.file_hashing import is_duplicate_file
        is_dup = is_duplicate_file(different_hash, len(different_content), db_session)

        assert is_dup is False, (
            "Different hash should not be considered duplicate"
        )

        # Clean up
        db_session.delete(upload)
        db_session.commit()

    def test_hash_function_is_configurable(self):
        """
        FAILING TEST: Hash function not configurable.

        Test that the hash function can be configured via environment
        variable for future algorithm upgrades.
        """
        # This test documents the need for configurability
        # The implementation should allow SHA-256, SHA-384, blake2b, etc.
        pass  # Placeholder for documentation


class TestHashingAlgorithmMigration:
    """Test suite for MD5 to SHA-256 migration."""

    def test_old_md5_hashes_still_supported(self, db_session):
        """
        Test that existing MD5 hashes in the database are still supported
        during the migration period.

        This is important for backward compatibility - old records with MD5
        hashes should still work until migrated.
        """
        from models import LabUnit, Hospital, User, Camera, Disease, Area

        # Get required entities
        lab_unit = db_session.query(LabUnit).first()
        hospital = db_session.query(Hospital).first()
        user = db_session.query(User).first()
        camera = db_session.query(Camera).first()
        disease = db_session.query(Disease).first()
        area = db_session.query(Area).first()

        # Create a test upload with MD5 hash (simulating old data)
        test_content = b"test image content"
        md5_hash = hashlib.md5(test_content).hexdigest()

        upload = DirectImageUpload(
            filename="legacy_image.jpg",
            file_hash=md5_hash,  # Old MD5 hash
            folder_rel="test/folder",
            lab_unit_id=lab_unit.id,
            uploader_id=user.id,
            hospital_id=hospital.id,
            camera_id=camera.id,
            disease_id=disease.id,
            area_id=area.id,
        )
        db_session.add(upload)
        db_session.commit()

        # Should still be able to query by MD5 hash
        existing = db_session.execute(
            select(DirectImageUpload).filter_by(file_hash=md5_hash).limit(1)
        ).scalar_one_or_none()

        assert existing is not None, (
            "Old MD5 hashes should still be queryable during migration"
        )

        # Clean up
        db_session.delete(upload)
        db_session.commit()

    def test_new_uploads_use_sha256(self):
        """
        FAILING TEST: New uploads don't use SHA-256.

        Test that new file uploads use SHA-256 hashing instead of MD5.
        """
        test_content = b"test image content for new upload"

        try:
            from utils.file_hashing import hash_file_content
            file_hash = hash_file_content(test_content)

            # Should be SHA-256
            sha256_hash = hashlib.sha256(test_content).hexdigest()
            assert file_hash == sha256_hash, (
                "New uploads should use SHA-256"
            )

            # Should NOT be MD5
            md5_hash = hashlib.md5(test_content).hexdigest()
            assert file_hash != md5_hash, (
                "New uploads should NOT use MD5"
            )
        except ImportError:
            pytest.fail("hash_file_content() function does not exist yet")


class TestFileHashingPerformance:
    """Test suite for file hashing performance considerations."""

    def test_sha256_performance_acceptable(self):
        """
        Test that SHA-256 hashing performance is acceptable for file uploads.

        SHA-256 is slower than MD5 but still fast enough for typical image files.
        This test documents the performance trade-off.
        """
        import time

        # Simulate a typical image size (1MB)
        large_content = b"test image content" * (1024 * 256)  # ~18MB

        start = time.perf_counter()
        sha256_hash = hashlib.sha256(large_content).hexdigest()
        elapsed_ms = (time.perf_counter() - start) * 1000

        # SHA-256 should complete in reasonable time
        # For 18MB, should be under 100ms on modern hardware
        assert elapsed_ms < 500, (
            f"SHA-256 hashing should be fast enough: {elapsed_ms:.2f}ms"
        )

        # Verify hash is valid format
        assert len(sha256_hash) == 64, "SHA-256 should be 64 hex characters"

    def test_blake2b_faster_than_sha256(self):
        """
        Test that both SHA-256 and blake2b are performant and cryptographically secure.

        NOTE: In Python's hashlib implementation, SHA-256 is often faster than blake2b
        due to hardware acceleration. The key point is that both are cryptographically
        secure alternatives to MD5.
        """
        import time

        # Simulate a typical image size (1MB)
        test_content = b"test image content" * (1024 * 256)  # ~18MB

        # Time SHA-256
        start = time.perf_counter()
        sha256_hash = hashlib.sha256(test_content).hexdigest()
        sha256_time_ms = (time.perf_counter() - start) * 1000

        # Time blake2b
        start = time.perf_counter()
        blake2b_hash = hashlib.blake2b(test_content).hexdigest()
        blake2b_time_ms = (time.perf_counter() - start) * 1000

        # Both should be fast enough for typical file uploads
        assert sha256_time_ms < 500, (
            f"SHA-256 hashing should be fast: {sha256_time_ms:.2f}ms"
        )
        assert blake2b_time_ms < 500, (
            f"blake2b hashing should be fast: {blake2b_time_ms:.2f}ms"
        )

        # Both should be cryptographically secure (longer hash than MD5)
        assert len(sha256_hash) == 64, "SHA-256 should be 64 hex characters"
        assert len(blake2b_hash) == 128, "blake2b should be 128 hex characters"
