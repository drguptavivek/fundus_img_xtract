from io import BytesIO
from uuid import uuid4

from PIL import Image

from encounter_set_types.models import EncounterSetType
from iitk_api_integration.contracts import IITKImageDTO, IITKImageInventory, IITKSessionDTO
from iitk_api_integration.models import IITKApiProjectConfig, IITKApiSessionLink
from iitk_api_integration.service import RuntimeConfig, _persist_session, _sync_session
from models import CeleryBeatSchedule, EncounterSetImage, PatientEncounters, Project
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileEncounterSetType


def jpeg(color="blue") -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), color=color).save(output, format="JPEG")
    return output.getvalue()


def source(status: str, image_count: int, positions: tuple[str, ...]) -> IITKSessionDTO:
    return IITKSessionDTO("session-1", "delhi", "closeup", "2026-08-01T01:30:00Z", positions, 9, status,
        image_count, "MRN-1", 42, "ou", "female", "other", "locally private", None)


def inventory(*positions: str) -> IITKImageInventory:
    return IITKImageInventory("session-1", "closeup", tuple(
        IITKImageDTO(f"private-{position}.jpg", position, len(jpeg(position == "primary" and "blue" or "green")), "image/jpeg", f"2026-08-01T01:3{index}:00Z")
        for index, position in enumerate(positions)
    ))


def setup_config(db_session, core_test_data):
    project = Project(title=f"IITK {uuid4()}", code=f"IITK{uuid4().hex[:8]}", active=True)
    profile = UploadProfile(name=f"IITK {uuid4()}", active=True)
    encounter_type = EncounterSetType(name=f"IITK {uuid4()}", code=f"iitk_{uuid4().hex[:8]}", active=True, metadata_schema_json={"fields": []}, asset_rules_json={})
    db_session.add_all([project, profile, encounter_type])
    db_session.flush()
    project_profile = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(UploadProfileEncounterSetType(upload_profile_id=profile.id, encounter_set_type_id=encounter_type.id, active=True))
    config = IITKApiProjectConfig(project_id=project.id, lab_unit_id=core_test_data["lab_unit"].id,
        project_upload_profile_id=project_profile.id, encounter_set_type_id=encounter_type.id,
        base_url="https://iitk.test", api_token_encrypted="unused", secret_salt="a" * 64, active=True)
    db_session.add(config)
    db_session.flush()
    runtime = RuntimeConfig(config.id, project.id, core_test_data["lab_unit"].id, profile.id, encounter_type.id,
        None, core_test_data["hospital"].id, "https://iitk.test", "secret", None, None, None)
    return runtime


def test_partial_session_is_created_then_updated_in_place(db_session, core_test_data, app, monkeypatch, tmp_path):
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)
    monkeypatch.setattr("iitk_api_integration.service.generate_thumbnail", lambda *args: False)

    first_inventory = inventory("primary")
    first = _persist_session(runtime, source("partial", 2, ("primary", "consent")), first_inventory, {"primary": jpeg()})
    second_inventory = inventory("primary", "up")
    second = _persist_session(runtime, source("complete", 3, ("primary", "up", "consent")), second_inventory, {"up": jpeg("green")})

    link = db_session.query(IITKApiSessionLink).one()
    encounter = db_session.get(PatientEncounters, link.patient_encounter_id)
    images = db_session.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).order_by(EncounterSetImage.spatial_position).all()
    assert first["encounters_created"] == 1
    assert second["encounters_updated"] == 1
    assert db_session.query(PatientEncounters).filter_by(project_id=runtime.project_id).count() == 1
    assert link.source_status == "complete"
    assert [image.spatial_position for image in images] == [1, 3]
    assert all(image.creates_task is False for image in images)
    assert encounter.metadata_json["patient"]["hospital_UHID"] == "MRN-1"
    assert encounter.metadata_json["encounter"]["capture_status"] == "complete"
    assert encounter.metadata_json["upload"]["source_kind"] == "iitk_api"
    assert all((tmp_path / image.folder_rel / image.original_filename).exists() for image in images)


def test_iitk_business_hours_schedule_is_seeded(db_session):
    row = db_session.query(CeleryBeatSchedule).filter_by(name="IITK API EncounterSet Sync Hourly IST Business Hours").one()
    assert row.queue == "maintenance"
    assert row.crontab_minute == "30"
    assert row.crontab_hour == "1-12"
    assert row.task_name == "celery_tasks.tasks.iitk_tasks.queue_active_iitk_syncs_task"


def test_image_failure_still_imports_partial_session_metadata(db_session, core_test_data, app, monkeypatch, tmp_path):
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)

    class FailingClient:
        def list_images(self, session_id):
            assert session_id == "session-1"
            return inventory("primary")

        def get_image(self, session_id, filename):
            raise RuntimeError("private remote failure")

    result = _sync_session(FailingClient(), runtime, source("partial", 1, ("primary", "consent")))

    link = db_session.query(IITKApiSessionLink).one()
    encounter = db_session.get(PatientEncounters, link.patient_encounter_id)
    assert result["images_failed"] == 1
    assert encounter.metadata_json["encounter"]["capture_status"] == "partial"
    assert link.local_image_count == 0
    assert "private remote failure" in link.last_error
