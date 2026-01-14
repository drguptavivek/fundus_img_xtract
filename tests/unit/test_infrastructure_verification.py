"""
Infrastructure Verification Test

This test verifies that the new test infrastructure is working properly.

Run with: pytest tests/unit/test_infrastructure_verification.py -v
"""

import pytest
from tests.helpers.factories import UserFactory, CoreEntityFactory
from tests.helpers.mocks import mock_rate_limiter, create_mock_user, create_mock_role
from tests.helpers.assertions import (
    assert_has_keys, 
    assert_user_has_role
)


@pytest.mark.unit
@pytest.mark.fast
class TestInfrastructureVerification:
    """Verify test infrastructure is working"""
    
    def test_pytest_marks_work(self):
        """Verify pytest markers are registered"""
        # This test existing proves markers work
        assert True
    
    def test_factories_import(self):
        """Verify factories module imports correctly"""
        assert UserFactory is not None
        assert CoreEntityFactory is not None
    
    def test_mocks_import(self):
        """Verify mocks module imports correctly"""
        assert create_mock_user is not None
        assert create_mock_role is not None
    
    def test_assertions_import(self):
        """Verify assertions module imports correctly"""
        assert assert_has_keys is not None
        assert assert_user_has_role is not None
    
    def test_mock_user_creation(self):
        """Verify mock user helper works"""
        role = create_mock_role('admin')
        user = create_mock_user(roles=[role])
        
        assert user.id == 1
        assert user.username == 'testuser'
        assert user.has_role('admin')
    
    def test_assert_has_keys_success(self):
        """Verify assert_has_keys works for valid data"""
        data = {'name': 'test', 'value': 123}
        assert_has_keys(data, ['name', 'value'])
        # If no exception, test passes
        assert True
    
    def test_assert_has_keys_failure(self):
        """Verify assert_has_keys raises for missing keys"""
        data = {'name': 'test'}
        
        with pytest.raises(AssertionError) as exc_info:
            assert_has_keys(data, ['name', 'missing_key'])
        
        assert 'Missing required keys' in str(exc_info.value)
    
    def test_mock_rate_limiter_fixture(self, mock_rate_limiter):
        """Verify mock_rate_limiter fixture works"""
        # The fixture should mock the limiter
        assert mock_rate_limiter is not None
        assert mock_rate_limiter.limit is not None


@pytest.mark.integration
class TestFactoriesWithDatabase:
    """Verify factories work with database (integration test)"""
    
    def test_user_factory_with_db(self, db_session):
        """Verify UserFactory can create users in database"""
        # This will use the db_session fixture from conftest
        user = UserFactory.create_admin(db_session)
        
        assert user is not None
        assert user.username == 'test_admin'
        assert user.is_active is True
    
    def test_core_entity_factory(self, db_session):
        """Verify CoreEntityFactory can create entities"""
        entities = CoreEntityFactory.setup_core_entities(db_session)
        
        assert 'hospital' in entities
        assert 'lab_unit' in entities
        assert 'glaucoma' in entities
        assert 'dr' in entities
        
        assert entities['hospital'].name == 'Hospital A'
        assert entities['glaucoma'].name == 'Glaucoma'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
