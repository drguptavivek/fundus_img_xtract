"""
Test database seeding - populates core entities at test session start.

This module provides a session-scoped fixture that seeds the test database with:
- Roles (master_admin, local_admin, ophthalmologist, resident, arbitrator, etc.)
- Diseases (DR, Glaucoma, AMD)
- Cameras (Test Camera, Fundus Camera, etc.)
- Areas (Macula, Optic Disc, etc.)
- Grades (for DR, Glaucoma, AMD)
- Hospitals (Hospital A, Hospital B)
- Lab Units (Lab A1, Lab A2, Lab B1, Lab B2)
- Test Users (master_admin, site_admin_a, site_admin_b, ophthalmologists, etc.)
"""
import pytest
from models import (
    Role, Disease, Camera, Area, Grade, Hospital, LabUnit, User
)
from auth.security import hash_password


@pytest.fixture(scope="session", autouse=True)
def seed_test_database(test_engine):
    """
    Seed the test database with core entities.
    
    This fixture runs automatically at the start of the test session
    and populates all foundational data that should persist across all tests.
    """
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        # ===== ROLES =====
        roles_data = [
            'master_admin', 'local_admin', 'ophthalmologist', 'resident',
            'arbitrator', 'optometrist', 'fileUploader', 'data_manager',
            'researcher', 'dataset_creator', 'analytics_viewer'
        ]
        roles = {}
        for role_name in roles_data:
            role = session.query(Role).filter_by(name=role_name).first()
            if not role:
                role = Role(name=role_name)
                session.add(role)
            roles[role_name] = role
        session.flush()
        
        # ===== DISEASES =====
        diseases_data = ['DR', 'Glaucoma', 'AMD', 'Test Disease']
        diseases = {}
        for disease_name in diseases_data:
            disease = session.query(Disease).filter_by(name=disease_name).first()
            if not disease:
                disease = Disease(name=disease_name)
                session.add(disease)
            diseases[disease_name] = disease
        session.flush()
        
        # ===== CAMERAS =====
        cameras_data = ['Test Camera', 'Fundus Camera', 'Topcon TRC-50DX', 'Canon CR-2']
        cameras = {}
        for camera_name in cameras_data:
            camera = session.query(Camera).filter_by(name=camera_name).first()
            if not camera:
                camera = Camera(name=camera_name)
                session.add(camera)
            cameras[camera_name] = camera
        session.flush()
        
        # ===== AREAS =====
        areas_data = ['Test Area', 'Macula', 'Optic Disc', 'Peripheral Retina']
        areas = {}
        for area_name in areas_data:
            area = session.query(Area).filter_by(name=area_name).first()
            if not area:
                area = Area(name=area_name)
                session.add(area)
            areas[area_name] = area
        session.flush()
        
        # ===== HOSPITALS =====
        hospitals_data = [
            {'id': 1, 'name': 'Hospital A'},
            {'id': 2, 'name': 'Hospital B'}
        ]
        hospitals = {}
        for hosp_data in hospitals_data:
            hospital = session.query(Hospital).filter_by(id=hosp_data['id']).first()
            if not hospital:
                hospital = Hospital(**hosp_data)
                session.add(hospital)
            hospitals[hosp_data['name']] = hospital
        session.flush()
        
        # ===== LAB UNITS =====
        lab_units_data = [
            {'id': 1, 'name': 'Lab A1', 'hospital_id': 1},
            {'id': 2, 'name': 'Lab A2', 'hospital_id': 1},
            {'id': 3, 'name': 'Lab B1', 'hospital_id': 2},
            {'id': 4, 'name': 'Lab B2', 'hospital_id': 2}
        ]
        lab_units = {}
        for lab_data in lab_units_data:
            lab_unit = session.query(LabUnit).filter_by(id=lab_data['id']).first()
            if not lab_unit:
                lab_unit = LabUnit(**lab_data)
                session.add(lab_unit)
            lab_units[lab_data['name']] = lab_unit
        session.flush()
        
        # ===== TEST USERS =====
        users_data = [
            {
                'username': 'master_admin',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': True,
                'roles': ['master_admin']
            },
            {
                'username': 'site_admin_a',
                'password': 'Test@2026',
                'hospital_id': 1,
                'is_master_admin': False,
                'roles': ['local_admin']
            },
            {
                'username': 'site_admin_b',
                'password': 'Test@2026',
                'hospital_id': 2,
                'is_master_admin': False,
                'roles': ['local_admin']
            },
            {
                'username': 'ophthalmologist_a',
                'password': 'Test@2026',
                'hospital_id': 1,
                'is_master_admin': False,
                'roles': ['ophthalmologist']
            },
            {
                'username': 'ophthalmologist_b',
                'password': 'Test@2026',
                'hospital_id': 2,
                'is_master_admin': False,
                'roles': ['ophthalmologist']
            },
            {
                'username': 'ophthalmologist_cross',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': False,
                'roles': ['ophthalmologist']
            }
        ]
        
        users = {}
        for user_data in users_data:
            user = session.query(User).filter_by(username=user_data['username']).first()
            if not user:
                user_roles = [roles[role_name] for role_name in user_data['roles']]
                user = User(
                    username=user_data['username'],
                    password_hash=hash_password(user_data['password']),
                    hospital_id=user_data['hospital_id'],
                    is_master_admin=user_data['is_master_admin'],
                    roles=user_roles
                )
                session.add(user)
            users[user_data['username']] = user
        
        session.commit()
        
        return {
            'roles': roles,
            'diseases': diseases,
            'cameras': cameras,
            'areas': areas,
            'hospitals': hospitals,
            'lab_units': lab_units,
            'users': users
        }
    finally:
        session.close()
