"""
Test database seeding - populates core entities at test session start.

This module provides a session-scoped fixture that seeds the test database with:
- Roles (master_admin, local_admin, ophthalmologist, resident, arbitrator, etc.)
- Diseases (DR, Glaucoma, AMD)
- Cameras (Test Camera, Fundus Camera, etc.)
- Areas (Macula, Optic Disc, etc.)
- Grades (for DR, Glaucoma, AMD)
- Hospitals (Hospital A, Hospital B)
- Lab Units (Lab A1, A2, A3 for Hospital A; Lab B1, B2, B3 for Hospital B)
- Test Users (master_admin, site_admin_a, site_admin_b, ophthalmologists, etc.)

Lab Unit ID Assignment:
  ID 1-3: Hospital A lab units (Lab A1, A2, A3)
  ID 4-6: Hospital B lab units (Lab B1, B2, B3)
"""
import pytest
from sqlalchemy import text
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
            'admin', 'master_admin', 'local_admin', 'ophthalmologist', 'resident',
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
        # Create with specific IDs for consistency with test expectations
        # Test Camera is ID 1 for backward compatibility with tests that query by name
        cameras_data = [
            {'id': 1, 'name': 'Test Camera'},
            {'id': 2, 'name': 'Fundus Camera'},
            {'id': 3, 'name': 'Topcon TRC-50DX'},
            {'id': 4, 'name': 'Canon CR-2'},
        ]
        cameras = {}
        for camera_data in cameras_data:
            camera = session.query(Camera).filter_by(id=camera_data['id']).first()
            if not camera:
                camera = Camera(id=camera_data['id'], name=camera_data['name'])
                session.add(camera)
            cameras[camera_data['name']] = camera
        session.flush()

        # ===== AREAS =====
        # Create with specific IDs for consistency with test expectations
        areas_data = [
            {'id': 1, 'name': 'Test Area'},
            {'id': 2, 'name': 'Macula'},
            {'id': 3, 'name': 'Optic Disc'},
            {'id': 4, 'name': 'Peripheral Retina'},
        ]
        areas = {}
        for area_data in areas_data:
            area = session.query(Area).filter_by(id=area_data['id']).first()
            if not area:
                area = Area(id=area_data['id'], name=area_data['name'])
                session.add(area)
            areas[area_data['name']] = area
        session.flush()
        
        # ===== HOSPITALS =====
        # Use names that tests expect (queried by name in test fixtures)
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
        # Hospital A: IDs 1-3
        # Hospital B: IDs 4-6
        lab_units_data = [
            {'id': 1, 'name': 'Lab A1', 'hospital_id': 1},
            {'id': 2, 'name': 'Lab A2', 'hospital_id': 1},
            {'id': 3, 'name': 'Lab A3', 'hospital_id': 1},
            {'id': 4, 'name': 'Lab B1', 'hospital_id': 2},
            {'id': 5, 'name': 'Lab B2', 'hospital_id': 2},
            {'id': 6, 'name': 'Lab B3', 'hospital_id': 2}
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
                'roles': ['master_admin', 'admin']  # Both roles for full access to analytics routes
            },
            {
                'username': 'test_admin',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': True,
                'roles': ['admin']  # Admin role for integration tests
            },
            {
                'username': 'test_manager',
                'password': 'Test@2026',
                'hospital_id': 1,
                'is_master_admin': False,
                'roles': ['data_manager'],  # Manager role for integration tests
                'lab_units': ['Lab A1']
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
                'roles': ['ophthalmologist'],
                'lab_units': ['Lab A1']  # Assign lab unit
            },
            {
                'username': 'ophthalmologist_b',
                'password': 'Test@2026',
                'hospital_id': 2,
                'is_master_admin': False,
                'roles': ['ophthalmologist'],
                'lab_units': ['Lab B1']  # Assign lab unit
            },
            {
                'username': 'ophthalmologist_cross',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': False,
                'roles': ['ophthalmologist'],
                'lab_units': ['Lab A1', 'Lab B1']  # Cross-hospital lab units
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
                session.flush()

                # Assign lab units if specified
                if 'lab_units' in user_data:
                    for lab_name in user_data['lab_units']:
                        lab_unit = lab_units.get(lab_name)
                        if lab_unit:
                            user.lab_units.append(lab_unit)
                    session.flush()

            users[user_data['username']] = user

        # ===== SYNC SEQUENCES =====
        # When entities are created with explicit IDs, PostgreSQL sequences
        # don't automatically advance. This causes duplicate key errors when
        # tests create new entities without specifying IDs.
        # Sync all sequences to the max ID currently in the table.
        session.execute(text("SELECT setval('cameras_id_seq', (SELECT COALESCE(MAX(id), 1) FROM cameras))"))
        session.execute(text("SELECT setval('areas_id_seq', (SELECT COALESCE(MAX(id), 1) FROM areas))"))
        session.execute(text("SELECT setval('hospitals_id_seq', (SELECT COALESCE(MAX(id), 1) FROM hospitals))"))
        session.execute(text("SELECT setval('lab_units_id_seq', (SELECT COALESCE(MAX(id), 1) FROM lab_units))"))

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
