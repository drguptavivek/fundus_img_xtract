"""
Test database seeding - adds test-specific entities on top of migrated data.

This module provides a session-scoped fixture that runs AFTER Alembic migrations
to add test-specific entities:

Core entities (seeded by migrations):
- Production hospitals (RPC AIIMS, UCMS GTB Hosp)
- Production lab units (Community Ophthalmology, Retina Lab, etc.)
- Diseases (Glaucoma, DR, AMD) with gradings and features
- Areas, Cameras, etc.

Test-specific entities (added by this fixture):
- Test hospitals (Hospital A, Hospital B) - IDs 100-101
- Test lab units (Lab A1-A3, Lab B1-B3) - IDs 100-105
- AI Models (GlaucomaNet, DRNet)
- Test users (master_admin, site_admin_a/b, ophthalmologists, etc.)
- Roles

Note: Tests should query by NAME instead of ID to be resilient to ID changes.
Example: db_session.query(LabUnit).filter_by(name='Lab A1').first()
"""
import pytest
from sqlalchemy import text
from models import (
    Role, Disease, Camera, Area, Hospital, LabUnit, User,
    DiseaseGrading, GradingsFeatures, AIModel
)
from auth.security import hash_password


@pytest.fixture(scope="session", autouse=True)
def seed_test_database(test_engine):
    """
    Seed the test database with test-specific entities.

    This fixture runs automatically AFTER Alembic migrations to add
    test-specific data on top of the core seeded entities.

    Core entities (hospitals, diseases, gradings, cameras, areas) are
    already seeded by migration 691d42ba3fff_seed_core_entities_data.py.
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
                session.flush()
            roles[role_name] = role

        # ===== TEST HOSPITALS (high IDs to avoid conflict with production) =====
        # Production uses IDs 1-2, so tests use 100-101
        # If there are name collisions with seeded data, delete the seeded entity first
        test_hospitals_data = [
            {'id': 100, 'name': 'Hospital A'},
            {'id': 101, 'name': 'Hospital B'}
        ]
        test_hospitals = {}
        for hosp_data in test_hospitals_data:
            # Check for name collision with seeded entities
            existing = session.query(Hospital).filter_by(name=hosp_data['name']).first()
            if existing:
                # Delete the seeded entity so test-specific one wins
                session.delete(existing)
                session.flush()

            hospital = session.query(Hospital).filter_by(id=hosp_data['id']).first()
            if not hospital:
                hospital = Hospital(**hosp_data)
                session.add(hospital)
                session.flush()
            test_hospitals[hosp_data['name']] = hospital
        session.flush()

        # ===== TEST LAB UNITS (high IDs to avoid conflict with production) =====
        # Production uses IDs 1-4, so tests use 100-105
        # If there are name collisions with seeded data, delete the seeded entity first
        test_lab_units_data = [
            {'id': 100, 'name': 'Lab A1', 'hospital_id': 100},
            {'id': 101, 'name': 'Lab A2', 'hospital_id': 100},
            {'id': 102, 'name': 'Lab A3', 'hospital_id': 100},
            {'id': 103, 'name': 'Lab B1', 'hospital_id': 101},
            {'id': 104, 'name': 'Lab B2', 'hospital_id': 101},
            {'id': 105, 'name': 'Lab B3', 'hospital_id': 101}
        ]
        test_lab_units = {}
        for lab_data in test_lab_units_data:
            # Check for name collision with seeded entities
            existing = session.query(LabUnit).filter_by(name=lab_data['name']).first()
            if existing:
                # Delete the seeded entity so test-specific one wins
                session.delete(existing)
                session.flush()

            lab_unit = session.query(LabUnit).filter_by(id=lab_data['id']).first()
            if not lab_unit:
                lab_unit = LabUnit(**lab_data)
                session.add(lab_unit)
                session.flush()
            test_lab_units[lab_data['name']] = lab_unit
        session.flush()

        # ===== AI MODELS =====
        # If there are name collisions with seeded data, delete the seeded entity first
        ai_models_data = [
            {'id': 1, 'name': 'GlaucomaNet', 'version': '1.0',
             'description': 'Deep learning model for glaucoma detection'},
            {'id': 2, 'name': 'DRNet', 'version': '2.0',
             'description': 'Deep learning model for diabetic retinopathy grading'},
        ]
        ai_models = {}
        for model_data in ai_models_data:
            # Check for name collision with seeded entities
            existing = session.query(AIModel).filter_by(name=model_data['name']).first()
            if existing:
                # Delete the seeded entity so test-specific one wins
                session.delete(existing)
                session.flush()

            ai_model = session.query(AIModel).filter_by(id=model_data['id']).first()
            if not ai_model:
                ai_model = AIModel(
                    id=model_data['id'],
                    name=model_data['name'],
                    version=model_data['version'],
                    description=model_data['description']
                )
                session.add(ai_model)
                session.flush()
            ai_models[model_data['name']] = ai_model
        session.flush()

        # ===== AI SYSTEM USER =====
        ai_system_user = session.query(User).filter_by(username='ai_system').first()
        if not ai_system_user:
            ai_system_user = User(
                username='ai_system',
                password_hash=hash_password('AI@2026'),
                is_active=True,
                full_name='AI Grading System'
            )
            session.add(ai_system_user)
            session.flush()

        # ===== TEST USERS =====
        users_data = [
            {
                'username': 'master_admin',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': True,
                'roles': ['master_admin', 'admin']
            },
            {
                'username': 'test_admin',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': True,
                'roles': ['admin']
            },
            {
                'username': 'test_manager',
                'password': 'Test@2026',
                'hospital_id': 100,
                'is_master_admin': False,
                'roles': ['data_manager'],
                'lab_units': ['Lab A1']
            },
            {
                'username': 'site_admin_a',
                'password': 'Test@2026',
                'hospital_id': 100,
                'is_master_admin': False,
                'roles': ['local_admin']
            },
            {
                'username': 'site_admin_b',
                'password': 'Test@2026',
                'hospital_id': 101,
                'is_master_admin': False,
                'roles': ['local_admin']
            },
            {
                'username': 'ophthalmologist_a',
                'password': 'Test@2026',
                'hospital_id': 100,
                'is_master_admin': False,
                'roles': ['ophthalmologist'],
                'lab_units': ['Lab A1']
            },
            {
                'username': 'ophthalmologist_b',
                'password': 'Test@2026',
                'hospital_id': 101,
                'is_master_admin': False,
                'roles': ['ophthalmologist'],
                'lab_units': ['Lab B1']
            },
            {
                'username': 'ophthalmologist_cross',
                'password': 'Test@2026',
                'hospital_id': None,
                'is_master_admin': False,
                'roles': ['ophthalmologist'],
                'lab_units': ['Lab A1', 'Lab B1']
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

                if 'lab_units' in user_data:
                    for lab_name in user_data['lab_units']:
                        lab_unit = test_lab_units.get(lab_name)
                        if lab_unit:
                            user.lab_units.append(lab_unit)
                    session.flush()

            users[user_data['username']] = user

        # ===== SYNC SEQUENCES FOR TEST TABLES =====
        session.execute(text("SELECT setval('ai_models_id_seq', (SELECT COALESCE(MAX(id), 1) FROM ai_models))"))

        session.commit()

        return {
            'roles': roles,
            'test_hospitals': test_hospitals,
            'test_lab_units': test_lab_units,
            'users': users,
            'ai_models': ai_models,
        }

    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()
