"""
Integration Tests for Thumbnail Generation Workflow

End-to-end tests for the complete thumbnail system including:
- Database integration with SQLAlchemy models
- Background job processing
- File creation and cleanup
- Flask route integration
- Automatic workflow triggering
"""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
import uuid
from PIL import Image
import time
from unittest.mock import patch, MagicMock

# Flask imports
from flask import Flask
from flask_login import login_user

# Model imports
from models import db, DirectImageUpload, EncounterFile, Job, JobItem, User
from db_transaction_manager import transaction_scope

# Thumbnail system imports
from utils.thumbnail_jobs import create_thumbnail_job, process_thumbnail_job
from utils.thumbnail_integration import (
    trigger_direct_upload_thumbnails,
    trigger_encounter_thumbnails,
    with_thumbnails
)
from utils.thumbnail_cleanup import (
    cleanup_direct_upload_thumbnails,
    cleanup_encounter_file_thumbnails
)
from utils.image_processing import generate_thumbnail
from utils.fileUtils import (
    get_thumbnail_path_for_direct_upload,
    get_thumbnail_path_for_encounter_file
)


class TestThumbnailIntegration:
    """Integration tests for thumbnail system."""

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
        """Create temporary directory for test files."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

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

    @pytest.fixture
    def sample_images(self, temp_dir):
        """Create sample images for testing."""
        images = {}

        # Create test image
        test_image = Image.new('RGB', (400, 300), color='blue')
        image_path = os.path.join(temp_dir, 'test_image.jpg')
        test_image.save(image_path, 'JPEG')

        images['test'] = {
            'path': image_path,
            'size': (400, 300),
            'format': 'JPEG'
        }

        # Create edited version
        edited_image = Image.new('RGB', (350, 250), color='red')
        edited_path = os.path.join(temp_dir, 'edited_image.jpg')
        edited_image.save(edited_path, 'JPEG')

        images['edited'] = {
            'path': edited_path,
            'size': (350, 250),
            'format': 'JPEG'
        }

        return images

    def test_complete_direct_upload_workflow(self, app, sample_images, temp_dir):
        """Test complete workflow for direct upload images."""
        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'direct_uploads')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Step 1: Create DirectImageUpload record
            direct_upload = DirectImageUpload(
                original_filename='test_image.jpg',
                file_uuid=str(uuid.uuid4()),
                upload_user_id=1,
                file_size=12345,
                mime_type='image/jpeg'
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()  # Get the ID
                upload_id = direct_upload.id

            # Step 2: Move image file to upload location
            source_path = sample_images['test']['path']
            target_dir = os.path.join(upload_dir, str(direct_upload.file_uuid)[:2])
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, str(direct_upload.file_uuid) + '.jpg')
            shutil.copy2(source_path, target_path)

            # Update record with file path
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                direct_upload.file_path = target_path
                db.flush()

            # Step 3: Trigger thumbnail generation
            result = trigger_direct_upload_thumbnails(direct_upload.id)
            assert result['success'] is True
            assert result['jobs_created'] >= 1

            # Step 4: Process thumbnail job
            with transaction_scope() as db:
                job = db.query(Job).filter(Job.job_type == 'thumbnail_generation').first()
                assert job is not None

                job_item = job.items[0]
                assert job_item.item_type == 'direct_upload_original'

                # Process the job
                process_result = process_thumbnail_job(job_item.id)
                assert process_result['success'] is True

            # Step 5: Verify thumbnail was created
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                assert direct_upload.thumbnail_filename is not None

                thumbnail_path = get_thumbnail_path_for_direct_upload(
                    direct_upload.file_uuid,
                    direct_upload.thumbnail_filename.split('.')[-1]
                )
                assert os.path.exists(thumbnail_path)

                # Verify thumbnail properties
                with Image.open(thumbnail_path) as thumb:
                    assert thumb.size == (180, 180)

    def test_complete_encounter_file_workflow(self, app, sample_images, temp_dir):
        """Test complete workflow for encounter files."""
        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'encounter_files')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Step 1: Create EncounterFile record
            encounter_file = EncounterFile(
                file_uuid=str(uuid.uuid4()),
                original_filename='encounter_image.jpg',
                file_size=12345,
                mime_type='image/jpeg',
                encounter_id=1
            )

            with transaction_scope() as db:
                db.add(encounter_file)
                db.flush()
                file_id = encounter_file.id

            # Step 2: Move image file to upload location
            source_path = sample_images['test']['path']
            target_dir = os.path.join(upload_dir, str(encounter_file.file_uuid)[:2])
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, str(encounter_file.file_uuid) + '.jpg')
            shutil.copy2(source_path, target_path)

            # Update record with file path
            with transaction_scope() as db:
                encounter_file = db.get(EncounterFile, file_id)
                encounter_file.file_path = target_path
                db.flush()

            # Step 3: Trigger thumbnail generation
            result = trigger_encounter_thumbnails(encounter_file.id)
            assert result['success'] is True
            assert result['jobs_created'] == 1

            # Step 4: Process thumbnail job
            with transaction_scope() as db:
                job = db.query(Job).filter(Job.job_type == 'thumbnail_generation').first()
                assert job is not None

                job_item = job.items[0]
                assert job_item.item_type == 'encounter_file'

                # Process the job
                process_result = process_thumbnail_job(job_item.id)
                assert process_result['success'] is True

            # Step 5: Verify thumbnail was created
            with transaction_scope() as db:
                encounter_file = db.get(EncounterFile, file_id)
                assert encounter_file.thumbnail_filename is not None

                thumbnail_path = get_thumbnail_path_for_encounter_file(
                    encounter_file.file_uuid,
                    encounter_file.thumbnail_filename.split('.')[-1]
                )
                assert os.path.exists(thumbnail_path)

                # Verify thumbnail properties
                with Image.open(thumbnail_path) as thumb:
                    assert thumb.size == (180, 180)

    def test_edited_image_workflow(self, app, sample_images, temp_dir):
        """Test workflow for edited direct upload images."""
        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'direct_uploads')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Step 1: Create DirectImageUpload with original and edited
            direct_upload = DirectImageUpload(
                original_filename='test_image.jpg',
                file_uuid=str(uuid.uuid4()),
                upload_user_id=1,
                file_size=12345,
                mime_type='image/jpeg',
                edited_filename='edited_image.jpg',
                edited_file_size=10000
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            # Step 2: Move both original and edited files
            source_orig = sample_images['test']['path']
            source_edit = sample_images['edited']['path']

            target_dir = os.path.join(upload_dir, str(direct_upload.file_uuid)[:2])
            os.makedirs(target_dir, exist_ok=True)

            orig_path = os.path.join(target_dir, str(direct_upload.file_uuid) + '.jpg')
            edit_path = os.path.join(target_dir, str(direct_upload.file_uuid) + '_edited.jpg')

            shutil.copy2(source_orig, orig_path)
            shutil.copy2(source_edit, edit_path)

            # Update record with file paths
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                direct_upload.file_path = orig_path
                direct_upload.edited_file_path = edit_path
                db.flush()

            # Step 3: Trigger thumbnail generation for both
            result = trigger_direct_upload_thumbnails(direct_upload.id)
            assert result['success'] is True
            assert result['jobs_created'] == 2  # Original + Edited

            # Step 4: Process both jobs
            with transaction_scope() as db:
                job = db.query(Job).filter(Job.job_type == 'thumbnail_generation').first()

                for job_item in job.items:
                    process_result = process_thumbnail_job(job_item.id)
                    assert process_result['success'] is True

            # Step 5: Verify both thumbnails were created
            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                assert direct_upload.thumbnail_filename is not None
                assert direct_upload.edited_thumbnail_filename is not None

                # Check original thumbnail
                orig_thumb_path = get_thumbnail_path_for_direct_upload(
                    direct_upload.file_uuid,
                    direct_upload.thumbnail_filename.split('.')[-1]
                )
                assert os.path.exists(orig_thumb_path)

                # Check edited thumbnail
                edit_thumb_path = get_thumbnail_path_for_direct_upload(
                    direct_upload.file_uuid,
                    direct_upload.edited_thumbnail_filename.split('.')[-1]
                )
                assert os.path.exists(edit_thumb_path)

    def test_with_thumbnails_decorator(self, app, sample_images, temp_dir):
        """Test the @with_thumbnails decorator functionality."""
        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'direct_uploads')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create test function with decorator
            @with_thumbnails()
            def process_upload(direct_upload_id):
                with transaction_scope() as db:
                    direct_upload = db.get(DirectImageUpload, direct_upload_id)
                    return {'processed': direct_upload_id, 'thumbnails': 'triggered'}

            # Step 1: Create DirectImageUpload record
            direct_upload = DirectImageUpload(
                original_filename='test_image.jpg',
                file_uuid=str(uuid.uuid4()),
                upload_user_id=1,
                file_size=12345,
                mime_type='image/jpeg'
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            # Step 2: Move file
            source_path = sample_images['test']['path']
            target_dir = os.path.join(upload_dir, str(direct_upload.file_uuid)[:2])
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, str(direct_upload.file_uuid) + '.jpg')
            shutil.copy2(source_path, target_path)

            with transaction_scope() as db:
                direct_upload = db.get(DirectImageUpload, upload_id)
                direct_upload.file_path = target_path
                db.flush()

            # Step 3: Call decorated function
            result = process_upload(upload_id)
            assert result['processed'] == upload_id
            assert result['thumbnails'] == 'triggered'

            # Step 4: Verify thumbnail job was created
            with transaction_scope() as db:
                job = db.query(Job).filter(Job.job_type == 'thumbnail_generation').first()
                assert job is not None

    def test_cleanup_workflow(self, app, sample_images, temp_dir):
        """Test the cleanup workflow for thumbnails."""
        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'direct_uploads')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Step 1: Create DirectImageUpload with thumbnails
            direct_upload = DirectImageUpload(
                original_filename='test_image.jpg',
                file_uuid=str(uuid.uuid4()),
                upload_user_id=1,
                file_size=12345,
                mime_type='image/jpeg',
                thumbnail_filename='thm_' + str(uuid.uuid4()) + '.jpg'
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            # Step 2: Create thumbnail file
            thumbnail_path = get_thumbnail_path_for_direct_upload(
                direct_upload.file_uuid,
                'jpg'
            )
            os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)

            # Generate actual thumbnail
            source_path = sample_images['test']['path']
            generate_thumbnail(source_path, thumbnail_path)
            assert os.path.exists(thumbnail_path)

            # Step 3: Test cleanup
            result = cleanup_direct_upload_thumbnails(direct_upload)
            assert result['success'] is True
            assert result['files_deleted'] >= 1
            assert not os.path.exists(thumbnail_path)

    def test_error_handling_workflow(self, app, temp_dir):
        """Test error handling in the thumbnail workflow."""
        with app.app_context():
            # Test with non-existent record
            result = trigger_direct_upload_thumbnails(999999)
            assert result['success'] is False
            assert 'not found' in result['message'].lower()

            # Test with missing file
            direct_upload = DirectImageUpload(
                original_filename='missing.jpg',
                file_uuid=str(uuid.uuid4()),
                upload_user_id=1,
                file_size=12345,
                mime_type='image/jpeg',
                file_path='/nonexistent/path.jpg'
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            result = trigger_direct_upload_thumbnails(upload_id)
            assert result['success'] is True  # Job created, but will fail during processing
            assert result['jobs_created'] == 1

    def test_job_retry_mechanism(self, app, sample_images, temp_dir):
        """Test job retry mechanism for failed thumbnail generation."""
        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'direct_uploads')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            # Create DirectImageUpload with invalid file path
            direct_upload = DirectImageUpload(
                original_filename='invalid.jpg',
                file_uuid=str(uuid.uuid4()),
                upload_user_id=1,
                file_size=12345,
                mime_type='image/jpeg',
                file_path='/nonexistent/invalid.jpg'
            )

            with transaction_scope() as db:
                db.add(direct_upload)
                db.flush()
                upload_id = direct_upload.id

            # Trigger thumbnail generation
            result = trigger_direct_upload_thumbnails(upload_id)
            assert result['success'] is True

            # Process the job (should fail)
            with transaction_scope() as db:
                job = db.query(Job).filter(Job.job_type == 'thumbnail_generation').first()
                job_item = job.items[0]

                process_result = process_thumbnail_job(job_item.id)
                assert process_result['success'] is False

                # Check if retry mechanism is working
                updated_job_item = db.get(JobItem, job_item.id)
                assert updated_job_item.status == 'failed'
                assert updated_job_item.retry_count > 0

    def test_concurrent_thumbnail_generation(self, app, sample_images, temp_dir):
        """Test concurrent thumbnail generation."""
        import threading
        import time

        with app.app_context():
            # Mock upload folder
            upload_dir = os.path.join(temp_dir, 'uploads', 'direct_uploads')
            os.makedirs(upload_dir, exist_ok=True)
            app.config['UPLOAD_FOLDER'] = temp_dir

            upload_ids = []
            results = []
            errors = []

            def create_and_process_upload(index):
                try:
                    # Create DirectImageUpload
                    direct_upload = DirectImageUpload(
                        original_filename=f'concurrent_{index}.jpg',
                        file_uuid=str(uuid.uuid4()),
                        upload_user_id=1,
                        file_size=12345,
                        mime_type='image/jpeg'
                    )

                    with transaction_scope() as db:
                        db.add(direct_upload)
                        db.flush()
                        upload_id = direct_upload.id
                        upload_ids.append(upload_id)

                        # Move file
                        target_dir = os.path.join(upload_dir, str(direct_upload.file_uuid)[:2])
                        os.makedirs(target_dir, exist_ok=True)
                        target_path = os.path.join(target_dir, str(direct_upload.file_uuid) + '.jpg')
                        shutil.copy2(sample_images['test']['path'], target_path)

                        direct_upload.file_path = target_path
                        db.flush()

                    # Trigger and process
                    trigger_result = trigger_direct_upload_thumbnails(upload_id)

                    with transaction_scope() as db:
                        job = db.query(Job).filter(Job.job_type == 'thumbnail_generation').filter_by(id=trigger_result['job_id']).first()
                        if job and job.items:
                            job_item = job.items[0]
                            process_result = process_thumbnail_job(job_item.id)
                            results.append((index, process_result['success']))

                except Exception as e:
                    errors.append((index, str(e)))

            # Create multiple threads
            threads = []
            for i in range(3):
                thread = threading.Thread(target=create_and_process_upload, args=(i,))
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # Verify results
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(results) == 3
            assert all(success for _, success in results)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])