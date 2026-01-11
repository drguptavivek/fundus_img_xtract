"""
Test security fixtures for hospital isolation.

Following TDD approach: These tests verify the security fixtures work correctly.
"""
import pytest
from models import User, Hospital, LabUnit, UserDiseaseUnitRole


@pytest.mark.unit
class TestHospitalFixtures:
    """Test multi-hospital fixtures."""
    
    def test_test_hospitals_creates_two_hospitals(self, test_hospitals):
        """Test hospitals fixture creates Hospital A and B."""
        assert 'hospital_a' in test_hospitals
        assert 'hospital_b' in test_hospitals
        
        assert test_hospitals['hospital_a'].id == 1
        assert test_hospitals['hospital_a'].name == 'Hospital A'
        
        assert test_hospitals['hospital_b'].id == 2
        assert test_hospitals['hospital_b'].name == 'Hospital B'
    
    def test_test_lab_units_creates_six_units(self, test_lab_units):
        """Test lab units fixture creates 6 lab units (3 per hospital)."""
        assert len(test_lab_units['hospital_a']) == 3
        assert len(test_lab_units['hospital_b']) == 3
        
        # Hospital A labs
        assert test_lab_units['lab_a1'].hospital_id == 1
        assert test_lab_units['lab_a2'].hospital_id == 1
        assert test_lab_units['lab_a3'].hospital_id == 1
        
        # Hospital B labs
        assert test_lab_units['lab_b1'].hospital_id == 2
        assert test_lab_units['lab_b2'].hospital_id == 2
        assert test_lab_units['lab_b3'].hospital_id == 2


@pytest.mark.unit
class TestUserSecurityFixtures:
    """Test hospital-scoped user fixtures."""
    
    def test_master_admin_has_correct_attributes(self, db_session, master_admin):
        """Master admin should have is_master_admin=True and hospital_id=None."""
        assert master_admin.username == 'master_admin'
        assert master_admin.is_master_admin is True
        assert master_admin.hospital_id is None
        assert len(master_admin.roles) > 0
        assert master_admin.roles[0].name == 'admin'
    
    def test_site_admin_hospital_a_scoped_to_hospital_1(self, db_session, site_admin_hospital_a):
        """Site admin A should be scoped to Hospital A."""
        assert site_admin_hospital_a.username == 'site_admin_a'
        assert site_admin_hospital_a.hospital_id == 1
        assert site_admin_hospital_a.is_master_admin is False
        assert site_admin_hospital_a.roles[0].name == 'local_admin'
    
    def test_site_admin_hospital_b_scoped_to_hospital_2(self, db_session, site_admin_hospital_b):
        """Site admin B should be scoped to Hospital B."""
        assert site_admin_hospital_b.username == 'site_admin_b'
        assert site_admin_hospital_b.hospital_id == 2
        assert site_admin_hospital_b.is_master_admin is False
    
    def test_ophthalmologist_hospital_a_has_hospital_and_lab_units(
        self, db_session, ophthalmologist_hospital_a
    ):
        """Ophthalmologist A should belong to Hospital A with lab units."""
        assert ophthalmologist_hospital_a.hospital_id == 1
        assert ophthalmologist_hospital_a.is_master_admin is False
        assert len(ophthalmologist_hospital_a.lab_units) == 1
        assert ophthalmologist_hospital_a.lab_units[0].hospital_id == 1
    
    def test_ophthalmologist_hospital_a_has_grading_permissions(
        self, db_session, ophthalmologist_hospital_a
    ):
        """Ophthalmologist A should have ABAC grading permissions."""
        # Check UserDiseaseUnitRole exists
        permissions = db_session.query(UserDiseaseUnitRole).filter_by(
            user_id=ophthalmologist_hospital_a.id
        ).all()
        
        assert len(permissions) == 1
        assert permissions[0].can_grade_resident is True
        assert permissions[0].can_grade_resident2 is True
        assert permissions[0].can_arbitrate is False
        assert permissions[0].lab_unit_id == 1  # Hospital A lab
    
    def test_ophthalmologist_cross_hospital_has_permissions_in_both_hospitals(
        self, db_session, ophthalmologist_cross_hospital
    ):
        """Cross-hospital ophthalmologist should have grading permissions in both hospitals."""
        permissions = db_session.query(UserDiseaseUnitRole).filter_by(
            user_id=ophthalmologist_cross_hospital.id
        ).all()
        
        # Should have 2 permissions (Hospital A and Hospital B)
        assert len(permissions) == 2
        
        lab_unit_ids = [p.lab_unit_id for p in permissions]
        assert 1 in lab_unit_ids  # Hospital A lab
        assert 4 in lab_unit_ids  # Hospital B lab
        
        # Both should allow grading
        assert all(p.can_grade_resident for p in permissions)
        assert all(p.can_grade_resident2 for p in permissions)
    
    def test_cross_hospital_grader_belongs_to_single_hospital(
        self, db_session, ophthalmologist_cross_hospital
    ):
        """Cross-hospital grader belongs to one hospital but can grade in others."""
        # Belongs to Hospital A
        assert ophthalmologist_cross_hospital.hospital_id == 1
        
        # Only Hospital A lab units for uploads
        assert len(ophthalmologist_cross_hospital.lab_units) == 1
        assert ophthalmologist_cross_hospital.lab_units[0].hospital_id == 1
        
        # But has grading permissions in Hospital B (via UserDiseaseUnitRole)
        permissions = db_session.query(UserDiseaseUnitRole).filter_by(
            user_id=ophthalmologist_cross_hospital.id
        ).all()
        
        # Has permission for lab_unit_id=4 (Hospital B)
        hospital_b_perm = [p for p in permissions if p.lab_unit_id == 4]
        assert len(hospital_b_perm) == 1
    
    def test_optometrist_hospital_a_has_all_hospital_a_labs(
        self, db_session, optometrist_hospital_a
    ):
        """Optometrist A should have access to all Hospital A lab units."""
        assert optometrist_hospital_a.hospital_id == 1
        assert len(optometrist_hospital_a.lab_units) == 3
        
        # All labs should be from Hospital A
        for lab_unit in optometrist_hospital_a.lab_units:
            assert lab_unit.hospital_id == 1
    
    def test_dataset_creator_belongs_to_hospital(self, db_session, dataset_creator):
        """Dataset creator belongs to a hospital but can access all (cross-hospital)."""
        assert dataset_creator.hospital_id == 1
        assert dataset_creator.is_master_admin is False
        assert dataset_creator.roles[0].name == 'dataset_creator'


@pytest.mark.unit
class TestFixtureIsolation:
    """Test that fixtures don't interfere with each other."""
    
    def test_multiple_users_can_coexist(
        self, db_session, master_admin, site_admin_hospital_a, ophthalmologist_hospital_a
    ):
        """Multiple user fixtures should coexist without conflicts."""
        users = db_session.query(User).all()
        
        usernames = [u.username for u in users]
        assert 'master_admin' in usernames
        assert 'site_admin_a' in usernames
        assert 'ophth_a' in usernames
    
    def test_fixtures_use_correct_hospitals(
        self, db_session, test_hospitals, site_admin_hospital_a, site_admin_hospital_b
    ):
        """Site admins should belong to different hospitals."""
        assert site_admin_hospital_a.hospital_id != site_admin_hospital_b.hospital_id
        assert site_admin_hospital_a.hospital_id == test_hospitals['hospital_a'].id
        assert site_admin_hospital_b.hospital_id == test_hospitals['hospital_b'].id
