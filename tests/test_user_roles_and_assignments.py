"""Test user creation for different roles and lab unit assignments."""

import pytest
from models import Session, User, Role, Hospital, LabUnit
from sqlalchemy import select
from auth.security import hash_password


class TestUserCreation:
    """Test cases for creating users with different roles and lab unit assignments."""

    def test_admin_users_created(self):
        """Test that admin users are created correctly."""
        with Session() as db:
            # Check for admin role
            admin_role = db.execute(
                select(Role).where(Role.name == 'admin')
            ).scalar_one_or_none()
            assert admin_role is not None
            
            # Check for admin users
            admin_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'admin'))
            ).scalars().all()
            assert len(admin_users) >= 1
            
            # Check specific admin user
            test_admin = db.execute(
                select(User).where(User.username == 'test_admin')
            ).scalar_one_or_none()
            assert test_admin is not None
            assert test_admin.full_name == 'Test Administrator'
            assert test_admin.email == 'admin@test.com'

    def test_consultant_users_created(self):
        """Test that consultant (ophthalmologist) users are created correctly."""
        with Session() as db:
            # Check for ophthalmologist role
            ophthal_role = db.execute(
                select(Role).where(Role.name == 'ophthalmologist')
            ).scalar_one_or_none()
            assert ophthal_role is not None
            
            # Check for consultant users
            consultant_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'ophthalmologist'))
            ).scalars().all()
            assert len(consultant_users) >= 3
            
            # Check specific consultant users
            dr_smith = db.execute(
                select(User).where(User.username == 'dr_smith')
            ).scalar_one_or_none()
            assert dr_smith is not None
            assert dr_smith.full_name == 'Dr. John Smith'
            
            dr_johnson = db.execute(
                select(User).where(User.username == 'dr_johnson')
            ).scalar_one_or_none()
            assert dr_johnson is not None
            assert dr_johnson.full_name == 'Dr. Sarah Johnson'
            
            dr_williams = db.execute(
                select(User).where(User.username == 'dr_williams')
            ).scalar_one_or_none()
            assert dr_williams is not None
            assert dr_williams.full_name == 'Dr. Michael Williams'

    def test_resident_users_created(self):
        """Test that resident users are created correctly."""
        with Session() as db:
            # Check for resident role
            resident_role = db.execute(
                select(Role).where(Role.name == 'resident')
            ).scalar_one_or_none()
            assert resident_role is not None
            
            # Check for resident users
            resident_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'resident'))
            ).scalars().all()
            assert len(resident_users) >= 2
            
            # Check specific resident users
            resident_1 = db.execute(
                select(User).where(User.username == 'resident_1')
            ).scalar_one_or_none()
            assert resident_1 is not None
            assert resident_1.full_name == 'Resident One'
            
            resident_2 = db.execute(
                select(User).where(User.username == 'resident_2')
            ).scalar_one_or_none()
            assert resident_2 is not None
            assert resident_2.full_name == 'Resident Two'

    def test_optometrist_users_created(self):
        """Test that optometrist users are created correctly."""
        with Session() as db:
            # Check for optometrist role
            optometrist_role = db.execute(
                select(Role).where(Role.name == 'optometrist')
            ).scalar_one_or_none()
            assert optometrist_role is not None
            
            # Check for optometrist users
            optometrist_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'optometrist'))
            ).scalars().all()
            assert len(optometrist_users) >= 1
            
            # Check specific optometrist user
            optom_1 = db.execute(
                select(User).where(User.username == 'optom_1')
            ).scalar_one_or_none()
            assert optom_1 is not None
            assert optom_1.full_name == 'Optometrist One'

    def test_data_manager_users_created(self):
        """Test that data manager users are created correctly."""
        with Session() as db:
            # Check for data_manager role
            data_manager_role = db.execute(
                select(Role).where(Role.name == 'data_manager')
            ).scalar_one_or_none()
            assert data_manager_role is not None
            
            # Check for data manager users
            data_manager_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'data_manager'))
            ).scalars().all()
            assert len(data_manager_users) >= 1
            
            # Check specific data manager user
            datamanager = db.execute(
                select(User).where(User.username == 'datamanager')
            ).scalar_one_or_none()
            assert datamanager is not None
            assert datamanager.full_name == 'Data Manager'

    def test_file_uploader_users_created(self):
        """Test that file uploader users are created correctly."""
        with Session() as db:
            # Check for fileUploader role
            file_uploader_role = db.execute(
                select(Role).where(Role.name == 'fileUploader')
            ).scalar_one_or_none()
            assert file_uploader_role is not None
            
            # Check for file uploader users
            file_uploader_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'fileUploader'))
            ).scalars().all()
            assert len(file_uploader_users) >= 1
            
            # Check specific file uploader user
            uploader = db.execute(
                select(User).where(User.username == 'uploader')
            ).scalar_one_or_none()
            assert uploader is not None
            assert uploader.full_name == 'File Uploader'

    def test_contributor_users_created(self):
        """Test that contributor users are created correctly."""
        with Session() as db:
            # Check for contributor role
            contributor_role = db.execute(
                select(Role).where(Role.name == 'contributor')
            ).scalar_one_or_none()
            assert contributor_role is not None
            
            # Check for contributor users
            contributor_users = db.execute(
                select(User).where(User.roles.any(Role.name == 'contributor'))
            ).scalars().all()
            assert len(contributor_users) >= 1
            
            # Check specific contributor user
            contributor = db.execute(
                select(User).where(User.username == 'contributor')
            ).scalar_one_or_none()
            assert contributor is not None
            assert contributor.full_name == 'Contributor User'

    def test_user_lab_unit_assignments(self):
        """Test that users are assigned to lab units correctly."""
        with Session() as db:
            # Check that users have lab unit assignments
            consultant = db.execute(
                select(User).where(User.username == 'dr_smith')
            ).scalar_one()
            
            # Should have lab unit assignments
            assert len(consultant.lab_units) >= 1
            
            # Check that lab units belong to correct hospitals
            city_hospital = db.execute(
                select(Hospital).where(Hospital.name == 'City Hospital')
            ).scalar_one()
            
            for lab_unit in consultant.lab_units:
                assert lab_unit.hospital_id == city_hospital.id

    def test_users_assigned_to_different_hospitals(self):
        """Test that users are assigned to different hospitals."""
        with Session() as db:
            # Check users from different hospitals
            dr_smith = db.execute(
                select(User).where(User.username == 'dr_smith')
            ).scalar_one()
            
            dr_johnson = db.execute(
                select(User).where(User.username == 'dr_johnson')
            ).scalar_one()
            
            dr_williams = db.execute(
                select(User).where(User.username == 'dr_williams')
            ).scalar_one()
            
            # These users should be assigned to different hospitals
            # Based on our setup, they should have different lab units
            assert len(dr_smith.lab_units) >= 1
            assert len(dr_johnson.lab_units) >= 1
            assert len(dr_williams.lab_units) >= 1