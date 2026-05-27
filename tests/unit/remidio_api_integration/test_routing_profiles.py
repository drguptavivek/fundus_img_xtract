from contextlib import contextmanager
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from encounter_set_types.models import EncounterSetType
from models import Disease, EncounterSetImage, Project, RemidioConnection, RemidioSite
from remidio_api_integration import service
from remidio_api_integration.errors import RemidioConfigError
from remidio_api_integration.routing import upsert_routing_profile, upsert_routing_profile_route
from upload_profiles.models import (
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE, UPLOAD_KIND_ENCOUNTER_SET


class FakeRemidioClient:
    def __init__(self, secrets):
        self.secrets = secrets

    def get_exams_by_date(self, *, start_date, end_date, site_custom_identifier, include_file_paths=False):
        assert include_file_paths is True
        return {
            "status": {"statusCode": "OK"},
            "data": [
                {
                    "patientDetails": {
                        "id": 6547105862647808,
                        "mrn": "MRN-1",
                        "siteId": 5504695309172736,
                    },
                    "examDetails": {
                        "id": 4613839312125952,
                        "localId": "REM-1",
                        "examDate": 1775022627123,
                        "examState": "ACTIVE",
                        "deviceType": ["PRISTINE"],
                    },
                    "images": {
                        "pristineImages": {
                            "STANDARD": [
                                {
                                    "id": 6396051191758848,
                                    "deviceType": "PRISTINE",
                                    "path": "https://files.example.test/image-1.jpg",
                                }
                            ]
                        }
                    },
                    "doctorReport": {
                        "id": 4523900784345088,
                        "path": "https://files.example.test/report-1.pdf",
                    },
                }
            ],
        }

    def download_file(self, file_url, *, max_bytes):
        if file_url.endswith(".pdf"):
            return b"%PDF-1.4\n%test\n", "application/pdf"
        image = Image.new("RGB", (16, 16), color=(0, 255, 0))
        output = BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue(), "image/jpeg"


def test_routing_profile_route_requires_same_project_automated_profile(db_session, core_test_data):
    project_a = _project(db_session, "A")
    project_b = _project(db_session, "B")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project_b, core_test_data)

    routing_profile = upsert_routing_profile(
        db_session,
        {"project_id": project_a.id, "name": f"Route {uuid4()}", "active": True},
    )

    with pytest.raises(RemidioConfigError, match="routing profile project"):
        upsert_routing_profile_route(
            db_session,
            {
                "routing_profile_id": routing_profile.id,
                "remidio_connection_id": connection.id,
                "site_custom_identifier": "rpc_test",
                "remidio_device_type": "PRISTINE",
                "project_upload_profile_id": automated_mapping.id,
                "lab_unit_id": core_test_data["lab_unit"].id,
                "camera_id": core_test_data["camera"].id,
                "active_from_date": "2026-01-01",
            },
        )

    manual_mapping = _manual_project_profile(db_session, project_a)
    with pytest.raises(RemidioConfigError, match="automated Remidio-populated"):
        upsert_routing_profile_route(
            db_session,
            {
                "routing_profile_id": routing_profile.id,
                "remidio_connection_id": connection.id,
                "site_custom_identifier": "rpc_test",
                "remidio_device_type": "PRISTINE",
                "project_upload_profile_id": manual_mapping.id,
                "lab_unit_id": core_test_data["lab_unit"].id,
                "camera_id": core_test_data["camera"].id,
                "active_from_date": "2026-01-01",
            },
        )


def test_routing_profile_route_prefers_synced_site_custom_identifier(db_session, core_test_data):
    project = _project(db_session, "SITE")
    connection = _connection(db_session)
    site = RemidioSite(
        remidio_connection_id=connection.id,
        remidio_site_id=5504695309172736,
        site_name="Synced Site",
        site_custom_identifier="rpc_from_site",
        active=True,
    )
    db_session.add(site)
    db_session.flush()
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    routing_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route {uuid4()}", "active": True},
    )

    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "remidio_site_id": site.id,
            "site_custom_identifier": "stale_form_value",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    assert route.source_rule.site_custom_identifier == "rpc_from_site"


def test_routing_profile_sync_fetches_and_saves_scoped_encounter_set(db_session, core_test_data, tmp_path, monkeypatch):
    from remidio_api_integration import ingest as ingest_module

    monkeypatch.setattr(ingest_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(service, "RemidioClient", FakeRemidioClient)
    monkeypatch.setattr(service, "_secrets", lambda connection: None)
    monkeypatch.setattr(service, "get_db_session", _session_context(db_session))

    project = _project(db_session, "SYNC")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    routing_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route {uuid4()}", "active": True},
    )
    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_test",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    result = service._run_routing_profile_sync_payload(
        {
            "routing_profile_id": routing_profile.id,
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "limit": 10,
            "route_ids": [route.id],
        }
    )

    assert result["groups"][0]["pull"]["summary"]["exams_created"] == 1
    assert result["groups"][0]["ingest"]["summary"]["images_downloaded"] == 1
    assert result["groups"][0]["ingest"]["summary"]["reports_downloaded"] == 1
    image = db_session.query(EncounterSetImage).one()
    assert image.project_id == project.id
    assert image.camera_id == core_test_data["camera"].id
    assert (tmp_path / image.folder_rel / image.original_filename).exists()


def _project(db_session, suffix: str) -> Project:
    project = Project(title=f"Remidio Routing {suffix} {uuid4()}", code=f"RR{suffix}{uuid4().hex[:8]}", active=True)
    db_session.add(project)
    db_session.flush()
    return project


def _connection(db_session) -> RemidioConnection:
    connection = RemidioConnection(
        name=f"Remidio Test {uuid4()}",
        base_url="https://example.test",
        client_name="PACS_GATEWAY",
        client_identification_token_encrypted="encrypted",
        email_encrypted="encrypted",
        password_encrypted="encrypted",
        secret_salt="a" * 64,
        active=True,
    )
    db_session.add(connection)
    db_session.flush()
    return connection


def _automated_project_profile(db_session, project: Project, core_test_data) -> ProjectUploadProfile:
    encounter_scheme = Disease(name=f"Remidio Encounter Scheme {uuid4()}", grading_scope="encounter")
    encounter_set_type = db_session.query(EncounterSetType).filter_by(code="remidio_api_standard").one_or_none()
    if encounter_set_type is None:
        encounter_set_type = EncounterSetType(
            name=f"Remidio API Standard {uuid4()}",
            code="remidio_api_standard",
            metadata_schema_json={"fields": []},
            active=True,
        )
    upload_profile = UploadProfile(
        name=f"Automated Remidio API Profile {uuid4()}",
        automated_remidio_populated=True,
        allow_mydriatic=False,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
        active=True,
    )
    upload_profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_ENCOUNTER_SET))
    upload_profile.encounter_set_types.append(
        UploadProfileEncounterSetType(
            encounter_set_type=encounter_set_type,
            encounter_grading_scheme=encounter_scheme,
            default_image_grading_scheme_id=core_test_data["dr"].id,
            active=True,
            image_grading_schemes=[
                UploadProfileEncounterSetTypeImageGradingScheme(
                    disease_id=core_test_data["dr"].id,
                    is_default=True,
                    display_order=1,
                    active=True,
                )
            ],
        )
    )
    mapping = ProjectUploadProfile(project=project, profile=upload_profile, active=True)
    db_session.add_all([encounter_scheme, encounter_set_type, upload_profile, mapping])
    db_session.flush()
    return mapping


def _session_context(db_session):
    class Wrapper:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def commit(self):
            db_session.flush()

    @contextmanager
    def _ctx():
        yield Wrapper()

    return _ctx


def _manual_project_profile(db_session, project: Project) -> ProjectUploadProfile:
    upload_profile = UploadProfile(
        name=f"Manual Profile {uuid4()}",
        automated_remidio_populated=False,
        active=True,
    )
    upload_profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    mapping = ProjectUploadProfile(project=project, profile=upload_profile, active=True)
    db_session.add_all([upload_profile, mapping])
    db_session.flush()
    return mapping
