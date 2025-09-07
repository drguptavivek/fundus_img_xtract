"""Test suite initialization and master data setup."""

import pytest
import sys
import os
# Add the project root to the path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models import (
    Session, User, Role, Hospital, LabUnit, Camera, Disease, Area
)
from auth.security import hash_password
from sqlalchemy import select


def create_master_data():
    """Create master data for testing."""
    db = Session()
    try:
        # Create roles
        roles_data = [
            {'name': 'admin'},
            {'name': 'ophthalmologist'},
            {'name': 'resident'},
            {'name': 'optometrist'},
            {'name': 'data_manager'},
            {'name': 'fileUploader'},
            {'name': 'contributor'}
        ]
        
        for role_data in roles_data:
            role = db.execute(
                select(Role).where(Role.name == role_data['name'])
            ).scalar_one_or_none()
            if not role:
                role = Role(**role_data)
                db.add(role)
        
        db.flush()
        
        # Create hospitals
        hospitals_data = [
            {'name': 'City Hospital'},
            {'name': 'University Medical Center'},
            {'name': 'Community Eye Clinic'}
        ]
        
        hospitals = []
        for hospital_data in hospitals_data:
            hospital = db.execute(
                select(Hospital).where(Hospital.name == hospital_data['name'])
            ).scalar_one_or_none()
            if not hospital:
                hospital = Hospital(**hospital_data)
                db.add(hospital)
                db.flush()
            hospitals.append(hospital)
        
        # Create lab units
        lab_units_data = [
            {'name': 'OPD Unit 1', 'hospital_id': hospitals[0].id},
            {'name': 'OPD Unit 2', 'hospital_id': hospitals[0].id},
            {'name': 'Emergency Unit', 'hospital_id': hospitals[0].id},
            {'name': 'Research Lab', 'hospital_id': hospitals[1].id},
            {'name': 'Pediatrics Unit', 'hospital_id': hospitals[1].id},
            {'name': 'General OPD', 'hospital_id': hospitals[2].id}
        ]
        
        lab_units = []
        for lab_unit_data in lab_units_data:
            lab_unit = db.execute(
                select(LabUnit).where(
                    LabUnit.name == lab_unit_data['name'],
                    LabUnit.hospital_id == lab_unit_data['hospital_id']
                )
            ).scalar_one_or_none()
            if not lab_unit:
                lab_unit = LabUnit(**lab_unit_data)
                db.add(lab_unit)
                db.flush()
            lab_units.append(lab_unit)
        
        # Create cameras
        cameras_data = [
            {'name': 'Topcon NW400'},
            {'name': 'Zeiss Cirrus HD-OCT'},
            {'name': 'NIDEK AFC-300'},
            {'name': 'Canon CR-2 AF'},
            {'name': 'Kowa VX-10'}
        ]
        
        cameras = []
        for camera_data in cameras_data:
            camera = db.execute(
                select(Camera).where(Camera.name == camera_data['name'])
            ).scalar_one_or_none()
            if not camera:
                camera = Camera(**camera_data)
                db.add(camera)
                db.flush()
            cameras.append(camera)
        
        # Create diseases
        diseases_data = [
            {'name': 'Glaucoma'},
            {'name': 'Diabetic Retinopathy'},
            {'name': 'Age-related Macular Degeneration'},
            {'name': 'Hypertensive Retinopathy'},
            {'name': 'Retinal Vein Occlusion'}
        ]
        
        diseases = []
        for disease_data in diseases_data:
            disease = db.execute(
                select(Disease).where(Disease.name == disease_data['name'])
            ).scalar_one_or_none()
            if not disease:
                disease = Disease(**disease_data)
                db.add(disease)
                db.flush()
            diseases.append(disease)
        
        # Create areas
        areas_data = [
            {'name': 'Urban'},
            {'name': 'Suburban'},
            {'name': 'Rural'},
            {'name': 'Remote'}
        ]
        
        areas = []
        for area_data in areas_data:
            area = db.execute(
                select(Area).where(Area.name == area_data['name'])
            ).scalar_one_or_none()
            if not area:
                area = Area(**area_data)
                db.add(area)
                db.flush()
            areas.append(area)
        
        db.commit()
        print("Master data created successfully.")
        
        return {
            'hospitals': hospitals,
            'lab_units': lab_units,
            'cameras': cameras,
            'diseases': diseases,
            'areas': areas
        }
        
    except Exception as e:
        db.rollback()
        print(f"Error creating master data: {e}")
        raise
    finally:
        db.close()


def create_test_users(master_data):
    """Create test users with different roles and lab unit assignments."""
    db = Session()
    try:
        hospitals = master_data['hospitals']
        lab_units = master_data['lab_units']
        
        # Get roles
        admin_role = db.execute(select(Role).where(Role.name == 'admin')).scalar_one()
        ophthalmologist_role = db.execute(select(Role).where(Role.name == 'ophthalmologist')).scalar_one()
        resident_role = db.execute(select(Role).where(Role.name == 'resident')).scalar_one()
        optometrist_role = db.execute(select(Role).where(Role.name == 'optometrist')).scalar_one()
        data_manager_role = db.execute(select(Role).where(Role.name == 'data_manager')).scalar_one()
        file_uploader_role = db.execute(select(Role).where(Role.name == 'fileUploader')).scalar_one()
        contributor_role = db.execute(select(Role).where(Role.name == 'contributor')).scalar_one()
        
        # Create admin user
        admin_user = db.execute(
            select(User).where(User.username == 'test_admin')
        ).scalar_one_or_none()
        if not admin_user:
            admin_user = User(
                username='test_admin',
                password_hash=hash_password('adminpassword'),
                is_active=True,
                full_name='Test Administrator',
                email='admin@test.com'
            )
            admin_user.roles.append(admin_role)
            db.add(admin_user)
            db.flush()
        
        # Create ophthalmologist users (consultants)
        consultant_users = []
        consultant_data = [
            {
                'username': 'dr_smith',
                'password': 'smithpassword',
                'full_name': 'Dr. John Smith',
                'email': 'smith@hospital.com',
                'lab_units': [lab_units[0], lab_units[1]]  # Assigned to OPD Unit 1 and 2
            },
            {
                'username': 'dr_johnson',
                'password': 'johnsonpassword',
                'full_name': 'Dr. Sarah Johnson',
                'email': 'johnson@hospital.com',
                'lab_units': [lab_units[3]]  # Assigned to Research Lab
            },
            {
                'username': 'dr_williams',
                'password': 'williamspassword',
                'full_name': 'Dr. Michael Williams',
                'email': 'williams@clinic.com',
                'lab_units': [lab_units[5]]  # Assigned to General OPD
            }
        ]
        
        for data in consultant_data:
            user = db.execute(
                select(User).where(User.username == data['username'])
            ).scalar_one_or_none()
            if not user:
                user = User(
                    username=data['username'],
                    password_hash=hash_password(data['password']),
                    is_active=True,
                    full_name=data['full_name'],
                    email=data['email']
                )
                user.roles.append(ophthalmologist_role)
                user.lab_units.extend(data['lab_units'])
                db.add(user)
                db.flush()
            consultant_users.append(user)
        
        # Create resident users
        resident_users = []
        resident_data = [
            {
                'username': 'resident_1',
                'password': 'resident1password',
                'full_name': 'Resident One',
                'email': 'resident1@hospital.edu'
            },
            {
                'username': 'resident_2',
                'password': 'resident2password',
                'full_name': 'Resident Two',
                'email': 'resident2@hospital.edu'
            }
        ]
        
        for data in resident_data:
            user = db.execute(
                select(User).where(User.username == data['username'])
            ).scalar_one_or_none()
            if not user:
                user = User(
                    username=data['username'],
                    password_hash=hash_password(data['password']),
                    is_active=True,
                    full_name=data['full_name'],
                    email=data['email']
                )
                user.roles.append(resident_role)
                db.add(user)
                db.flush()
            resident_users.append(user)
        
        # Create optometrist users
        optometrist_users = []
        optometrist_data = [
            {
                'username': 'optom_1',
                'password': 'optom1password',
                'full_name': 'Optometrist One',
                'email': 'optom1@clinic.com',
                'lab_units': [lab_units[0]]  # Assigned to OPD Unit 1
            }
        ]
        
        for data in optometrist_data:
            user = db.execute(
                select(User).where(User.username == data['username'])
            ).scalar_one_or_none()
            if not user:
                user = User(
                    username=data['username'],
                    password_hash=hash_password(data['password']),
                    is_active=True,
                    full_name=data['full_name'],
                    email=data['email']
                )
                user.roles.append(optometrist_role)
                user.lab_units.extend(data['lab_units'])
                db.add(user)
                db.flush()
            optometrist_users.append(user)
        
        # Create data manager user
        data_manager_user = db.execute(
            select(User).where(User.username == 'datamanager')
        ).scalar_one_or_none()
        if not data_manager_user:
            data_manager_user = User(
                username='datamanager',
                password_hash=hash_password('datamanagerpassword'),
                is_active=True,
                full_name='Data Manager',
                email='datamanager@hospital.org'
            )
            data_manager_user.roles.append(data_manager_role)
            db.add(data_manager_user)
            db.flush()
        
        # Create file uploader user
        file_uploader_user = db.execute(
            select(User).where(User.username == 'uploader')
        ).scalar_one_or_none()
        if not file_uploader_user:
            file_uploader_user = User(
                username='uploader',
                password_hash=hash_password('uploaderpassword'),
                is_active=True,
                full_name='File Uploader',
                email='uploader@hospital.org'
            )
            file_uploader_user.roles.append(file_uploader_role)
            db.add(file_uploader_user)
            db.flush()
        
        # Create contributor user
        contributor_user = db.execute(
            select(User).where(User.username == 'contributor')
        ).scalar_one_or_none()
        if not contributor_user:
            contributor_user = User(
                username='contributor',
                password_hash=hash_password('contributorpassword'),
                is_active=True,
                full_name='Contributor User',
                email='contributor@hospital.org'
            )
            contributor_user.roles.append(contributor_role)
            contributor_user.lab_units.append(lab_units[0])  # Assigned to OPD Unit 1
            db.add(contributor_user)
            db.flush()
        
        db.commit()
        print("Test users created successfully.")
        
        return {
            'admin': admin_user,
            'consultants': consultant_users,
            'residents': resident_users,
            'optometrists': optometrist_users,
            'data_manager': data_manager_user,
            'file_uploader': file_uploader_user,
            'contributor': contributor_user
        }
        
    except Exception as e:
        db.rollback()
        print(f"Error creating test users: {e}")
        raise
    finally:
        db.close()


def setup_test_environment():
    """Setup complete test environment with master data and users."""
    print("Setting up test environment...")
    
    # Create master data
    master_data = create_master_data()
    
    # Create test users
    test_users = create_test_users(master_data)
    
    print("Test environment setup completed successfully.")
    
    return {
        'master_data': master_data,
        'test_users': test_users
    }


if __name__ == "__main__":
    setup_test_environment()