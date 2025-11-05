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
        """Test that ensure_roles works properly with transaction_scope"""
        # Clear existing roles for this test
        db_session.query(Role).delete()
        db_session.commit()
        
        # Use transaction_scope to ensure roles
        with transaction_scope() as db:
            ensure_roles(db, ["admin", "ophthalmologist", "custom_role"])
        
        # Verify roles were created with new session
        with get_db_session() as db:
            roles = db.query(Role).all()
            role_names = [r.name for r in roles]
            assert "admin" in role_names
            assert "ophthalmologist" in role_names
            assert "custom_role" in role_names
    
    def test_ensure_roles_idempotent(self, app, db_session):
        """Test that ensure_roles is idempotent (doesn't create duplicates)"""
        # Create some roles first
        with transaction_scope() as db:
            ensure_roles(db, ["admin", "ophthalmologist"])
        
        # Get initial count
        with get_db_session() as db:
            initial_count = db.query(Role).count()
        
        # Call ensure_roles again with same roles
        with transaction_scope() as db:
            ensure_roles(db, ["admin", "ophthalmologist"])
        
        # Verify no duplicates were created
        with get_db_session() as db:
            final_count = db.query(Role).count()
            assert initial_count == final_count
    
    def test_ensure_roles_with_new_roles(self, app, db_session):
        """Test that ensure_roles adds new roles without affecting existing ones"""
        # Create initial roles
        with transaction_scope() as db:
            ensure_roles(db, ["admin", "ophthalmologist"])
        
        # Add new roles
        with transaction_scope() as db:
            ensure_roles(db, ["admin", "ophthalmologist", "data_manager", "resident"])
        
        # Verify all roles exist
        with get_db_session() as db:
            roles = db.query(Role).all()
            role_names = [r.name for r in roles]
            assert "admin" in role_names
            assert "ophthalmologist" in role_names
            assert "data_manager" in role_names
            assert "resident" in role_names
    
    def test_ensure_roles_transaction_rollback_on_error(self, app, db_session):
        """Test that ensure_roles rolls back transaction on error"""
        # Get initial count
        with get_db_session() as db:
            initial_count = db.query(Role).count()
        
        # Mock an error during role creation
        with patch('sqlalchemy.orm.Session.add_all') as mock_add:
            mock_add.side_effect = Exception("Database error")
            
            with pytest.raises(Exception):
                with transaction_scope() as db:
                    ensure_roles(db, ["new_role"])
        
        # Verify no new roles were added due to rollback
        with get_db_session() as db:
            final_count = db.query(Role).count()
            assert initial_count == final_count
    
    def test_get_all_roles_session_management(self, app, db_session):
        """Test that get_all_roles properly manages database sessions"""
        # Create some test roles
        with transaction_scope() as db:
            ensure_roles(db, ["admin", "ophthalmologist", "data_manager"])
        
        # Test get_all_roles
        roles = get_all_roles()
        assert isinstance(roles, list)
        assert "admin" in roles
        assert "ophthalmologist" in roles
        assert "data_manager" in roles
    
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
        with transaction_scope() as db:
            ensure_roles(db, ["test_role"])
        
        # Test existing role
        assert role_exists("test_role") is True
        
        # Test non-existing role
        assert role_exists("nonexistent_role") is False
    
    def test_role_exists_fallback_on_error(self, app):
        """Test that role_exists returns False on database error"""
        # Mock database error
        with patch('db_transaction_manager.get_db_session') as mock_session:
            mock_session.side_effect = Exception("Database error")
            
            # Should return False on error
            assert role_exists("any_role") is False


class TestAuthRolesDecorators:
    """Test cases for auth role decorators"""
    
    def test_roles_required_decorator(self, app, test_users):
        """Test that roles_required decorator works correctly"""
        with app.test_client() as client:
            # Login as admin user
            client.post("/login", data={
                "username": test_users["admin"].username,
                "password": "Test@2026"
            })
            
            # Create a test route with roles_required decorator
            @app.route('/test-admin-only')
            @roles_required("admin")
            def test_admin_only():
                return {"success": True}
            
            # Test access with admin role
            response = client.get('/test-admin-only')
            assert response.status_code == 200
    
    def test_roles_required_decorator_unauthorized(self, app, test_users):
        """Test that roles_required decorator blocks unauthorized users"""
        with app.test_client() as client:
            # Login as resident user (not admin)
            client.post("/login", data={
                "username": test_users["resident"].username,
                "password": "TestPassword123!"
            })
            
            # Create a test route with roles_required decorator
            @app.route('/test-admin-only')
            @roles_required("admin")
            def test_admin_only():
                return {"success": True}
            
            # Test access without admin role
            response = client.get('/test-admin-only')
            assert response.status_code == 403
    
    def test_roles_required_decorator_not_authenticated(self, app):
        """Test that roles_required decorator blocks unauthenticated users"""
        with app.test_client() as client:
            # Create a test route with roles_required decorator
            @app.route('/test-auth-required')
            @roles_required("admin")
            def test_auth_required():
                return {"success": True}
            
            # Test access without authentication
            response = client.get('/test-auth-required')
            # Should redirect to login
            assert response.status_code == 302
    
    def test_roles_any_decorator(self, app, test_users):
        """Test that roles_any decorator works correctly"""
        with app.test_client() as client:
            # Login as resident user
            client.post("/login", data={
                "username": test_users["resident"].username,
                "password": "TestPassword123!"
            })
            
            # Create a test route with roles_any decorator
            @app.route('/test-multiple-roles')
            @roles_any("admin", "ophthalmologist")
            def test_multiple_roles():
                return {"success": True}
            
            # Test access with ophthalmologist role
            response = client.get('/test-multiple-roles')
            assert response.status_code == 200
    
    def test_roles_all_decorator(self, app, db_session):
        """Test that roles_all decorator works correctly"""
        # Create a user with multiple roles
        with transaction_scope() as db:
            admin_role = db.query(Role).filter(Role.name == "admin").first()
            oph_role = db.query(Role).filter(Role.name == "ophthalmologist").first()
            
            if not admin_role:
                admin_role = Role(name="admin")
                db.add(admin_role)
            if not oph_role:
                oph_role = Role(name="ophthalmologist")
                db.add(oph_role)
            
            multi_role_user = User(
                username="multi_role_user",
                password_hash="hashed_password",
                is_active=True,
                full_name="Multi Role User",
                roles=[admin_role, oph_role]
            )
            db.add(multi_role_user)
        
        with app.test_client() as client:
            # Login as multi-role user
            client.post("/login", data={
                "username": "multi_role_user",
                "password": "any_password"  # Password verification not important for this test
            })
            
            # Create a test route with roles_all decorator
            @app.route('/test-all-roles')
            @roles_all("admin", "ophthalmologist")
            def test_all_roles():
                return {"success": True}
            
            # Test access with all required roles
            response = client.get('/test-all-roles')
            assert response.status_code == 200


class TestAuthRolesDataPersistence:
    """Test cases for data persistence in auth roles functions"""
    
    def test_role_creation_persistence(self, app):
        """Test that role creation persists correctly"""
        # Create roles using ensure_roles
        with transaction_scope() as db:
            ensure_roles(db, ["persistent_role"])
        
        # Verify persistence with new session
        with get_db_session() as db:
            role = db.query(Role).filter(Role.name == "persistent_role").first()
            assert role is not None
            assert role.name == "persistent_role"
    
    def test_role_exists_persistence(self, app):
        """Test that role_exists checks persistent data"""
        # Create a role
        with transaction_scope() as db:
            new_role = Role(name="persistent_check_role")
            db.add(new_role)
        
        # Verify role_exists finds it with new session
        assert role_exists("persistent_check_role") is True
        
        # Verify role_exists doesn't find non-existent role
        assert role_exists("non_persistent_role") is False
    
    def test_get_all_roles_persistence(self, app):
        """Test that get_all_roles returns persistent data"""
        # Create multiple roles
        with transaction_scope() as db:
            for role_name in ["role1", "role2", "role3"]:
                role = Role(name=role_name)
                db.add(role)
        
        # Verify get_all_roles returns all persistent roles
        roles = get_all_roles()
        assert "role1" in roles
        assert "role2" in roles
        assert "role3" in roles


class TestAuthRolesErrorHandling:
    """Test cases for error handling in auth roles functions"""
    
    def test_ensure_roles_handles_none_input(self, app, db_session):
        """Test that ensure_roles handles None input gracefully"""
        with transaction_scope() as db:
            # Should not crash with None input
            ensure_roles(db, None)
        
        # Verify no crash occurred
        with get_db_session() as db:
            roles = db.query(Role).all()
            assert isinstance(roles, list)
    
    def test_ensure_roles_handles_empty_list(self, app, db_session):
        """Test that ensure_roles handles empty list gracefully"""
        with transaction_scope() as db:
            # Should not crash with empty list
            ensure_roles(db, [])
        
        # Verify no crash occurred
        with get_db_session() as db:
            roles = db.query(Role).all()
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
    
    def test_full_role_lifecycle(self, app):
        """Test complete lifecycle of role management"""
        # Start with no roles
        with transaction_scope() as db:
            db.query(Role).delete()
        
        # Create roles
        with transaction_scope() as db:
            ensure_roles(db, ["lifecycle_role1", "lifecycle_role2"])
        
        # Verify roles exist
        assert role_exists("lifecycle_role1") is True
        assert role_exists("lifecycle_role2") is True
        
        # Get all roles
        all_roles = get_all_roles()
        assert "lifecycle_role1" in all_roles
        assert "lifecycle_role2" in all_roles
        
        # Add more roles
        with transaction_scope() as db:
            ensure_roles(db, ["lifecycle_role1", "lifecycle_role2", "lifecycle_role3"])
        
        # Verify all roles still exist
        assert role_exists("lifecycle_role1") is True
        assert role_exists("lifecycle_role2") is True
        assert role_exists("lifecycle_role3") is True
        
        # Final verification with get_all_roles
        final_roles = get_all_roles()
        assert "lifecycle_role1" in final_roles
        assert "lifecycle_role2" in final_roles
        assert "lifecycle_role3" in final_roles
    
    def test_concurrent_role_creation(self, app):
        """Test that concurrent role creation doesn't cause issues"""
        # This test simulates concurrent access patterns
        with transaction_scope() as db:
            ensure_roles(db, ["concurrent_role"])
        
        # Multiple calls to ensure_roles with same role should not cause issues
        for _ in range(5):
            with transaction_scope() as db:
                ensure_roles(db, ["concurrent_role"])
        
        # Verify only one role was created
        with get_db_session() as db:
            roles = db.query(Role).filter(Role.name == "concurrent_role").all()
            assert len(roles) == 1