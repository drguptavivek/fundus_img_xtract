"""
Test user fixtures verification.

Verifies that the new test user fixtures work correctly.
"""

import pytest


@pytest.mark.unit
class TestUserFixtures:
    """Verify test user fixtures work correctly"""
    
    def test_core_test_data_fixture(self, core_test_data):
        """Verify core test data is created"""
        assert 'hospital' in core_test_data
        assert 'lab_unit' in core_test_data
        assert 'glaucoma' in core_test_data
        assert 'dr' in core_test_data
        
        assert core_test_data['hospital'].name == 'Hospital A'
        assert core_test_data['glaucoma'].name == 'Glaucoma'
    
    def test_admin_user_fixture(self, admin_user):
        """Verify admin user fixture works"""
        assert admin_user is not None
        assert admin_user.username == 'test_admin'
        assert admin_user.has_role('admin')
        assert admin_user.is_active is True
    
    def test_ophthalmologist_user_fixture(self, ophthalmologist_user, core_test_data):
        """Verify ophthalmologist user fixture works"""
        assert ophthalmologist_user is not None
        assert ophthalmologist_user.has_role('ophthalmologist')
        assert len(ophthalmologist_user.lab_units) > 0
        assert ophthalmologist_user.lab_units[0].id == core_test_data['lab_unit'].id
    
    def test_resident_user_fixture(self, resident_user, db_session, core_test_data):
        """Verify resident user fixture works"""
        from models import UserDiseaseUnitRole
        
        assert resident_user is not None
        assert resident_user.has_role('resident')
        
        # Check permissions
        permission = db_session.query(UserDiseaseUnitRole).filter_by(
            user_id=resident_user.id,
            disease_id=core_test_data['glaucoma'].id
        ).first()
        
        assert permission is not None
        assert permission.can_grade_resident is True
    
    def test_arbitrator_user_fixture(self, arbitrator_user, db_session, core_test_data):
        """Verify arbitrator user fixture works"""
        from models import UserDiseaseUnitRole
        
        assert arbitrator_user is not None
        assert arbitrator_user.username == 'test_arbitrator'
        
        # Check arbitration permission
        permission = db_session.query(UserDiseaseUnitRole).filter_by(
            user_id=arbitrator_user.id,
            disease_id=core_test_data['glaucoma'].id
        ).first()
        
        assert permission is not None
        assert permission.can_arbitrate is True
    
    def test_test_users_fixture(self, test_users):
        """Verify test_users dict fixture works"""
        assert 'admin' in test_users
        assert 'ophthalmologist' in test_users
        assert 'resident' in test_users
        assert 'arbitrator' in test_users
        
        assert test_users['admin'].has_role('admin')
        assert test_users['resident'].has_role('resident')
    
    def test_authenticated_client_fixture(self, authenticated_client, admin_user):
        """Verify authenticated client fixture works"""
        # The client should have a session with user_id set
        with authenticated_client.session_transaction() as sess:
            assert 'user_id' in sess
            assert sess['user_id'] == admin_user.id


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
