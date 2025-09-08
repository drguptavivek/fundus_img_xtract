# tests/test_api_gradings.py
import pytest
from flask import Flask
from flask.testing import FlaskClient
from unittest.mock import patch
from uuid import uuid4

from app import create_app
from models import Session, User, EncounterFile, DirectImageUpload, ImageGrading, Role, Disease, Hospital, LabUnit, Camera, Area, ZipFile, PatientEncounters
from sqlalchemy import select
from auth.roles import DEFAULT_ROLES

@pytest.fixture(scope='module')
def app():
    """Create and configure a new app instance for each test module."""
    app = create_app()
    app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "SESSION_COOKIE_SECURE": False,
        "SESSION_PROTECTION": None,
    })
    with app.app_context():
        from models import Base, engine
        Base.metadata.create_all(engine)
        # Seed roles
        with Session() as db:
            for role_name in DEFAULT_ROLES:
                if not db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none():
                    db.add(Role(name=role_name))
            db.commit()
    yield app

@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """A test client for the app."""
    return app.test_client()

@pytest.fixture
def db_session(app: Flask):
    """Creates a new database session for a test."""
    with app.app_context():
        with Session() as session:
            yield session
            session.rollback() # Rollback any changes made during the test

def test_get_gradings_by_image_uuid_encounter_file(client: FlaskClient, db_session):
    """Test getting gradings for an image associated with an EncounterFile."""
    # 1. Create mock data
    test_uuid = str(uuid4())
    
    # Grader
    grader = db_session.execute(select(User).filter_by(username="testgrader")).scalar_one_or_none()
    if not grader:
        grader = User(username="testgrader", password_hash="hash")
        db_session.add(grader)
        db_session.commit()

    # Supporting entities
    zip_file = ZipFile(zip_filename=f"test_zip_{str(uuid4())}.zip", md5_hash=str(uuid4()))
    db_session.add(zip_file)
    db_session.commit()

    patient_encounter = PatientEncounters(
        zip_file_id=zip_file.id,
        name="Test Patient",
        patient_id="P123",
        capture_date="2023-01-01"
    )
    db_session.add(patient_encounter)
    db_session.commit()

    # EncounterFile
    encounter_file = EncounterFile(
        patient_encounter_id=patient_encounter.id,
        uuid=test_uuid,
        filename="test.jpg",
        file_type="image"
    )
    db_session.add(encounter_file)
    db_session.commit()

    # Gradings
    grading1 = ImageGrading(encounter_file_id=encounter_file.id, grader_user_id=grader.id, graded_for="Glaucoma", impression="Mild")
    grading2 = ImageGrading(encounter_file_id=encounter_file.id, grader_user_id=grader.id, graded_for="DR", impression="Severe")
    db_session.add_all([grading1, grading2])
    db_session.commit()

    # 2. Mock login and make request
    with patch('flask_login.utils._get_user') as _get_user:
        mock_user = User(id=1, username='testadmin', password_hash='hash')
        mock_user.roles = [Role(name='admin')]
        _get_user.return_value = mock_user

        response = client.get(f'/api/gradings/by-image-uuid/{test_uuid}')

    # 3. Assert response
    assert response.status_code == 200
    data = response.json
    assert isinstance(data, list)
    assert len(data) == 2
    assert data[0]['impression'] == 'Severe' # Sorted by updated_at desc
    assert data[1]['impression'] == 'Mild'
    assert data[0]['grader_username'] == 'testgrader'

def test_get_gradings_by_image_uuid_direct_upload(client: FlaskClient, db_session):
    """Test getting gradings for an image associated with a DirectImageUpload."""
    # 1. Create mock data
    test_uuid = str(uuid4())
    
    # Grader
    grader = db_session.execute(select(User).filter_by(username="testgrader2")).scalar_one_or_none()
    if not grader:
        grader = User(username="testgrader2", password_hash="hash")
        db_session.add(grader)
        db_session.commit()

    # Supporting entities for DirectImageUpload
    hospital = db_session.execute(select(Hospital).filter_by(name="Test Hospital")).scalar_one_or_none()
    if not hospital:
        hospital = Hospital(name="Test Hospital")
        db_session.add(hospital)
        db_session.flush()

    lab_unit = db_session.execute(select(LabUnit).filter_by(name="Test Lab")).scalar_one_or_none()
    if not lab_unit:
        lab_unit = LabUnit(name="Test Lab", hospital=hospital)
        db_session.add(lab_unit)
        db_session.flush()

    camera = db_session.execute(select(Camera).filter_by(name="Test Camera")).scalar_one_or_none()
    if not camera:
        camera = Camera(name="Test Camera")
        db_session.add(camera)
        db_session.flush()

    disease = db_session.execute(select(Disease).filter_by(name="Test Disease")).scalar_one_or_none()
    if not disease:
        disease = Disease(name="Test Disease")
        db_session.add(disease)
        db_session.flush()

    area = db_session.execute(select(Area).filter_by(name="Test Area")).scalar_one_or_none()
    if not area:
        area = Area(name="Test Area")
        db_session.add(area)
        db_session.flush()

    uploader = db_session.execute(select(User).filter_by(username="uploader")).scalar_one_or_none()
    if not uploader:
        uploader = User(username="uploader", password_hash="hash")
        db_session.add(uploader)
        db_session.flush()
    db_session.commit()

    # DirectImageUpload
    direct_upload = DirectImageUpload(
        uuid=test_uuid, filename="test_direct.jpg", folder_rel="test", file_hash=str(uuid4()),
        uploader_id=uploader.id, hospital_id=hospital.id, lab_unit_id=lab_unit.id,
        camera_id=camera.id, disease_id=disease.id, area_id=area.id
    )
    db_session.add(direct_upload)
    db_session.commit()

    # Gradings
    grading1 = ImageGrading(direct_image_upload_id=direct_upload.id, grader_user_id=grader.id, graded_for="AMD", impression="Dry")
    db_session.add(grading1)
    db_session.commit()

    # 2. Mock login and make request
    with patch('flask_login.utils._get_user') as _get_user:
        mock_user = User(id=1, username='testadmin', password_hash='hash')
        mock_user.roles = [Role(name='admin')]
        _get_user.return_value = mock_user

        response = client.get(f'/api/gradings/by-image-uuid/{test_uuid}')

    # 3. Assert response
    assert response.status_code == 200
    data = response.json
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]['impression'] == 'Dry'
    assert data[0]['grader_username'] == 'testgrader2'

def test_get_gradings_by_image_uuid_not_found(client: FlaskClient, db_session):
    """Test getting gradings for a non-existent image UUID."""
    non_existent_uuid = str(uuid4())
    
    with patch('flask_login.utils._get_user') as _get_user:
        mock_user = User(id=1, username='testadmin', password_hash='hash')
        mock_user.roles = [Role(name='admin')]
        _get_user.return_value = mock_user

        response = client.get(f'/api/gradings/by-image-uuid/{non_existent_uuid}')

    assert response.status_code == 404
    data = response.json
    assert data['error'] == 'Image not found'
