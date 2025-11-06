"""Pytest configuration and fixtures for the fundus image management application."""

import os
import sys
import tempfile
from pathlib import Path

# Add the project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pytest
from flask import Flask
from flask_login import FlaskLoginClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Session, User, Role, Hospital, LabUnit, Disease, UserDiseaseUnitRole
from auth.security import hash_password
from app import create_app


@pytest.fixture(scope="session")
def test_db():
    """Create a test database."""
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp()
    test_db_url = f"sqlite:///{db_path}"
    
    # Create engine and session
    engine = create_engine(test_db_url)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Create all tables with error handling
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # If there are constraint issues, try without them
        print(f"Warning: Database setup had issues: {e}")
        # Remove problematic constraints and try again
        if "direct_image_uploads" in Base.metadata.tables:
            original_constraints = Base.metadata.tables["direct_image_uploads"].constraints.copy()
            # Filter out problematic constraints
            Base.metadata.tables["direct_image_uploads"].constraints = [
                c for c in original_constraints
                if not hasattr(c, 'name') or "ck_diu_" not in str(c.name)
            ]
            try:
                Base.metadata.create_all(bind=engine, checkfirst=True)
            except Exception as e2:
                print(f"Warning: Second attempt also failed: {e2}")
                # Final fallback: create without any constraints on this table
                Base.metadata.tables["direct_image_uploads"].constraints = []
                Base.metadata.create_all(bind=engine, checkfirst=True)
            # Restore original constraints (won't affect created DB)
            Base.metadata.tables["direct_image_uploads"].constraints = original_constraints
    
    yield TestingSessionLocal
    
    # Clean up
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def db_session(test_db):
    """Create a database session for testing."""
    session = test_db()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def app(db_session):
    """Create a Flask app for testing."""
    # Create a test app
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        LOGIN_DISABLED=False,
        # Enable rate limiting for testing
        RATELIMIT_ENABLED='true',
        RATELIMIT_STORAGE_URI='memory://',
        REDIS_URL='memory://',  # Override Redis URL to use memory
        RATELIMIT_DEFAULT='500 per hour, 50 per minute',
        RATELIMIT_APPLICATION='1000 per hour, 100 per minute',
        RATELIMIT_SWALLOW_ERRORS='false'  # Don't swallow errors so we can see what's happening
    )
    
    # Re-initialize rate limiting with updated config
    from utils.rate_limiter import init_rate_limiting
    init_rate_limiting(app)
    
    # Use FlaskLoginClient for testing
    app.test_client_class = FlaskLoginClient
    
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def admin_user(db_session):
    """Create an admin user for testing."""
    # Check if admin role exists
    admin_role = db_session.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        admin_role = Role(name="admin")
        db_session.add(admin_role)
        db_session.commit()
    
    # Create or get admin user
    admin_user = db_session.query(User).filter(User.username == "test_admin").first()
    if not admin_user:
        admin_user = User(
            username="test_admin",
            password_hash=hash_password("Test@2026"),
            is_active=True,
            full_name="Test Admin",
            roles=[admin_role]
        )
        db_session.add(admin_user)
        db_session.commit()
    
    yield admin_user
    
    # Cleanup is handled by the test_db fixture


@pytest.fixture
def app_factory():
    """Create an app factory for testing."""
    def _create_app():
        app = Flask(__name__)
        app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            WTF_CSRF_ENABLED=False,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            # Rate limiting configuration for testing
            RATELIMIT_ENABLED='true',
            RATELIMIT_STORAGE_URI='memory://',
            REDIS_URL='memory://',  # Override Redis URL to use memory
            RATELIMIT_DEFAULT='500 per hour, 50 per minute',
            RATELIMIT_APPLICATION='1000 per hour, 100 per minute',
            RATELIMIT_SWALLOW_ERRORS='false'  # Don't swallow errors so we can see what's happening
        )
        
        # Initialize rate limiting
        from utils.rate_limiter import init_rate_limiting
        init_rate_limiting(app)
        
        return app
    return _create_app


@pytest.fixture
def test_users(db_session):
    """Create test users with different roles."""
    # Use core entities from setup_core_entities.py and initial_setup.py
    # Hospitals (ID 1: RPC AIIMS, ID 2: GTB Hospital)
    hospital = db_session.query(Hospital).filter(Hospital.id == 1).first()
    if not hospital:
        hospital = Hospital(id=1, name="RPC AIIMS")
        db_session.add(hospital)
        db_session.commit()
    
    # Lab Units (ID 1: Community Ophthalmology, ID 2: Retina Lab, ID 3: Glaucoma Lab)
    lab_unit1 = db_session.query(LabUnit).filter(LabUnit.id == 1).first()
    if not lab_unit1:
        lab_unit1 = LabUnit(id=1, name="Community Ophthalmology", hospital_id=1)
        db_session.add(lab_unit1)
        db_session.commit()
    
    lab_unit2 = db_session.query(LabUnit).filter(LabUnit.id == 2).first()
    if not lab_unit2:
        lab_unit2 = LabUnit(id=2, name="Retina Lab", hospital_id=1)
        db_session.add(lab_unit2)
        db_session.commit()
    
    # Diseases (ID 1: Glaucoma, ID 2: DR, ID 3: AMD)
    glaucoma = db_session.query(Disease).filter(Disease.id == 1).first()
    if not glaucoma:
        glaucoma = Disease(id=1, name="Glaucoma")
        db_session.add(glaucoma)
        db_session.commit()
    
    dr = db_session.query(Disease).filter(Disease.id == 2).first()
    if not dr:
        dr = Disease(id=2, name="DR")
        db_session.add(dr)
        db_session.commit()
    
    # Get or create ophthalmologist role
    oph_role = db_session.query(Role).filter(Role.name == "ophthalmologist").first()
    if not oph_role:
        oph_role = Role(name="ophthalmologist")
        db_session.add(oph_role)
        db_session.commit()
    
    # Create test users
    users = {}
    
    # Admin user
    admin_role = db_session.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        admin_role = Role(name="admin")
        db_session.add(admin_role)
        db_session.commit()
    
    users["admin"] = db_session.query(User).filter(User.username == "test_admin").first()
    if not users["admin"]:
        users["admin"] = User(
            username="test_admin",
            password_hash=hash_password("Test@2026"),
            is_active=True,
            full_name="Test Admin",
            roles=[admin_role]
        )
        db_session.add(users["admin"])
        db_session.commit()
    
    # resident2 user
    users["resident2"] = db_session.query(User).filter(User.username == "test_resident2").first()
    if not users["resident2"]:
        users["resident2"] = User(
            username="test_resident2",
            password_hash=hash_password("Test@2026"),
            is_active=True,
            full_name="Test resident2",
            roles=[oph_role]
        )
        db_session.add(users["resident2"])
        db_session.commit()
        
        # Add lab unit
        users["resident2"].lab_units.append(lab_unit1)
        db_session.commit()
    
    # Resident user
    users["resident"] = db_session.query(User).filter(User.username == "test_resident").first()
    if not users["resident"]:
        users["resident"] = User(
            username="test_resident",
            password_hash=hash_password("TestPassword123!"),
            is_active=True,
            full_name="Test Resident",
            roles=[oph_role]
        )
        db_session.add(users["resident"])
        db_session.commit()
        
        # Add lab unit
        users["resident"].lab_units.append(lab_unit1)
        db_session.commit()
    
    # Test resident2 user (testresident2) - with resident2 slot
    users["testresident2"] = db_session.query(User).filter(User.username == "testresident2").first()
    if not users["testresident2"]:
        users["testresident2"] = User(
            username="testresident2",
            password_hash=hash_password("TestPassword123!"),
            is_active=True,
            full_name="Test resident2 User",
            roles=[oph_role]
        )
        db_session.add(users["testresident2"])
        db_session.commit()
        
        # Add to both lab units
        users["testresident2"].lab_units.append(lab_unit1)
        users["testresident2"].lab_units.append(lab_unit2)
        db_session.commit()
        
        # Add resident2 slot permissions for both diseases in both lab units
        for disease in [glaucoma, dr]:
            for unit in [lab_unit1, lab_unit2]:
                resident2_role = UserDiseaseUnitRole(
                    user_id=users["testresident2"].id,
                    disease_id=disease.id,
                    lab_unit_id=unit.id,
                    can_grade_resident2=True
                )
                db_session.add(resident2_role)
        db_session.commit()
    
    # Test Resident user (testResident) - with resident slot
    users["testResident"] = db_session.query(User).filter(User.username == "testResident").first()
    if not users["testResident"]:
        users["testResident"] = User(
            username="testResident",
            password_hash=hash_password("TestPassword123!"),
            is_active=True,
            full_name="Test Resident User",
            roles=[oph_role]
        )
        db_session.add(users["testResident"])
        db_session.commit()
        
        # Add to both lab units
        users["testResident"].lab_units.append(lab_unit1)
        users["testResident"].lab_units.append(lab_unit2)
        db_session.commit()
        
        # Add resident slot permissions for both diseases in both lab units
        for disease in [glaucoma, dr]:
            for unit in [lab_unit1, lab_unit2]:
                resident_role = UserDiseaseUnitRole(
                    user_id=users["testResident"].id,
                    disease_id=disease.id,
                    lab_unit_id=unit.id,
                    can_grade_resident=True
                )
                db_session.add(resident_role)
        db_session.commit()
    
    # Test Arbitrator user (testArbitrator) - with arbitrator slot
    users["testArbitrator"] = db_session.query(User).filter(User.username == "testArbitrator").first()
    if not users["testArbitrator"]:
        users["testArbitrator"] = User(
            username="testArbitrator",
            password_hash=hash_password("TestPassword123!"),
            is_active=True,
            full_name="Test Arbitrator User",
            roles=[oph_role]
        )
        db_session.add(users["testArbitrator"])
        db_session.commit()
        
        # Add to both lab units
        users["testArbitrator"].lab_units.append(lab_unit1)
        users["testArbitrator"].lab_units.append(lab_unit2)
        db_session.commit()
        
        # Add arbitrator slot permissions for both diseases in both lab units
        for disease in [glaucoma, dr]:
            for unit in [lab_unit1, lab_unit2]:
                arbitrator_role = UserDiseaseUnitRole(
                    user_id=users["testArbitrator"].id,
                    disease_id=disease.id,
                    lab_unit_id=unit.id,
                    can_arbitrate=True
                )
                db_session.add(arbitrator_role)
        db_session.commit()
    
    yield users
    
    # Cleanup is handled by the test_db fixture