"""Test database setup and connectivity."""

import pytest
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import Base, engine, Session, User, Role
from sqlalchemy import create_engine, select, text


class TestDatabaseSetup:
    """Test cases for database setup and connectivity."""

    def test_database_connection(self):
        """Test that we can connect to the database."""
        # Test that we can connect to the database
        with Session() as db:
            # Try a simple query
            result = db.execute(select(1)).scalar()
            assert result == 1

    def test_tables_created(self):
        """Test that all required tables are created."""
        # Check that key tables exist by querying them
        with Session() as db:
            # These queries will fail if tables don't exist
            db.execute(text("SELECT count(*) FROM users")).fetchone()
            db.execute(text("SELECT count(*) FROM roles")).fetchone()
            db.execute(text("SELECT count(*) FROM user_roles")).fetchone()
            
            # Test that we can query some tables
            user_count = db.query(User).count()
            role_count = db.query(Role).count()
            
            # Just verify the queries work, counts can be 0
            assert user_count >= 0
            assert role_count >= 0

    def test_sample_data_creation(self):
        """Test creating sample data."""
        with Session() as db:
            # Check if admin role exists, create if not
            admin_role = db.execute(
                select(Role).where(Role.name == 'admin')
            ).scalar_one_or_none()
            
            if not admin_role:
                admin_role = Role(name='admin')
                db.add(admin_role)
                db.flush()
            
            # Check if test user exists, create if not
            test_user = db.execute(
                select(User).where(User.username == 'testuser')
            ).scalar_one_or_none()
            
            if not test_user:
                from auth.security import hash_password
                test_user = User(
                    username='testuser',
                    password_hash=hash_password('testpassword'),
                    is_active=True,
                    full_name='Test User'
                )
                test_user.roles.append(admin_role)
                db.add(test_user)
                db.commit()
            
            # Verify user was created
            created_user = db.execute(
                select(User).where(User.username == 'testuser')
            ).scalar_one_or_none()
            
            assert created_user is not None
            assert created_user.username == 'testuser'
            assert created_user.full_name == 'Test User'
            assert len(created_user.roles) >= 1