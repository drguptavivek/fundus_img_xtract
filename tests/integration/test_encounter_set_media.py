import pytest
import uuid
from models import PatientEncounters, EncounterSetImage, Project, ProjectInvestigator
from encounter_sets.models import ProjectEncounterSetPermission
from tests.helpers.factories import UserFactory
from datetime import date, datetime


def _grant_media_access(db_session, encounter_set_data, user, **capabilities):
    row = ProjectEncounterSetPermission(
        project_id=encounter_set_data["project"].id,
        user_id=user.id,
        lab_unit_id=encounter_set_data["lab_unit"].id,
        active=True,
        **capabilities,
    )
    db_session.add(row)
    db_session.flush()
    return row

@pytest.fixture
def encounter_set_data(db_session, core_test_data):
    """Create a set-based encounter and an image for testing."""
    
    # Create a dummy ZipFile (required by PatientEncounters foreign key, though nullable in newer schema? 
    # Check model: zip_file_id is Mapped[int | None] = mapped_column(ForeignKey('zip_files.id'), unique=True, nullable=True)
    # So we can skip it if nullable. Let's try skipping it.
    
    lab_unit = db_session.merge(core_test_data['lab_unit'])
    project = Project(title="Media Collaborator Project", code="MEDIA-COLLAB", active=True)
    db_session.add(project)
    db_session.flush()
    
    encounter = PatientEncounters(
        uuid=str(uuid.uuid4()),
        name="Test Patient Set",
        patient_id="PAT-SET-001",
        capture_date="2023-10-27",
        capture_date_dt=date(2023, 10, 27),
        lab_unit_id=lab_unit.id,
        project_id=project.id,
        is_set_based=True,
        encounter_verified_status='pending'
    )
    db_session.add(encounter)
    db_session.flush()
    
    image_uuid = str(uuid.uuid4())
    image = EncounterSetImage(
        uuid=image_uuid,
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="test_pos_1.jpg",
        folder_rel="files/test_sets",
        project_id=project.id,
        created_at=datetime.now()
    )
    db_session.add(image)
    db_session.flush()
    
    return {
        'encounter': encounter,
        'image': image,
        'lab_unit': lab_unit,
        'project': project,
    }

def test_access_encounter_set_image_authenticated(client, auth_client_factory, encounter_set_data, db_session):
    """Test accessing an encounter set image with a valid user."""
    # Create a user with required role (e.g., optometrist) and access to the lab unit
    user = UserFactory.create_ophthalmologist(
        db_session, 
        username='test_set_viewer', 
        lab_units=[encounter_set_data['lab_unit']]
    )
    _grant_media_access(db_session, encounter_set_data, user, can_browse=True)
    auth_client = auth_client_factory(user)
    
    # Expect 404 because file doesn't exist on disk, but access is allowed
    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}")
    assert response.status_code == 404

def test_access_encounter_set_image_anonymous(client, encounter_set_data):
    """Test accessing without login should redirect or 401."""
    response = client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}")
    # Flask-Login usually redirects to login page (302) or returns 401 depending on config
    assert response.status_code in [302, 401]

def test_access_encounter_set_image_wrong_role(client, auth_client_factory, encounter_set_data, db_session):
    """Test accessing with a user who doesn't have the required role."""
    from models import Role
    # Create a user with a role not in the allowed list
    role_name = "guest_role_unique"
    role = db_session.query(Role).filter_by(name=role_name).first()
    if not role:
        role = Role(name=role_name)
        db_session.add(role)
        db_session.flush()

    user = UserFactory.create_by_role(db_session, role_name, username="guest_user_unique")
    auth_client = auth_client_factory(user)
    
    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}")
    # Object authorization intentionally hides whether the media UUID exists.
    assert response.status_code == 404


def test_access_encounter_set_thumbnail_project_collaborator(auth_client_factory, encounter_set_data, db_session, monkeypatch, tmp_path):
    user = UserFactory.create_by_role(db_session, "collaborator", username="media_project_collaborator")
    db_session.add(
        ProjectInvestigator(
            project_id=encounter_set_data["project"].id,
            user_id=user.id,
            role="collaborator",
            active=True,
        )
    )
    db_session.commit()
    media_dir = tmp_path / "files" / "test_sets"
    media_dir.mkdir(parents=True)
    (media_dir / "test_pos_1.jpg").write_bytes(b"test image")
    monkeypatch.setattr("utils.utilsImgServe.BASE_DIR", tmp_path)
    auth_client = auth_client_factory(user)

    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}/thumbnail")

    assert response.status_code == 200


def test_access_encounter_set_thumbnail_collaborator_without_project_membership(
    auth_client_factory,
    encounter_set_data,
    db_session,
    monkeypatch,
    tmp_path,
):
    user = UserFactory.create_by_role(db_session, "collaborator", username="media_unassigned_collaborator")
    media_dir = tmp_path / "files" / "test_sets"
    media_dir.mkdir(parents=True)
    (media_dir / "test_pos_1.jpg").write_bytes(b"test image")
    monkeypatch.setattr("utils.utilsImgServe.BASE_DIR", tmp_path)
    auth_client = auth_client_factory(user)

    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}/thumbnail")

    assert response.status_code == 404


def test_access_encounter_set_full_image_collaborator_without_project_membership(
    auth_client_factory,
    encounter_set_data,
    db_session,
    monkeypatch,
    tmp_path,
):
    user = UserFactory.create_by_role(db_session, "collaborator", username="media_unassigned_full_collaborator")
    media_dir = tmp_path / "files" / "test_sets"
    media_dir.mkdir(parents=True)
    (media_dir / "test_pos_1.jpg").write_bytes(b"test image")
    monkeypatch.setattr("utils.utilsImgServe.BASE_DIR", tmp_path)
    auth_client = auth_client_factory(user)

    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}")

    assert response.status_code == 404


def test_access_encounter_set_full_image_project_collaborator(auth_client_factory, encounter_set_data, db_session, monkeypatch, tmp_path):
    user = UserFactory.create_by_role(db_session, "collaborator", username="media_full_image_collaborator")
    db_session.add(
        ProjectInvestigator(
            project_id=encounter_set_data["project"].id,
            user_id=user.id,
            role="collaborator",
            active=True,
        )
    )
    db_session.commit()
    media_dir = tmp_path / "files" / "test_sets"
    media_dir.mkdir(parents=True)
    (media_dir / "test_pos_1.jpg").write_bytes(b"test image")
    monkeypatch.setattr("utils.utilsImgServe.BASE_DIR", tmp_path)
    auth_client = auth_client_factory(user)

    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}")

    assert response.status_code == 200

def test_access_encounter_set_image_not_found(client, auth_client_factory, test_users):
    """Test accessing a non-existent UUID."""
    # Use existing admin user from test_users fixture to avoid unique constraint errors
    admin = test_users['admin']
    auth_client = auth_client_factory(admin)
    random_uuid = str(uuid.uuid4())
    response = auth_client.get(f"/media/encounter_set/img/{random_uuid}")
    assert response.status_code == 404

def test_access_encounter_set_thumbnail_authenticated(client, auth_client_factory, encounter_set_data, db_session):
    """Test accessing thumbnail."""
    user = UserFactory.create_ophthalmologist(
        db_session, 
        username='test_thumb_viewer', 
        lab_units=[encounter_set_data['lab_unit']]
    )
    _grant_media_access(db_session, encounter_set_data, user, can_browse=True)
    auth_client = auth_client_factory(user)
    
    # Expect 404 because file doesn't exist, but route is reachable (not 401/403)
    response = auth_client.get(f"/media/encounter_set/img/{encounter_set_data['image'].uuid}/thumbnail")
    assert response.status_code == 404


def test_universal_thumbnail_serves_encounter_set_image(
    auth_client_factory, encounter_set_data, db_session, monkeypatch, tmp_path
):
    user = UserFactory.create_ophthalmologist(
        db_session,
        username="test_universal_set_thumb_viewer",
        lab_units=[encounter_set_data["lab_unit"]],
    )
    _grant_media_access(db_session, encounter_set_data, user, can_browse=True)
    media_dir = tmp_path / "files" / "test_sets"
    thumbnail_dir = media_dir / "thumbnails"
    thumbnail_dir.mkdir(parents=True)
    thumbnail_name = "thm_test_pos_1.jpg"
    (thumbnail_dir / thumbnail_name).write_bytes(b"thumbnail bytes")
    encounter_set_data["image"].thumbnail_filename = thumbnail_name
    db_session.flush()
    monkeypatch.setattr("utils.utilsImgServe.BASE_DIR", tmp_path)
    auth_client = auth_client_factory(user)

    response = auth_client.get(f"/media/img/{encounter_set_data['image'].uuid}/thumbnail")

    assert response.status_code == 200
    assert response.headers["X-Thumbnail"] == "true"
    assert response.data == b"thumbnail bytes"


def test_encounter_set_media_denies_lab_role_without_project_capability(
    auth_client_factory, encounter_set_data, db_session, monkeypatch, tmp_path
):
    user = UserFactory.create_ophthalmologist(
        db_session,
        username="test_unscoped_set_viewer",
        lab_units=[encounter_set_data["lab_unit"]],
    )
    media_dir = tmp_path / "files" / "test_sets"
    media_dir.mkdir(parents=True)
    (media_dir / "test_pos_1.jpg").write_bytes(b"test image")
    monkeypatch.setattr("utils.utilsImgServe.BASE_DIR", tmp_path)
    auth_client = auth_client_factory(user)

    response = auth_client.get(
        f"/media/encounter_set/img/{encounter_set_data['image'].uuid}"
    )

    assert response.status_code == 404
