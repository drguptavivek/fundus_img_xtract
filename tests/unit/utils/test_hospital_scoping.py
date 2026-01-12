"""
Test hospital scoping utilities (TDD approach).

These tests verify the hospital scoping utility functions work correctly
for both hospital-bound and cross-hospital operations.
"""
import pytest
from models import DirectImageUpload, GradingTask
from utils.hospital_scoping import (
    is_cross_hospital_operation,
    get_user_lab_units_in_hospital,
    validate_lab_unit_hospital_match,
    apply_scoping,
    CROSS_HOSPITAL_OPERATIONS,
)


@pytest.mark.unit
class TestCrossHospitalOperationCheck:
    """Test is_cross_hospital_operation() function."""
    
    def test_grading_is_cross_hospital(self):
        """Grading operations should be cross-hospital."""
        assert is_cross_hospital_operation('grading') is True
    
    def test_arbitration_is_cross_hospital(self):
        """Arbitration operations should be cross-hospital."""
        assert is_cross_hospital_operation('arbitration') is True
    
    def test_dataset_creation_is_hospital_bound(self):
        """Dataset creation should be hospital-bound (unless role override)."""
        assert is_cross_hospital_operation('dataset_creation') is False
    
    def test_upload_is_hospital_bound(self):
        """Upload operations should be hospital-bound."""
        assert is_cross_hospital_operation('upload') is False
    
    def test_analytics_is_hospital_bound(self):
        """Analytics operations should be hospital-bound."""
        assert is_cross_hospital_operation('analytics') is False
    
    def test_cross_hospital_operations_constant_has_expected_values(self):
        """CROSS_HOSPITAL_OPERATIONS constant should contain expected values."""
        assert 'grading' in CROSS_HOSPITAL_OPERATIONS
        assert 'arbitration' in CROSS_HOSPITAL_OPERATIONS
        assert 'dataset_creation' not in CROSS_HOSPITAL_OPERATIONS
        assert 'upload' not in CROSS_HOSPITAL_OPERATIONS


@pytest.mark.unit
class TestGetUserLabUnitsInHospital:
    """Test get_user_lab_units_in_hospital() function."""
    
    def test_master_admin_gets_all_lab_units_in_hospital(
        self, db_session, master_admin, test_lab_units
    ):
        """Master admin should get all lab units in specified hospital."""
        user = db_session.merge(master_admin)
        # Get Hospital A lab units
        lab_ids = get_user_lab_units_in_hospital(user.id, hospital_id=1, db=db_session)
        
        assert 1 in lab_ids  # lab_a1
        assert 2 in lab_ids  # lab_a2
        assert 3 in lab_ids  # lab_a3
        assert 4 not in lab_ids  # lab_b1 (different hospital)
   
    def test_master_admin_gets_all_lab_units_without_hospital_filter(
        self, db_session, master_admin, test_lab_units
    ):
        """Master admin without hospital filter should get ALL lab units."""
        user = db_session.merge(master_admin)
        lab_ids = get_user_lab_units_in_hospital(user.id, db=db_session)
        
        # Should include both hospitals
        assert len(lab_ids) >= 6
        assert 1 in lab_ids  # Hospital A
        assert 4 in lab_ids  # Hospital B
    
    def test_regular_user_gets_only_own_hospital_lab_units(
        self, db_session, ophthalmologist_hospital_a, test_lab_units
    ):
        """Regular user should only get lab units from their hospital."""
        user = db_session.merge(ophthalmologist_hospital_a)
        lab_ids = get_user_lab_units_in_hospital(user.id, db=db_session)
        
        # Should only have Hospital A lab units (user's hospital)
        assert 1 in lab_ids  # lab_a1 (assigned)
        assert 4 not in lab_ids  # lab_b1 (different hospital)
    
    def test_user_with_no_hospital_gets_empty_set(self, db_session):
        """User with no hospital assignment should get empty set."""
        from models import User, Role
        from auth.security import hash_password
        
        role = db_session.query(Role).filter_by(name='ophthalmologist').first()
        if not role:
            role = Role(name='ophthalmologist')
            db_session.add(role)
            db_session.flush()
        
        user = User(
            username='no_hospital_user',
            password_hash=hash_password('Test@2026'),
            hospital_id=None,
            is_master_admin=False,
            roles=[role]
        )
        db_session.add(user)
        db_session.flush()
        db_session.refresh(user)  # Refresh to ensure it's attached to session
        
        lab_ids = get_user_lab_units_in_hospital(user.id, db=db_session)
        assert len(lab_ids) == 0


@pytest.mark.unit
class TestValidateLabUnitHospitalMatch:
    """Test validate_lab_unit_hospital_match() function."""
    
    def test_lab_unit_from_same_hospital_is_valid(
        self, db_session, ophthalmologist_hospital_a, core_test_data
    ):
        """Lab unit from same hospital should be valid."""
        user = db_session.merge(ophthalmologist_hospital_a)
        # ophth_a is in Hospital A (id=1), lab_a2 is also in Hospital A
        is_valid = validate_lab_unit_hospital_match(
            user.id,
            core_test_data['lab_a2'].id,  # Hospital A lab
            db=db_session
        )
        
        assert is_valid is True
    
    def test_lab_unit_from_different_hospital_is_invalid(
        self, db_session, ophthalmologist_hospital_a, core_test_data
    ):
        """Lab unit from different hospital should be invalid."""
        user = db_session.merge(ophthalmologist_hospital_a)
        # ophth_a is in Hospital A (id=1), lab_b1 is in Hospital B (id=2)
        is_valid = validate_lab_unit_hospital_match(
            user.id,
            core_test_data['lab_b1'].id,  # Hospital B lab
            db=db_session
        )
        
        assert is_valid is False
    
    def test_master_admin_can_access_any_lab_unit(
        self, db_session, master_admin, core_test_data
    ):
        """Master admin should be able to access any lab unit."""
        user = db_session.merge(master_admin)
        # Master admin can access Hospital B lab unit
        is_valid = validate_lab_unit_hospital_match(
            user.id,
            core_test_data['lab_b1'].id,  # Hospital B lab
            db=db_session
        )
        
        assert is_valid is True
    
    def test_invalid_user_raises_error(self, db_session, core_test_data):
        """Invalid user ID should raise ValueError."""
        with pytest.raises(ValueError, match="User .* not found"):
            validate_lab_unit_hospital_match(99999, core_test_data['lab_a1'].id, db=db_session)
@pytest.mark.unit
class TestApplyScopingHospitalBound:
    """Test apply_scoping() for hospital-bound operations."""
    
    def test_apply_scoping_filters_by_hospital_for_upload(
        self, db_session, ophthalmologist_hospital_a, core_test_data
    ):
        """Upload operation should filter by hospital."""
        # Create test images in both hospitals
        from models import DirectImageUpload, User
        import uuid
        
        # Get uploader from Hospital A
        uploader = db_session.merge(ophthalmologist_hospital_a)
        
        img_a = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_a.jpg',
            filename='test_a.jpg',
            folder_rel='files/test',
            file_hash='abc123',
            uploader_id=uploader.id,
            hospital_id=1,
            lab_unit_id=1,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        img_b = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_b.jpg',
            filename='test_b.jpg',
            folder_rel='files/test',
            file_hash='def456',
            uploader_id=uploader.id,
            hospital_id=2,
            lab_unit_id=4,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        db_session.add_all([img_a, img_b])
        db_session.flush()
        
        # Apply scoping for upload (hospital-bound)
        query = db_session.query(DirectImageUpload)
        query = apply_scoping(query, DirectImageUpload, uploader, 'upload')
        
        images = query.all()
        hospital_ids = {img.hospital_id for img in images}
        
        # Should only see Hospital A images
        assert 1 in hospital_ids
        assert 2 not in hospital_ids
    
    def test_master_admin_sees_all_hospitals_for_upload(
        self, db_session, master_admin, core_test_data
    ):
        """Master admin should see all hospitals even for hospital-bound operations."""
        from models import DirectImageUpload
        import uuid
        
        user = db_session.merge(master_admin)
        
        img_a = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_a.jpg',
            filename='test_a.jpg',
            folder_rel='files/test',
            file_hash='abc123',
            uploader_id=user.id,
            hospital_id=1,
            lab_unit_id=1,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        img_b = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_b.jpg',
            filename='test_b.jpg',
            folder_rel='files/test',
            file_hash='def456',
            uploader_id=user.id,
            hospital_id=2,
            lab_unit_id=4,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        db_session.add_all([img_a, img_b])
        db_session.flush()
        
        query = db_session.query(DirectImageUpload)
        user = db_session.merge(master_admin)
        query = apply_scoping(query, DirectImageUpload, user, 'upload')
        
        images = query.all()
        hospital_ids = {img.hospital_id for img in images}
        
        # Master admin sees both hospitals
        assert 1 in hospital_ids
        assert 2 in hospital_ids


@pytest.mark.unit
class TestApplyScopingCrossHospital:
    """Test apply_scoping() for cross-hospital operations."""
    
    def test_grading_operation_does_not_filter_by_hospital(
        self, db_session, ophthalmologist_hospital_a, core_test_data
    ):
        """Grading operations should NOT filter by hospital (cross-hospital)."""
        from models import DirectImageUpload
        import uuid
        
        uploader = db_session.merge(ophthalmologist_hospital_a)
        
        img_a = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_a.jpg',
            filename='test_a.jpg',
            folder_rel='files/test',
            file_hash='abc123',
            uploader_id=uploader.id,
            hospital_id=1,
            lab_unit_id=1,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        img_b = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_b.jpg',
            filename='test_b.jpg',
            folder_rel='files/test',
            file_hash='def456',
            uploader_id=uploader.id,
            hospital_id=2,
            lab_unit_id=4,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        db_session.add_all([img_a, img_b])
        db_session.flush()
        
        # Apply scoping for grading (cross-hospital)
        query = db_session.query(DirectImageUpload)
        query = apply_scoping(query, DirectImageUpload, uploader, 'grading')
        
        images = query.all()
        hospital_ids = {img.hospital_id for img in images}
        
        # Should see BOTH hospitals for grading (no hospital filter)
        assert 1 in hospital_ids
        assert 2 in hospital_ids
    
    def test_dataset_creation_is_cross_hospital(
        self, db_session, dataset_creator, core_test_data
    ):
        """Dataset creation should be cross-hospital."""
        from models import DirectImageUpload
        import uuid

        user = db_session.merge(dataset_creator)
        
        img_a = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_a.jpg',
            filename='test_a.jpg',
            folder_rel='files/test',
            file_hash='abc123',

            uploader_id=user.id,
            hospital_id=1,
            lab_unit_id=1,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        img_b = DirectImageUpload(
            uuid=str(uuid.uuid4()),
            original_filename='test_b.jpg',
            filename='test_b.jpg',
            folder_rel='files/test',
            file_hash='def456',

            uploader_id=user.id,
            hospital_id=2,
            lab_unit_id=4,
            camera_id=core_test_data['camera'].id,
            disease_id=core_test_data['glaucoma'].id,
            area_id=core_test_data['area'].id
        )
        db_session.add_all([img_a, img_b])
        db_session.flush()
        
        # Apply scoping for dataset creation (cross-hospital)
        query = db_session.query(DirectImageUpload)
        query = apply_scoping(query, DirectImageUpload, user, 'dataset_creation')
        
        images = query.all()
        hospital_ids = {img.hospital_id for img in images}
        
        # Dataset creator can access both hospitals
        assert 1 in hospital_ids
        assert 2 in hospital_ids
