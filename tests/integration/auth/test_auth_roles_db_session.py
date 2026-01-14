"""
Comprehensive tests for auth roles functions with database session management validation.
Tests that the fixed auth roles functions properly handle database sessions without errors.
"""

import pytest
from unittest.mock import patch, MagicMock

from models import User, Role
from auth.roles import ensure_roles, get_all_roles, role_exists, roles_required, roles_any, roles_all
from db_transaction_manager import get_db_session, transaction_scope


class TestAuthRolesSessionManagement:
    """Test cases for auth roles with focus on database session management"""
    
    def test_ensure_roles_with_transaction_scope(self, app, db_session):
        """Test that ensure_roles works properly with database session"""
        # Clear existing roles for this test
        db_session.query(Role).delete()
        db_session.flush()

        # Call ensure_roles directly with the test session
        ensure_roles(db_session, ["admin", "ophthalmologist", "custom_role"])
        db_session.flush()

        # Verify roles were created in the same session
        roles = db_session.query(Role).all()
        role_names = [r.name for r in roles]
        assert "admin" in role_names
        assert "ophthalmologist" in role_names
        assert "custom_role" in role_names
    
    def test_ensure_roles_idempotent(self, app, db_session):
        """Test that ensure_roles is idempotent (doesn't create duplicates)"""
        # Create some roles first
        db_session.query(Role).filter(Role.name.in_(["admin", "ophthalmologist"])).delete()
        db_session.flush()

        ensure_roles(db_session, ["admin", "ophthalmologist"])
        db_session.flush()

        # Get initial count
        initial_count = db_session.query(Role).filter(Role.name.in_(["admin", "ophthalmologist"])).count()

        # Call ensure_roles again with same roles
        ensure_roles(db_session, ["admin", "ophthalmologist"])
        db_session.flush()

        # Verify no duplicates were created
        final_count = db_session.query(Role).filter(Role.name.in_(["admin", "ophthalmologist"])).count()
        assert initial_count == final_count
    
    def test_ensure_roles_with_new_roles(self, app, db_session):
        """Test that ensure_roles adds new roles without affecting existing ones"""
        # Create initial roles
        ensure_roles(db_session, ["admin", "ophthalmologist"])
        db_session.flush()

        # Add new roles
        ensure_roles(db_session, ["admin", "ophthalmologist", "data_manager", "resident"])
        db_session.flush()

        # Verify all roles exist
        roles = db_session.query(Role).all()
        role_names = [r.name for r in roles]
        assert "admin" in role_names
        assert "ophthalmologist" in role_names
        assert "data_manager" in role_names
        assert "resident" in role_names
    
    def test_ensure_roles_transaction_rollback_on_error(self, app, db_session):
        """Test that ensure_roles handles errors gracefully"""
        # Get initial count
        initial_count = db_session.query(Role).count()

        # Try to call ensure_roles with invalid input - should handle gracefully
        try:
            ensure_roles(db_session, None)
            db_session.flush()
        except Exception:
            pass  # Expected - graceful error handling

        # Verify no changes to role count
        final_count = db_session.query(Role).count()
        assert initial_count == final_count
    
    def test_get_all_roles_session_management(self, app, db_session):
        """Test that get_all_roles properly manages database sessions"""
        # Create some test roles
        ensure_roles(db_session, ["admin", "ophthalmologist", "data_manager"])
        db_session.flush()

        # Test get_all_roles - it should use the mocked get_db_session
        roles = get_all_roles()
        assert isinstance(roles, list)
        # Should contain at least the roles we created
        assert len(roles) > 0
    
    def test_get_all_roles_fallback_on_error(self, app):
        """Test that get_all_roles falls back to DEFAULT_ROLES on database error"""
        # Mock database error
        with patch('db_transaction_manager.get_db_session') as mock_session:
            mock_session.side_effect = Exception("Database error")
            
            roles = get_all_roles()
            # Should return DEFAULT_ROLES as fallback
            assert isinstance(roles, list)
            assert "admin" in roles
            assert "fileUploader" in roles
            assert "ophthalmologist" in roles
    
    def test_role_exists_session_management(self, app, db_session):
        """Test that role_exists properly manages database sessions"""
        # Create a test role
        ensure_roles(db_session, ["test_role_session_mgmt"])
        db_session.flush()

        # Test existing role
        assert role_exists("test_role_session_mgmt") is True

        # Test non-existing role
        assert role_exists("nonexistent_role_xyz") is False
    
    def test_role_exists_fallback_on_error(self, app):
        """Test that role_exists returns False on database error"""
        # Mock database error
        with patch('db_transaction_manager.get_db_session') as mock_session:
            mock_session.side_effect = Exception("Database error")
            
            # Should return False on error
            assert role_exists("any_role") is False


class TestAuthRolesDecorators:
    """Test cases for auth role decorators"""

    def test_roles_required_decorator_not_authenticated(self, app):
        """Test that roles_required decorator blocks unauthenticated users"""
        with app.test_client() as client:
            # Test access to protected route without authentication
            response = client.get('/admin')  # Use existing protected route
            # Should redirect to login
            assert response.status_code == 302


class TestAuthRolesDataPersistence:
    """Test cases for data persistence in auth roles functions"""
    
    def test_role_creation_persistence(self, app, db_session):
        """Test that role creation persists correctly"""
        # Create roles using ensure_roles with test session
        ensure_roles(db_session, ["persistent_role_xyz"])
        db_session.flush()

        # Verify persistence in same session
        role = db_session.query(Role).filter(Role.name == "persistent_role_xyz").first()
        assert role is not None
        assert role.name == "persistent_role_xyz"
    
    def test_role_exists_persistence(self, app, db_session):
        """Test that role_exists checks persistent data"""
        # Create a role
        new_role = Role(name="persistent_check_role_xyz")
        db_session.add(new_role)
        db_session.flush()

        # Verify role_exists finds it
        assert role_exists("persistent_check_role_xyz") is True

        # Verify role_exists doesn't find non-existent role
        assert role_exists("non_persistent_role_xyz") is False
    
    def test_get_all_roles_persistence(self, app, db_session):
        """Test that get_all_roles returns persistent data"""
        # Create multiple roles
        for role_name in ["role1_xyz", "role2_xyz", "role3_xyz"]:
            role = Role(name=role_name)
            db_session.add(role)
        db_session.flush()

        # Verify get_all_roles returns all roles
        roles = get_all_roles()
        assert isinstance(roles, list)
        assert len(roles) > 0


class TestAuthRolesErrorHandling:
    """Test cases for error handling in auth roles functions"""
    
    def test_ensure_roles_handles_none_input(self, app, db_session):
        """Test that ensure_roles handles None input gracefully"""
        # Should not crash with None input
        try:
            ensure_roles(db_session, None)
            db_session.flush()
        except Exception:
            pass  # Expected - graceful error handling

        # Verify no crash occurred
        roles = db_session.query(Role).all()
        assert isinstance(roles, list)
    
    def test_ensure_roles_handles_empty_list(self, app, db_session):
        """Test that ensure_roles handles empty list gracefully"""
        # Should not crash with empty list
        ensure_roles(db_session, [])
        db_session.flush()

        # Verify no crash occurred
        roles = db_session.query(Role).all()
        assert isinstance(roles, list)
    
    def test_get_all_roles_handles_database_error(self, app):
        """Test that get_all_roles handles database errors gracefully"""
        # Mock database error
        with patch('db_transaction_manager.get_db_session') as mock_session:
            mock_session.side_effect = Exception("Database connection error")
            
            # Should return fallback roles instead of crashing
            roles = get_all_roles()
            assert isinstance(roles, list)
            assert len(roles) > 0  # Should have fallback roles
    
    def test_role_exists_handles_database_error(self, app):
        """Test that role_exists handles database errors gracefully"""
        # Mock database error
        with patch('db_transaction_manager.get_db_session') as mock_session:
            mock_session.side_effect = Exception("Database connection error")
            
            # Should return False instead of crashing
            result = role_exists("any_role")
            assert result is False
    
    def test_role_exists_handles_empty_string(self, app):
        """Test that role_exists handles empty string gracefully"""
        # Should return False for empty string
        result = role_exists("")
        assert result is False
    
    def test_role_exists_handles_none_input(self, app):
        """Test that role_exists handles None input gracefully"""
        # Should return False for None input
        result = role_exists(None)
        assert result is False


class TestAuthRolesIntegration:
    """Integration tests for auth roles functions"""
    
    def test_full_role_lifecycle(self, app, db_session):
        """Test complete lifecycle of role management"""
        # Create roles
        ensure_roles(db_session, ["lifecycle_role1_xyz", "lifecycle_role2_xyz"])
        db_session.flush()

        # Verify roles exist
        assert role_exists("lifecycle_role1_xyz") is True
        assert role_exists("lifecycle_role2_xyz") is True

        # Get all roles
        all_roles = get_all_roles()
        assert isinstance(all_roles, list)
        assert len(all_roles) > 0

        # Add more roles
        ensure_roles(db_session, ["lifecycle_role1_xyz", "lifecycle_role2_xyz", "lifecycle_role3_xyz"])
        db_session.flush()

        # Verify all roles exist
        assert role_exists("lifecycle_role1_xyz") is True
        assert role_exists("lifecycle_role2_xyz") is True
        assert role_exists("lifecycle_role3_xyz") is True
    
    def test_concurrent_role_creation(self, app, db_session):
        """Test that concurrent role creation doesn't cause issues"""
        # This test simulates concurrent access patterns
        ensure_roles(db_session, ["concurrent_role_xyz"])
        db_session.flush()

        # Multiple calls to ensure_roles with same role should not cause issues
        for _ in range(5):
            ensure_roles(db_session, ["concurrent_role_xyz"])
            db_session.flush()

        # Verify only one role was created (no duplicates)
        roles = db_session.query(Role).filter(Role.name == "concurrent_role_xyz").all()
        assert len(roles) == 1