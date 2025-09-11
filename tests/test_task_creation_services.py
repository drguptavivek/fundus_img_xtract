import pytest
import uuid
from sqlalchemy import select
from models import (
    Session, DirectImageUpload, DirectImageVerify, EncounterFile, 
    PatientEncounters, Disease, GradingTask, LabUnit, Hospital, Camera, Area
)
from services.taskCreationServices import (
    _resolve_image_by_uuid, _is_verified_for_disease, 
    create_or_get_task, ensure_task, can_unverify_image, remove_pending_tasks
)


class TestTaskCreationServices:
    """Test suite for task creation services."""

    def test_resolve_image_by_uuid_direct_image(self, setup_test_data):
        """Test resolving a direct image by UUID."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        
        kind, image_id, lab_unit_id = _resolve_image_by_uuid(db, direct_image.uuid)
        
        assert kind == 'direct'
        assert image_id == direct_image.id
        assert lab_unit_id == direct_image.lab_unit_id

    def test_resolve_image_by_uuid_encounter_file(self, setup_test_data):
        """Test resolving an encounter file by UUID."""
        db, test_data = setup_test_data
        encounter_file = test_data['encounter_file']
        
        kind, image_id, lab_unit_id = _resolve_image_by_uuid(db, encounter_file.uuid)
        
        assert kind == 'encounter'
        assert image_id == encounter_file.id
        assert lab_unit_id == encounter_file.lab_unit_id

    def test_resolve_image_by_uuid_not_found(self, setup_test_data):
        """Test resolving a non-existent image by UUID."""
        db, _ = setup_test_data
        fake_uuid = str(uuid.uuid4())
        
        with pytest.raises(ValueError, match="Image not found"):
            _resolve_image_by_uuid(db, fake_uuid)

    def test_is_verified_for_disease_direct_verified(self, setup_test_data):
        """Test verification check for a verified direct image."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        # Create verification record
        verification = DirectImageVerify(
            image_upload_id=direct_image.id,
            verified_status='verified',
            remarks='Test verification'
        )
        db.add(verification)
        db.commit()
        
        is_verified = _is_verified_for_disease(db, 'direct', direct_image.id, disease.id)
        assert is_verified is True

    def test_is_verified_for_disease_direct_not_verified(self, setup_test_data):
        """Test verification check for a non-verified direct image."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        is_verified = _is_verified_for_disease(db, 'direct', direct_image.id, disease.id)
        assert is_verified is False

    def test_is_verified_for_disease_dr_verified(self, setup_test_data):
        """Test verification check for a DR-verified encounter."""
        db, test_data = setup_test_data
        encounter = test_data['encounter']
        dr_disease = test_data['dr_disease']
        
        # Update encounter to be DR verified
        encounter.dr_verified_status = 'verified'
        db.add(encounter)
        db.commit()
        
        is_verified = _is_verified_for_disease(db, 'encounter', encounter.encounter_files[0].id, dr_disease.id)
        assert is_verified is True

    def test_is_verified_for_disease_glaucoma_verified(self, setup_test_data):
        """Test verification check for a Glaucoma-verified encounter."""
        db, test_data = setup_test_data
        encounter = test_data['encounter']
        glaucoma_disease = test_data['glaucoma_disease']
        
        # Update encounter to be Glaucoma verified
        encounter.glaucoma_verified_status = 'verified'
        db.add(encounter)
        db.commit()
        
        is_verified = _is_verified_for_disease(db, 'encounter', encounter.encounter_files[0].id, glaucoma_disease.id)
        assert is_verified is True

    def test_create_or_get_task_direct_image(self, setup_test_data):
        """Test creating a grading task for a direct image."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        task = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        assert task.direct_image_upload_id == direct_image.id
        assert task.disease_id == disease.id
        assert task.lab_unit_id == direct_image.lab_unit_id
        assert task.state == 'pending'

    def test_create_or_get_task_encounter_file(self, setup_test_data):
        """Test creating a grading task for an encounter file."""
        db, test_data = setup_test_data
        encounter_file = test_data['encounter_file']
        disease = test_data['disease']
        
        task = create_or_get_task(
            db, 
            kind='encounter', 
            image_id=encounter_file.id, 
            disease_id=disease.id, 
            lab_unit_id=encounter_file.lab_unit_id
        )
        
        assert task.encounter_file_id == encounter_file.id
        assert task.disease_id == disease.id
        assert task.lab_unit_id == encounter_file.lab_unit_id
        assert task.state == 'pending'

    def test_create_or_get_task_idempotent(self, setup_test_data):
        """Test that create_or_get_task is idempotent."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        # Create task first time
        task1 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Create task second time (should return the same)
        task2 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        assert task1.id == task2.id

    def test_ensure_task_direct_image(self, setup_test_data):
        """Test ensuring a task for a direct image."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        # Create verification record first
        verification = DirectImageVerify(
            image_upload_id=direct_image.id,
            verified_status='verified',
            remarks='Test verification'
        )
        db.add(verification)
        db.commit()
        
        # Ensure task
        task = ensure_task(direct_image.uuid, disease.id)
        
        assert task.direct_image_upload_id == direct_image.id
        assert task.disease_id == disease.id
        assert task.lab_unit_id == direct_image.lab_unit_id
        assert task.state == 'pending'

    def test_ensure_task_not_verified(self, setup_test_data):
        """Test that ensuring a task for a non-verified image raises PermissionError."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        with pytest.raises(PermissionError, match="Image not verified for this disease"):
            ensure_task(direct_image.uuid, disease.id)

    def test_ensure_task_locked_image(self, setup_test_data):
        """Test that ensuring a task for a locked image raises PermissionError."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        # Create verification record
        verification = DirectImageVerify(
            image_upload_id=direct_image.id,
            verified_status='verified',
            remarks='Test verification'
        )
        db.add(verification)
        db.commit()
        
        # Add is_locked attribute to direct image (simulating the attribute)
        # In real implementation, this would be a column in the model
        direct_image.is_locked = True
        
        with pytest.raises(PermissionError, match="Image is locked"):
            ensure_task(direct_image.uuid, disease.id)

    def test_can_unverify_image_no_tasks(self, setup_test_data):
        """Test that an image with no tasks can be unverified."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        
        # Check if image can be unverified (should be True as there are no tasks)
        result = can_unverify_image(db, kind='direct', image_id=direct_image.id)
        assert result is True

    def test_can_unverify_image_pending_tasks(self, setup_test_data):
        """Test that an image with only pending tasks can be unverified."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        # Create a pending task
        task = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Verify task is pending
        assert task.state == 'pending'
        
        # Check if image can be unverified (should be True as task is pending)
        result = can_unverify_image(db, kind='direct', image_id=direct_image.id)
        assert result is True

    def test_can_unverify_image_non_pending_tasks(self, setup_test_data):
        """Test that an image with non-pending tasks cannot be unverified."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease = test_data['disease']
        
        # Create a task and change its state
        task = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Change task state to non-pending
        task.state = 'final'
        db.add(task)
        db.commit()
        
        # Check if image can be unverified (should be False as task is not pending)
        result = can_unverify_image(db, kind='direct', image_id=direct_image.id)
        assert result is False

    def test_remove_pending_tasks_multiple_diseases(self, setup_test_data):
        """Test removing pending tasks for an image with multiple diseases."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease1 = test_data['disease']
        disease2 = test_data['dr_disease']
        
        # Create tasks for multiple diseases
        task1 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease1.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        task2 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease2.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Verify tasks exist and are pending
        assert task1 is not None
        assert task2 is not None
        assert task1.state == 'pending'
        assert task2.state == 'pending'
        
        # Remove all pending tasks
        removed_count = remove_pending_tasks(db, kind='direct', image_id=direct_image.id)
        
        assert removed_count == 2
        
        # Verify tasks are removed
        remaining_tasks = db.execute(
            select(GradingTask).where(
                GradingTask.direct_image_upload_id == direct_image.id
            )
        ).scalars().all()
        
        assert len(remaining_tasks) == 0

    def test_remove_pending_tasks_mixed_states(self, setup_test_data):
        """Test removing pending tasks when some are non-pending."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease1 = test_data['disease']
        disease2 = test_data['dr_disease']
        
        # Create tasks for multiple diseases
        task1 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease1.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        task2 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease2.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Change one task to non-pending state
        task1.state = 'final'
        db.add(task1)
        db.commit()
        
        # Check that we cannot unverify the image
        can_unverify = can_unverify_image(db, kind='direct', image_id=direct_image.id)
        assert can_unverify is False
        
        # Remove pending tasks (should only remove task2)
        removed_count = remove_pending_tasks(db, kind='direct', image_id=direct_image.id)
        
        assert removed_count == 1
        
        # Verify only task1 remains
        remaining_tasks = db.execute(
            select(GradingTask).where(
                GradingTask.direct_image_upload_id == direct_image.id
            )
        ).scalars().all()
        
        assert len(remaining_tasks) == 1
        assert remaining_tasks[0].id == task1.id
        assert remaining_tasks[0].state == 'final'

    def test_can_unverify_image_mixed_states(self, setup_test_data):
        """Test that can_unverify_image returns False when tasks have mixed states."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease1 = test_data['disease']
        disease2 = test_data['dr_disease']
        
        # Create tasks for multiple diseases
        task1 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease1.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        task2 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease2.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Change one task to non-pending state
        task1.state = 'resident_done'
        db.add(task1)
        db.commit()
        
        # Check that we cannot unverify the image
        can_unverify = can_unverify_image(db, kind='direct', image_id=direct_image.id)
        assert can_unverify is False

    def test_can_unverify_image_all_pending(self, setup_test_data):
        """Test that can_unverify_image returns True when all tasks are pending."""
        db, test_data = setup_test_data
        direct_image = test_data['direct_image']
        disease1 = test_data['disease']
        disease2 = test_data['dr_disease']
        
        # Create tasks for multiple diseases, all pending
        task1 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease1.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        task2 = create_or_get_task(
            db, 
            kind='direct', 
            image_id=direct_image.id, 
            disease_id=disease2.id, 
            lab_unit_id=direct_image.lab_unit_id
        )
        
        # Verify both tasks are pending
        assert task1.state == 'pending'
        assert task2.state == 'pending'
        
        # Check that we can unverify the image
        can_unverify = can_unverify_image(db, kind='direct', image_id=direct_image.id)
        assert can_unverify is True