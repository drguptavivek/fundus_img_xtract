"""Test utilities and helper functions for admin route tests."""

from models import User, Role, Session
from sqlalchemy import select


def create_admin_user():
    """Create an admin user for testing purposes."""
    with Session() as db:
        # Check if admin role exists
        admin_role = db.execute(
            select(Role).where(Role.name == 'admin')
        ).scalar_one_or_none()
        
        if not admin_role:
            admin_role = Role(name='admin')
            db.add(admin_role)
            db.flush()
        
        # Create admin user
        admin_user = User(
            username='testadmin',
            password_hash='hashed_password_for_testing',
            is_active=True
        )
        admin_user.roles.append(admin_role)
        db.add(admin_user)
        db.commit()
        
        return admin_user


def create_test_user(username='testuser'):
    """Create a test user for testing purposes."""
    with Session() as db:
        user = User(
            username=username,
            password_hash='hashed_password_for_testing',
            is_active=True
        )
        db.add(user)
        db.commit()
        return user


def create_role(name):
    """Create a role for testing purposes."""
    with Session() as db:
        role = Role(name=name)
        db.add(role)
        db.commit()
        return role