from contextlib import contextmanager
from datetime import date
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from encounter_set_types.models import EncounterSetType
from models import Disease, EncounterSetImage, JobItem, PatientEncounters, Project, RemidioConnection, RemidioExam, RemidioSite, Role, User
from project_configuration.models import ProjectLabUnit
from remidio_api_integration import service
from remidio_api_integration.errors import RemidioConfigError, RemidioRemoteError
from remidio_api_integration.models import RemidioApiExamEncounter, RemidioApiSourceRule
from remidio_api_integration.routing import (
    delete_routing_profile_route,
    set_routing_profile_route_active,
    upsert_routing_profile,
    upsert_routing_profile_route,
)
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

    def download_file(self, file_url, *, max_bytes, context=None):
        if file_url.endswith(".pdf"):
            return b"%PDF-1.4\n%test\n", "application/pdf"
        image = Image.new("RGB", (16, 16), color=(0, 255, 0))
        output = BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue(), "image/jpeg"


class PartiallyFailingRemidioClient(FakeRemidioClient):
    def get_exams_by_date(self, *, start_date, end_date, site_custom_identifier, include_file_paths=False):
        if site_custom_identifier == "rpc_bad":
            raise RemidioRemoteError(
                "The Site Custom ID provided cannot be found for your organisation",
                remote_status_code=404,
                response_snapshot={
                    "method": "GET",
                    "path": f"/api/gateway/getExamsByDate/{start_date}/{end_date}/{site_custom_identifier}",
                    "status_code": 404,
                },
            )
        return super().get_exams_by_date(
            start_date=start_date,
            end_date=end_date,
            site_custom_identifier=site_custom_identifier,
            include_file_paths=include_file_paths,
        )


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


def test_routing_profile_route_reuses_existing_active_source_rule(db_session, core_test_data):
    project = _project(db_session, "EXISTING")
    connection = _connection(db_session)
    existing_rule = RemidioApiSourceRule(
        remidio_connection_id=connection.id,
        site_custom_identifier="rpc_existing",
        remidio_device_type="PRISTINE",
        active=True,
    )
    db_session.add(existing_rule)
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
            "site_custom_identifier": "rpc_existing",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    assert route.remidio_api_source_rule_id == existing_rule.id
    assert db_session.query(RemidioApiSourceRule).filter_by(site_custom_identifier="rpc_existing").count() == 1


def test_deactivating_routing_profile_frees_source_route_window(db_session, core_test_data):
    project = _project(db_session, "MOVE")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    first_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route A {uuid4()}", "active": True},
    )
    first_route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": first_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_move",
            "remidio_device_type": "FOP",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    upsert_routing_profile(
        db_session,
        {
            "id": first_profile.id,
            "project_id": project.id,
            "name": first_profile.name,
            "active": False,
        },
    )
    db_session.refresh(first_route)
    second_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route B {uuid4()}", "active": True},
    )
    second_route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": second_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_move",
            "remidio_device_type": "FOP",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    assert first_route.active is False
    assert first_route.active_to_date is not None
    assert second_route.active is True
    assert second_route.remidio_api_source_rule_id == first_route.remidio_api_source_rule_id


def test_route_status_action_frees_source_route_window(db_session, core_test_data):
    project = _project(db_session, "ROUTESTATUS")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    first_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route Status A {uuid4()}", "active": True},
    )
    first_route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": first_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_route_status",
            "remidio_device_type": "FOP",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    set_routing_profile_route_active(db_session, first_route.id, active=False)
    db_session.refresh(first_route)
    second_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route Status B {uuid4()}", "active": True},
    )
    second_route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": second_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_route_status",
            "remidio_device_type": "FOP",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )

    assert first_route.active is False
    assert first_route.active_to_date is not None
    assert second_route.active is True


def test_delete_route_with_linked_encounter_deactivates_instead(db_session, core_test_data):
    project = _project(db_session, "ROUTEDELETE")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    routing_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route Delete {uuid4()}", "active": True},
    )
    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_route_delete",
            "remidio_device_type": "FOP",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )
    encounter = PatientEncounters(
        name="Route Delete Patient",
        patient_id=f"RD-{uuid4()}",
        capture_date="2026-04-01",
        capture_date_dt=date(2026, 4, 1),
        is_set_based=True,
        lab_unit_id=core_test_data["lab_unit"].id,
        project_id=project.id,
        upload_profile_id=automated_mapping.upload_profile_id,
    )
    exam = RemidioExam(
        remidio_connection_id=connection.id,
        patient_encounter=encounter,
        remidio_exam_id=f"exam-{uuid4()}",
        site_custom_identifier="rpc_route_delete",
        device_types=["FOP"],
        pull_source="test",
    )
    db_session.add_all([encounter, exam])
    db_session.flush()
    db_session.add(
        RemidioApiExamEncounter(
            remidio_exam_id=exam.id,
            patient_encounter_id=encounter.id,
            project_upload_profile_id=route.project_upload_profile_id,
            remidio_api_binding_id=route.id,
        )
    )
    db_session.flush()

    result = delete_routing_profile_route(db_session, route.id)
    db_session.refresh(route)

    assert result == "deactivated"
    assert route.active is False
    assert route.active_to_date is not None


def test_delete_route_without_linked_encounter_removes_route(db_session, core_test_data):
    project = _project(db_session, "ROUTEREMOVE")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    routing_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route Remove {uuid4()}", "active": True},
    )
    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_route_remove",
            "remidio_device_type": "FOP",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )
    route_id = route.id

    result = delete_routing_profile_route(db_session, route_id)

    assert result == "deleted"
    assert db_session.get(type(route), route_id) is None


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


def test_routing_profile_worker_reauthorizes_actor_and_exact_lineage(
    db_session,
    core_test_data,
):
    project = _project(db_session, "WORKER_AUTH")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(
        db_session, project, core_test_data
    )
    routing_profile = upsert_routing_profile(
        db_session,
        {
            "project_id": project.id,
            "name": f"Worker auth {uuid4()}",
            "active": True,
        },
    )
    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_worker_auth",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )
    admin_role = db_session.query(Role).filter_by(name="admin").one_or_none()
    if admin_role is None:
        admin_role = Role(name="admin")
        db_session.add(admin_role)
        db_session.flush()
    actor = User(
        username="routing_worker_admin",
        password_hash="x",
        is_active=True,
        roles=[admin_role],
    )
    db_session.add(actor)
    db_session.flush()
    job = SimpleNamespace(
        uploader_user_id=actor.id,
        project_id=project.id,
    )
    item = SimpleNamespace(source_id=routing_profile.id)
    payload = {
        "routing_profile_id": routing_profile.id,
        "route_ids": [route.id],
    }

    service._reauthorize_routing_profile_sync_job(
        db_session,
        job=job,
        item=item,
        payload=payload,
        expected_user_id=actor.id,
    )
    with pytest.raises(RemidioConfigError, match="does not match"):
        service._reauthorize_routing_profile_sync_job(
            db_session,
            job=job,
            item=item,
            payload=payload,
            expected_user_id=actor.id + 1,
        )

    actor.is_active = False
    db_session.flush()
    with pytest.raises(RemidioConfigError, match="Admin authority"):
        service._reauthorize_routing_profile_sync_job(
            db_session,
            job=job,
            item=item,
            payload=payload,
            expected_user_id=actor.id,
        )


def test_routing_profile_worker_denies_any_incomplete_or_foreign_selected_route(
    db_session,
    core_test_data,
):
    project = _project(db_session, "WORKER_ROUTE_LINEAGE")
    connection = _connection(db_session)
    project_profile = _automated_project_profile(
        db_session, project, core_test_data
    )
    routing_profile = upsert_routing_profile(
        db_session,
        {
            "project_id": project.id,
            "name": f"Worker lineage {uuid4()}",
            "active": True,
        },
    )
    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_worker_lineage",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": project_profile.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )
    admin_role = db_session.query(Role).filter_by(name="admin").one()
    actor = User(
        username=f"routing_lineage_admin_{uuid4().hex[:8]}",
        password_hash="x",
        is_active=True,
        roles=[admin_role],
    )
    db_session.add(actor)
    db_session.flush()
    job = SimpleNamespace(uploader_user_id=actor.id, project_id=project.id)
    item = SimpleNamespace(source_id=routing_profile.id)

    def reauthorize(route_ids):
        return service._reauthorize_routing_profile_sync_job(
            db_session,
            job=job,
            item=item,
            payload={
                "routing_profile_id": routing_profile.id,
                "route_ids": route_ids,
            },
            expected_user_id=actor.id,
        )

    reauthorize([route.id])
    with pytest.raises(RemidioConfigError, match="Every selected"):
        reauthorize([route.id, route.id + 999_999])

    project_profile.active = False
    db_session.flush()
    with pytest.raises(RemidioConfigError, match="Every selected"):
        reauthorize([route.id])
    project_profile.active = True

    project_profile.profile.active = False
    db_session.flush()
    with pytest.raises(RemidioConfigError, match="Every selected"):
        reauthorize([route.id])
    project_profile.profile.active = True

    project.active = False
    db_session.flush()
    with pytest.raises(RemidioConfigError, match="inactive"):
        reauthorize([route.id])
    project.active = True

    project_lab = db_session.query(ProjectLabUnit).filter_by(
        project_id=project.id,
        lab_unit_id=route.lab_unit_id,
    ).one()
    project_lab.active = False
    db_session.flush()
    with pytest.raises(RemidioConfigError, match="Every selected"):
        reauthorize([route.id])


def test_routing_profile_job_persists_exact_validated_route_ids(
    db_session,
    core_test_data,
):
    project = _project(db_session, "QUEUED_ROUTE_FACTS")
    connection = _connection(db_session)
    project_profile = _automated_project_profile(
        db_session, project, core_test_data
    )
    routing_profile = upsert_routing_profile(
        db_session,
        {
            "project_id": project.id,
            "name": f"Queued route facts {uuid4()}",
            "active": True,
        },
    )
    route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_queued_route_facts",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": project_profile.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )
    admin_role = db_session.query(Role).filter_by(name="admin").one()
    actor = User(
        username=f"routing_queue_admin_{uuid4().hex[:8]}",
        password_hash="x",
        is_active=True,
        roles=[admin_role],
    )
    db_session.add(actor)
    db_session.flush()

    result = service.create_routing_profile_sync_job(
        db_session,
        routing_profile_id=routing_profile.id,
        payload={
            "start_date": "2026-04-01",
            "end_date": "2026-04-02",
        },
        requested_by_user_id=actor.id,
        requested_by_username=actor.username,
    )
    item = db_session.get(JobItem, result["job_item_id"])
    assert item is not None
    assert service._job_item_payload(item)["route_ids"] == [route.id]

    with pytest.raises(RemidioConfigError, match="Every selected"):
        service.create_routing_profile_sync_job(
            db_session,
            routing_profile_id=routing_profile.id,
            payload={
                "start_date": "2026-04-01",
                "end_date": "2026-04-02",
                "route_ids": [route.id, route.id + 999_999],
            },
            requested_by_user_id=actor.id,
            requested_by_username=actor.username,
        )


def test_routing_profile_sync_continues_after_bad_site_identifier(db_session, core_test_data, tmp_path, monkeypatch):
    from remidio_api_integration import ingest as ingest_module

    monkeypatch.setattr(ingest_module, "BASE_DIR", tmp_path)
    monkeypatch.setattr(service, "RemidioClient", PartiallyFailingRemidioClient)
    monkeypatch.setattr(service, "_secrets", lambda connection: None)
    monkeypatch.setattr(service, "get_db_session", _session_context(db_session))

    project = _project(db_session, "PARTIAL")
    connection = _connection(db_session)
    automated_mapping = _automated_project_profile(db_session, project, core_test_data)
    routing_profile = upsert_routing_profile(
        db_session,
        {"project_id": project.id, "name": f"Route {uuid4()}", "active": True},
    )
    bad_route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_bad",
            "remidio_device_type": "PRISTINE",
            "project_upload_profile_id": automated_mapping.id,
            "lab_unit_id": core_test_data["lab_unit"].id,
            "camera_id": core_test_data["camera"].id,
            "active_from_date": "2026-01-01",
        },
    )
    good_route = upsert_routing_profile_route(
        db_session,
        {
            "routing_profile_id": routing_profile.id,
            "remidio_connection_id": connection.id,
            "site_custom_identifier": "rpc_good",
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
            "route_ids": [bad_route.id, good_route.id],
        }
    )

    assert [group["site_custom_identifier"] for group in result["groups"]] == ["rpc_bad", "rpc_good"]
    assert result["groups"][0]["status"] == "failed"
    assert result["groups"][0]["ingest"]["summary"]["route_errors"] == 1
    assert result["groups"][1]["status"] == "completed"
    assert result["groups"][1]["pull"]["summary"]["exams_created"] == 1
    assert result["groups"][1]["ingest"]["summary"]["images_downloaded"] == 1
    assert db_session.query(EncounterSetImage).count() == 1

    payload = {
        "routing_profile_id": routing_profile.id,
        "start_date": "2026-04-01",
        "end_date": "2026-04-30",
    }
    route_groups = service._project_sync_route_group_details(payload, result, item_id=123, item_state="completed")
    assert [group["status"] for group in route_groups] == ["failed", "completed"]
    assert route_groups[0]["site_custom_identifier"] == "rpc_bad"
    assert route_groups[0]["error"] == "The Site Custom ID provided cannot be found for your organisation"
    assert route_groups[0]["remote_status_code"] == 404
    assert route_groups[0]["ingest_summary"]["route_errors"] == 1
    assert route_groups[1]["site_custom_identifier"] == "rpc_good"
    assert route_groups[1]["pull_summary"]["images_seen"] == 1
    assert route_groups[1]["ingest_summary"]["images_downloaded"] == 1

    summary = service._result_summary(result)
    assert summary["images_found"] == 1
    assert summary["reports_found"] == 1


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
    project_lab = ProjectLabUnit(
        project_id=project.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        active=True,
    )
    db_session.add_all(
        [encounter_scheme, encounter_set_type, upload_profile, mapping, project_lab]
    )
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
