"""
Common Mock Objects and Fixtures

Provides reusable mock objects for testing.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_rate_limiter():
    """Disable rate limiting for tests that don't need it"""
    with patch('utils.rate_limiter.limiter') as mock:
        # Make all decorators pass-through
        mock.limit.return_value = lambda f: f
        mock.exempt.return_value = lambda f: f
        mock.shared_limit.return_value = lambda f: f
        yield mock


@pytest.fixture
def mock_current_user():
    """Mock current_user for testing"""
    with patch('flask_login.current_user') as mock_user:
        mock_user.is_authenticated = False
        mock_user.id = None
        mock_user.username = None
        yield mock_user


@pytest.fixture
def mock_redis():
    """Mock Redis connection for tests"""
    with patch('redis.Redis') as mock:
        redis_instance = MagicMock()
        mock.return_value = redis_instance
        yield redis_instance


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = Mock()
    session.query.return_value = session
    session.filter.return_value = session
    session.filter_by.return_value = session
    session.first.return_value = None
    session.all.return_value = []
    session.add = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.close = Mock()
    return session


def create_mock_user(user_id=1, username='testuser', roles=None, is_active=True):
    """Create a mock user object"""
    user = Mock()
    user.id = user_id
    user.username = username
    user.is_active = is_active
    user.is_authenticated = True
    user.roles = roles or []
    
    def has_role(*role_names):
        return any(role in [r.name for r in user.roles] for role in role_names)
    
    def has_all_roles(*role_names):
        role_set = {r.name for r in user.roles}
        return all(role in role_set for role in role_names)
    
    user.has_role = Mock(side_effect=has_role)
    user.has_all_roles = Mock(side_effect=has_all_roles)
    
    return user


def create_mock_role(name='admin'):
    """Create a mock role object"""
    role = Mock()
    role.name = name
    return role
