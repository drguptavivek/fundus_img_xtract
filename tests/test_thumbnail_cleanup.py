"""
Cleanup Verification Tests for Thumbnail System

Tests focusing on cleanup functionality:
- Automatic thumbnail deletion when parent images are deleted
- Orphaned thumbnail detection and cleanup
- SQLAlchemy event handlers
- Cascade deletion behavior
- Error handling during cleanup
- Integrity after cleanup operations
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
import uuid
from unittest.mock import patch, MagicMock

# Flask imports
from flask import Flask

# Model imports
from models import (
    db, DirectImageUpload, EncounterFile, PatientEncounters, Patient,
    Job, JobItem, User
)
from db_transaction_manager import transaction_scope

# Thumbnail system imports
from utils.thumbnail_cleanup import (
    cleanup_direct_upload_thumbnails,
    cleanup_encounter_file_thumbnails,
    cleanup_patient_encounter_thumbnails,
    find_orphaned_thumbnails,
    validate_thumbnails_integrity
)
from utils.thumbnail_maintenance_scheduler import (
    cleanup_orphaned_thumbnails,
    regenerate_missing_thumbnails,
    validate_thumbnail_integrity
)
from utils.fileUtils import (
    get_thumbnail_path_for_direct_upload,
    get_thumbnail_path_for_encounter_file,
    thumbnail_exists
)
from utils.image_processing import generate_thumbnail


class TestThumbnailCleanup:
    """Tests for thumbnail cleanup functionality."""

    @pytest.fixture
    def app(self):
        """Create Flask app for testing."""
        app = Flask(__name__)
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
        app.config['SECRET_KEY'] = 'test-secret-key'

        db.init_app(app)

        with app.app_context():
            db.create_all()
            yield app
            db.drop_all()

        # Cleanup temp directory
        shutil.rmtree(app.config['UPLOAD_FOLDER'], ignore_errors=True)

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def sample_images(self, temp_dir):
        """Create sample images for testing."""
        images = {}

        # Create test images
        from PIL import Image

        test_configs = [
            ('original', (400, 300), 'blue'),
            ('edited', (350, 250), 'red'),
            ('encounter', (600, 400), 'green'),
        ]

        for name, size, color in test_configs:
            img = Image.new('RGB', size, color=color)
            path = os.path.join(temp_dir, f'{name}.jpg')
            img.save(path, 'JPEG')
            images[name] = path

        return images

    @pytest.fixture
    def sample_user(self, app):
        """Create a sample user for testing."""
        with app.app_context():
            user = User(
                username='testuser',
                email='test@example.com',
                full_name='Test User'
            )
            user.set_password('password')
            db.session.add(user)
            db.session.commit()
            return user

    def test_direct_upload_thumbnail_cleanup(self, app, sample_images, temp_dir):
        """Test thumbnail cleanup for DirectImageUpload records."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create DirectImageUpload with thumbnails
            direct_upload = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='test.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename='thm_test.jpg',
                edited_filename='edited.jpg',
                edited_file_size=10000,
                edited_thumbnail_filename='thm_test_edited.jpg'
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            # Create thumbnail files
            original_thumb_path = get_thumbnail_path_for_direct_upload(
                direct_upload.file_uuid, 'jpg'
            )
            edited_thumb_path = get_thumbnail_path_for_direct_upload(
                direct_upload.file_uuid, 'jpg'
            )

            os.makedirs(os.path.dirname(original_thumb_path), exist_ok=True)
            generate_thumbnail(sample_images['original'], original_thumb_path)
            generate_thumbnail(sample_images['edited'], edited_thumb_path)

            # Verify thumbnails exist
            assert os.path.exists(original_thumb_path)
            assert os.path.exists(edited_thumb_path)

            # Test cleanup
            result = cleanup_direct_upload_thumbnails(direct_upload)
            assert result['success'] is True
            assert result['files_deleted'] >= 2

            # Verify thumbnails are deleted
            assert not os.path.exists(original_thumb_path)
            assert not os.path.exists(edited_thumb_path)

            # Verify database record is updated
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                assert direct_upload.thumbnail_filename is None
                assert direct_upload.edited_thumbnail_filename is None

    def test_encounter_file_thumbnail_cleanup(self, app, sample_images, temp_dir):
        """Test thumbnail cleanup for EncounterFile records."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create EncounterFile with thumbnail
            encounter_file = EncounterFile(
                file_uuid=str(uuid.uuid4()),
                original_filename='encounter.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                encounter_id=1,
                thumbnail_filename='thm_encounter.jpg'
            )

            with transaction_scope() as db:
                db.add(encounter_file)
                db.flush()
                file_id = encounter_file.id

            # Create thumbnail file
            thumbnail_path = get_thumbnail_path_for_encounter_file(
                encounter_file.file_uuid, 'jpg'
            )
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
            generate_thumbnail(sample_images['encounter'], thumbnail_path)

            # Verify thumbnail exists
            assert os.path.exists(thumbnail_path)

            # Test cleanup
            result = cleanup_encounter_file_thumbnails(encounter_file)
            assert result['success'] is True
            assert result['files_deleted'] >= 1

            # Verify thumbnail is deleted
            assert not os.path.exists(thumbnail_path)

            # Verify database record is updated
            with transaction_scope() as db:
                encounter_file = db.get(EncounterFile, file_id)
                assert encounter_file.thumbnail_filename is None

    def test_patient_encounter_cascade_cleanup(self, app, sample_images, sample_user, temp_dir):
        """Test cascade cleanup when PatientEncounters are deleted."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create test data hierarchy
            patient = Patient(
                patient_id='TEST001',
                patient_name='Test Patient',
                age=30,
                gender='M',
                created_by_user_id=sample_user.id
            )

            with transaction_scope() as db:
                db.add(patient)
                db.flush()
                patient_id = patient.id

                # Create patient encounter
                encounter = PatientEncounters(
                    patient_id=patient_id,
                    encounter_date='2024-01-01',
                    created_by_user_id=sample_user.id
                )
                db.add(encounter)
                db.flush()
                encounter_id = encounter.id

                # Create multiple encounter files
                encounter_files = []
                for i in range(3):
                    encounter_file = EncounterFile(
                        file_uuid=str(uuid.uuid4()),
                        original_filename=f'encounter_{i}.jpg',
                        file_size=12345,
                        mime_type='image/jpeg',
                        encounter_id=encounter_id,
                        thumbnail_filename=f'thm_encounter_{i}.jpg'
                    )
                    db.add(encounter_file)
                    db.flush()
                    encounter_files.append(encounter_file)

                    # Create thumbnail files
                    thumbnail_path = get_thumbnail_path_for_encounter_file(
                        encounter_file.file_uuid, 'jpg'
                    )
                    os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                    generate_thumbnail(sample_images['encounter'], thumbnail_path)
                    assert os.path.exists(thumbnail_path)

            # Verify all thumbnails exist
            for encounter_file in encounter_files:
                thumb_path = get_thumbnail_path_for_encounter_file(
                    encounter_file.file_uuid, 'jpg'
                )
                assert os.path.exists(thumb_path)

            # Test cascade cleanup
            result = cleanup_patient_encounter_thumbnails(encounter_id)
            assert result['success'] is True
            assert result['files_deleted'] == len(encounter_files)

            # Verify all thumbnails are deleted
            for encounter_file in encounter_files:
                thumb_path = get_thumbnail_path_for_encounter_file(
                    encounter_file.file_uuid, 'jpg'
                )
                assert not os.path.exists(thumb_path)

    def test_orphaned_thumbnail_detection(self, app, sample_images, temp_dir):
        """Test detection and cleanup of orphaned thumbnails."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create some orphaned thumbnails
            orphaned_paths = []
            for i in range(3):
                file_uuid = str(uuid.uuid4())
                thumbnail_path = get_thumbnail_path_for_direct_upload(file_uuid, 'jpg')
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                generate_thumbnail(sample_images['original'], thumbnail_path)
                orphaned_paths.append(thumbnail_path)

            # Verify orphaned thumbnails exist
            for path in orphaned_paths:
                assert os.path.exists(path)

            # Test orphaned detection
            orphaned = find_orphaned_thumbnails()
            assert len(orphaned) >= len(orphaned_paths)

            # Test orphaned cleanup
            result = cleanup_orphaned_thumbnails(app, 'test')
            assert result['success'] is True
            assert result['orphaned_found'] >= len(orphaned_paths)
            assert result['orphaned_deleted'] >= len(orphaned_paths)

            # Verify orphaned thumbnails are deleted
            for path in orphaned_paths:
                assert not os.path.exists(path)

    def test_mixed_cleanup_scenarios(self, app, sample_images, sample_user, temp_dir):
        """Test cleanup with mixed scenarios (some thumbnails exist, some don't)."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create DirectImageUpload with mixed thumbnail presence
            direct_upload = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='mixed_test.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename='thm_exists.jpg',  # This exists
                edited_thumbnail_filename='thm_missing.jpg'  # This doesn't exist
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            # Create only the original thumbnail
            original_thumb_path = get_thumbnail_path_for_direct_upload(
                direct_upload.file_uuid, 'jpg'
            )
            os.makedirs(os.path.dirname(original_thumb_path), exist_ok=True)
            generate_thumbnail(sample_images['original'], original_thumb_path)

            # Verify only original exists
            assert os.path.exists(original_thumb_path)

            # Test cleanup (should handle missing files gracefully)
            result = cleanup_direct_upload_thumbnails(direct_upload)
            assert result['success'] is True
            assert result['files_deleted'] == 1  # Only existing file should be deleted

            # Verify database cleanup worked
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                assert direct_upload.thumbnail_filename is None
                assert direct_upload.edited_thumbnail_filename is None

    def test_cleanup_error_handling(self, app, temp_dir):
        """Test error handling during cleanup operations."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Test cleanup of non-existent file
            non_existent_upload = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='nonexistent.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename='thm_nonexistent.jpg'
            )

            # Should handle missing files gracefully
            result = cleanup_direct_upload_thumbnails(non_existent_upload)
            assert result['success'] is True  # Should succeed even if file doesn't exist
            assert result['files_deleted'] == 0

            # Test with invalid paths
            with patch('os.path.exists', side_effect=OSError("Permission denied")):
                result = cleanup_direct_upload_thumbnails(non_existent_upload)
                # Should handle OS errors gracefully
                assert isinstance(result, dict)
                assert 'success' in result

    def test_integrity_validation_after_cleanup(self, app, sample_images, temp_dir):
        """Test system integrity after cleanup operations."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create multiple DirectImageUpload records with thumbnails
            uploads = []
            for i in range(5):
                upload = DirectImageUpload(
                    file_uuid=str(uuid.uuid4()),
                    original_filename=f'integrity_test_{i}.jpg',
                    file_size=12345,
                    mime_type='image/jpeg',
                    upload_user_id=1,
                    thumbnail_filename=f'thm_integrity_{i}.jpg'
                )
                uploads.append(upload)

            with transaction_scope() as db:
                for upload in uploads:
                    db.add(upload)
                db.flush()
                upload_ids = [upload.id for upload in uploads]

            # Create thumbnail files
            for upload in uploads:
                thumbnail_path = get_thumbnail_path_for_direct_upload(
                    upload.file_uuid, 'jpg'
                )
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                generate_thumbnail(sample_images['original'], thumbnail_path)

            # Verify initial integrity
            initial_validation = validate_thumbnails_integrity()
            assert initial_validation['total_records'] == len(uploads)
            assert initial_validation['consistent_records'] == len(uploads)

            # Clean up some thumbnails
            cleanup_results = []
            for i, upload in enumerate(uploads[:3]):  # Clean up first 3
                result = cleanup_direct_upload_thumbnails(upload)
                cleanup_results.append(result)

            # Verify integrity after partial cleanup
            post_cleanup_validation = validate_thumbnails_integrity()
            assert post_cleanup_validation['total_records'] == len(uploads)
            # Records with null thumbnails should be consistent
            assert post_cleanup_validation['consistent_records'] == len(uploads)

            # Verify specific cleanup results
            for result in cleanup_results:
                assert result['success'] is True
                assert result['files_deleted'] == 1

    def test_regenerate_missing_thumbnails(self, app, sample_images, sample_user, temp_dir):
        """Test regeneration of missing thumbnails."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create DirectImageUpload with missing thumbnail
            direct_upload = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='regenerate_test.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename='thm_missing.jpg'  # Referenced but doesn't exist
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

                # Create source image
                source_dir = os.path.join(temp_dir, 'direct_uploads', direct_upload.file_uuid[:2])
                os.makedirs(source_dir, exist_ok=True)
                source_path = os.path.join(source_dir, f'{direct_upload.file_uuid}.jpg')
                shutil.copy2(sample_images['original'], source_path)
                direct_upload.file_path = source_path

            # Verify thumbnail doesn't exist
            thumbnail_path = get_thumbnail_path_for_direct_upload(
                direct_upload.file_uuid, 'jpg'
            )
            assert not os.path.exists(thumbnail_path)

            # Test regeneration
            result = regenerate_missing_thumbnails(app, 'test', limit=10)
            assert result['success'] is True
            assert result['thumbnails_generated'] >= 1

            # Verify thumbnail was created
            assert os.path.exists(thumbnail_path)

            # Verify database record is updated
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                assert direct_upload.thumbnail_filename is not None

    def test_integrity_validation_comprehensive(self, app, sample_images, temp_dir):
        """Test comprehensive integrity validation."""
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create test data with various integrity scenarios
            scenarios = []

            # Scenario 1: Record with existing thumbnail
            upload1 = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='scenario1.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename='thm_scenario1.jpg'
            )
            scenarios.append(('consistent', upload1))

            # Scenario 2: Record with missing thumbnail
            upload2 = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='scenario2.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename='thm_scenario2.jpg'
            )
            scenarios.append(('missing', upload2))

            # Scenario 3: Record with null thumbnail
            upload3 = DirectImageUpload(
                file_uuid=str(uuid.uuid4()),
                original_filename='scenario3.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                upload_user_id=1,
                thumbnail_filename=None
            )
            scenarios.append(('null', upload3))

            with transaction_scope() as db:
                for scenario_name, upload in scenarios:
                    db.add(upload)
                db.flush()

            # Create thumbnails for consistent scenarios
            consistent_thumb_path = get_thumbnail_path_for_direct_upload(
                scenarios[0][1].file_uuid, 'jpg'
            )
            os.makedirs(os.path.dirname(consistent_thumb_path), exist_ok=True)
            generate_thumbnail(sample_images['original'], consistent_thumb_path)

            # Test integrity validation
            validation_result = validate_thumbnail_integrity(app, 'test', sample_size=10)
            assert validation_result['success'] is True
            assert validation_result['total_checked'] == len(scenarios)
            assert 'consistent_count' in validation_result
            assert 'missing_count' in validation_result

            # Should find 1 consistent, 1 missing, 1 null (which is consistent)
            assert validation_result['consistent_count'] >= 1
            assert validation_result['missing_count'] >= 1

    def test_concurrent_cleanup_operations(self, app, sample_images, temp_dir):
        """Test concurrent cleanup operations."""
        import threading
        import time

        with app.app_context():
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create multiple uploads with thumbnails
            uploads = []
            for i in range(10):
                upload = DirectImageUpload(
                    file_uuid=str(uuid.uuid4()),
                    original_filename=f'concurrent_{i}.jpg',
                    file_size=12345,
                    mime_type='image/jpeg',
                    upload_user_id=1,
                    thumbnail_filename=f'thm_concurrent_{i}.jpg'
                )
                uploads.append(upload)

            with transaction_scope() as db:
                for upload in uploads:
                    db.add(upload)
                db.flush()
                upload_ids = [upload.id for upload in uploads]

            # Create thumbnail files
            for upload in uploads:
                thumbnail_path = get_thumbnail_path_for_direct_upload(
                    upload.file_uuid, 'jpg'
                )
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                generate_thumbnail(sample_images['original'], thumbnail_path)

            results = []
            errors = []

            def cleanup_upload(upload_id):
                try:
                    with transaction_scope() as db:
                        upload = db.get(DirectImageUpload, upload_id)
                        result = cleanup_direct_upload_thumbnails(upload)
                        results.append((upload_id, result))
                except Exception as e:
                    errors.append((upload_id, str(e)))

            # Run cleanup concurrently
            threads = []
            for upload_id in upload_ids:
                thread = threading.Thread(target=cleanup_upload, args=(upload_id,))
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # Verify results
            assert len(errors) == 0, f"Concurrent cleanup errors: {errors}"
            assert len(results) == len(upload_ids)

            successful = sum(1 for _, result in results if result.get('success', False))
            assert successful == len(upload_ids)

            # Verify all thumbnails were deleted
            for upload in uploads:
                thumbnail_path = get_thumbnail_path_for_direct_upload(
                    upload.file_uuid, 'jpg'
                )
                assert not os.path.exists(thumbnail_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])