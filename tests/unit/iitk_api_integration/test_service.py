from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

from PIL import Image

from encounter_set_types.models import EncounterSetType
from iitk_api_integration.contracts import IITKImageDTO, IITKImageInventory, IITKSessionDTO
from iitk_api_integration.models import IITKApiProjectConfig, IITKApiSessionLink
from iitk_api_integration.service import (
    RuntimeConfig,
    _persist_session,
    _sync_session,
    project_connection_context,
    recover_stale_config_syncs,
    remap_iitk_encounter_site,
    reclaim_stale_sync_locks,
    save_project_connection,
    site_mapping_catalog,
)
from models import CeleryBeatSchedule, EncounterSetImage, Hospital, LabUnit, PatientEncounters, Project
from upload_profiles.models import ProjectUploadProfile, UploadProfile, UploadProfileEncounterSetType
from utils.encryption import decrypt_password_with_salt


def jpeg(color="blue") -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 12), color=color).save(output, format="JPEG")
    return output.getvalue()


def source(status: str, image_count: int, positions: tuple[str, ...], *, site: str = "delhi") -> IITKSessionDTO:
    return IITKSessionDTO("session-1", site, "closeup", "2026-08-01T01:30:00Z", positions, 9, status,
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


def destination(db_session, hospital_name: str, lab_unit_name: str):
    hospital = db_session.query(Hospital).filter_by(name=hospital_name).one_or_none()
    if hospital is None:
        hospital = Hospital(name=hospital_name)
        db_session.add(hospital)
        db_session.flush()
    lab_unit = db_session.query(LabUnit).filter_by(hospital_id=hospital.id, name=lab_unit_name).one_or_none()
    if lab_unit is None:
        lab_unit = LabUnit(hospital_id=hospital.id, name=lab_unit_name)
        db_session.add(lab_unit)
        db_session.flush()
    return hospital, lab_unit


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
    assert [image.metadata_json["source_filename"] for image in images] == ["private-primary.jpg", "private-up.jpg"]
    assert all(image.original_filename != image.metadata_json["source_filename"] for image in images)


def test_inventory_sync_backfills_exact_source_filename_without_redownload(
    db_session, core_test_data, app, monkeypatch, tmp_path
):
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)
    monkeypatch.setattr("iitk_api_integration.service.generate_thumbnail", lambda *args: False)
    current_inventory = inventory("primary")
    _persist_session(runtime, source("partial", 1, ("primary",)), current_inventory, {"primary": jpeg()})
    image = db_session.query(EncounterSetImage).one()
    local_filename = image.original_filename
    metadata = dict(image.metadata_json)
    metadata.pop("source_filename")
    image.metadata_json = metadata
    db_session.flush()

    result = _persist_session(runtime, source("partial", 1, ("primary",)), current_inventory, {})
    db_session.refresh(image)

    assert result["images_unchanged"] == 1
    assert image.original_filename == local_filename
    assert image.metadata_json["source_filename"] == "private-primary.jpg"


def test_complete_upstream_session_and_inventory_payloads_are_preserved_for_audit(
    db_session, core_test_data, app, monkeypatch, tmp_path
):
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)
    monkeypatch.setattr("iitk_api_integration.service.generate_thumbnail", lambda *args: False)
    raw_session = {
        "sessionId": "session-1",
        "mrn": "MRN-1",
        "futureSessionField": {"nested": [1, "kept"]},
    }
    raw_image = {
        "filename": "private-primary.jpg",
        "position": "primary",
        "contentType": "image/jpeg",
        "futureImageField": {"kept": True},
    }
    raw_inventory = {
        "sessionId": "session-1",
        "mode": "closeup",
        "images": [raw_image],
        "futureInventoryField": ["also", "kept"],
    }
    source_dto = replace(source("partial", 1, ("primary",)), raw_payload=raw_session)
    parsed_inventory = inventory("primary")
    image_dto = replace(parsed_inventory.images[0], raw_payload=raw_image)
    inventory_dto = IITKImageInventory(
        parsed_inventory.session_id,
        parsed_inventory.mode,
        (image_dto,),
        raw_payload=raw_inventory,
    )

    _persist_session(runtime, source_dto, inventory_dto, {"primary": jpeg()})

    link = db_session.query(IITKApiSessionLink).one()
    image = db_session.query(EncounterSetImage).one()
    assert link.source_metadata_json["upstream_session_payload"] == raw_session
    assert link.source_metadata_json["upstream_image_inventory_payload"] == raw_inventory
    assert image.metadata_json["upstream_payload"] == raw_image


def test_capture_datetime_is_normalized_and_dated_in_utc(db_session, core_test_data, app, monkeypatch, tmp_path):
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)
    source_with_offset = replace(source("partial", 0, ()), started_at="2026-08-01T00:30:00+05:30")

    _persist_session(runtime, source_with_offset, inventory(), {})

    encounter = db_session.query(PatientEncounters).filter_by(project_id=runtime.project_id).one()
    assert encounter.capture_date == "2026-07-31"
    assert encounter.capture_date_dt.isoformat() == "2026-07-31"
    assert encounter.metadata_json["encounter"]["capture_datetime"] == "2026-07-31T19:00:00Z"


def test_site_mapping_routes_import_and_preserves_editable_site(db_session, core_test_data, app, monkeypatch, tmp_path):
    rpc, delhi_lab = destination(db_session, "RPC AIIMS", "Deepsekhar Das")
    kalyani, kalyani_lab = destination(db_session, "AIIMS Kalyani", "Ophthalmology")
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)
    monkeypatch.setattr("iitk_api_integration.service.generate_thumbnail", lambda *args: False)

    _persist_session(runtime, source("partial", 1, ("primary",)), inventory("primary"), {"primary": jpeg()})
    link = db_session.query(IITKApiSessionLink).one()
    encounter = db_session.get(PatientEncounters, link.patient_encounter_id)
    image = db_session.query(EncounterSetImage).filter_by(patient_encounter_id=encounter.id).one()

    assert encounter.lab_unit_id == delhi_lab.id
    assert image.hospital_id == rpc.id
    assert encounter.metadata_json["patient"]["site_recruitment"] == "delhi"
    assert encounter.metadata_json["upload"]["source_site"] == "delhi"
    assert encounter.metadata_json["upload"]["site_mapping_status"] == "mapped"

    metadata = dict(encounter.metadata_json)
    metadata["patient"] = {**metadata["patient"], "site_recruitment": "kalyani"}
    encounter.metadata_json = metadata
    remap_iitk_encounter_site(db_session, encounter)
    db_session.flush()

    _persist_session(runtime, source("partial", 1, ("primary",), site="delhi"), inventory("primary"), {})
    db_session.refresh(encounter)
    db_session.refresh(image)

    assert encounter.lab_unit_id == kalyani_lab.id
    assert image.hospital_id == kalyani.id
    assert encounter.metadata_json["patient"]["site_recruitment"] == "kalyani"
    assert encounter.metadata_json["upload"]["source_site"] == "delhi"


def test_unknown_site_imports_to_default_intake_lab(db_session, core_test_data, app, monkeypatch, tmp_path):
    runtime = setup_config(db_session, core_test_data)
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)

    _persist_session(runtime, source("partial", 0, (), site="new-site"), inventory(), {})
    link = db_session.query(IITKApiSessionLink).one()
    encounter = db_session.get(PatientEncounters, link.patient_encounter_id)

    assert encounter.lab_unit_id == runtime.lab_unit_id
    assert encounter.metadata_json["patient"]["site_recruitment"] == "new-site"
    assert encounter.metadata_json["upload"]["source_site"] == "new-site"
    assert encounter.metadata_json["upload"]["site_mapping_status"] == "unmapped"


def test_site_mapping_catalog_uses_stable_names_not_database_ids():
    assert site_mapping_catalog() == {
        "bilaspur": {"hospital": "AIIMS Bilaspur", "lab_unit": "Ophthalmology"},
        "delhi": {"hospital": "RPC AIIMS", "lab_unit": "Deepsekhar Das"},
        "kalyani": {"hospital": "AIIMS Kalyani", "lab_unit": "Ophthalmology"},
        "nagpur": {"hospital": "AIIMS Nagpur", "lab_unit": "Ophthalmology"},
    }


def test_project_connection_saves_only_flag_and_encrypted_token_from_existing_target(
    db_session, core_test_data, app, monkeypatch
):
    _, default_lab = destination(db_session, "RPC AIIMS", "Deepsekhar Das")
    project = Project(title=f"IITK {uuid4()}", code=f"IITK{uuid4().hex[:8]}", active=True)
    profile = UploadProfile(name=f"IITK API {uuid4()}", active=True)
    encounter_type = EncounterSetType(
        name=f"IITK {uuid4()}", code=f"iitk_{uuid4().hex[:8]}", active=True,
        metadata_schema_json={"fields": []}, asset_rules_json={},
    )
    db_session.add_all([project, profile, encounter_type])
    db_session.flush()
    project_profile = ProjectUploadProfile(project_id=project.id, upload_profile_id=profile.id, active=True)
    db_session.add(project_profile)
    db_session.flush()
    db_session.add(UploadProfileEncounterSetType(
        upload_profile_id=profile.id, encounter_set_type_id=encounter_type.id, active=True,
    ))
    db_session.flush()
    monkeypatch.setattr("iitk_api_integration.service.manager_lab_unit_ids", lambda _user_id: {default_lab.id})

    row = save_project_connection(
        db_session, project.id, {"active": "true", "api_token": "private-token"}, manager_user_id=7,
    )
    encrypted_token = row.api_token_encrypted

    assert row.active is True
    assert row.lab_unit_id == default_lab.id
    assert row.project_upload_profile_id == project_profile.id
    assert row.encounter_set_type_id == encounter_type.id
    assert decrypt_password_with_salt(row.api_token_encrypted, row.secret_salt) == "private-token"

    save_project_connection(
        db_session, project.id, {"active": "true", "api_token": ""}, manager_user_id=7,
    )
    assert row.api_token_encrypted == encrypted_token

    save_project_connection(db_session, project.id, {"active": "false"}, manager_user_id=7)
    assert row.active is False


def test_disabled_non_iitk_project_does_not_show_iitk_target_warning(db_session):
    project = Project(
        title=f"Ordinary project {uuid4()}", code=f"ORD{uuid4().hex[:8]}", active=True,
    )
    first_profile = UploadProfile(name=f"First {uuid4()}", active=True)
    second_profile = UploadProfile(name=f"Second {uuid4()}", active=True)
    first_type = EncounterSetType(
        name=f"First type {uuid4()}", code=f"first_{uuid4().hex[:8]}", active=True,
        metadata_schema_json={"fields": []}, asset_rules_json={},
    )
    second_type = EncounterSetType(
        name=f"Second type {uuid4()}", code=f"second_{uuid4().hex[:8]}", active=True,
        metadata_schema_json={"fields": []}, asset_rules_json={},
    )
    db_session.add_all([project, first_profile, second_profile, first_type, second_type])
    db_session.flush()
    db_session.add_all([
        ProjectUploadProfile(project_id=project.id, upload_profile_id=first_profile.id, active=True),
        ProjectUploadProfile(project_id=project.id, upload_profile_id=second_profile.id, active=True),
        UploadProfileEncounterSetType(
            upload_profile_id=first_profile.id, encounter_set_type_id=first_type.id, active=True,
        ),
        UploadProfileEncounterSetType(
            upload_profile_id=second_profile.id, encounter_set_type_id=second_type.id, active=True,
        ),
    ])
    db_session.flush()

    context = project_connection_context(db_session, project.id)

    assert context["iitk_project_config"]["active"] is False
    assert context["iitk_project_target"] is None
    assert context["iitk_project_readiness_error"] is None


def test_iitk_business_hours_schedule_is_seeded(db_session):
    row = db_session.query(CeleryBeatSchedule).filter_by(name="IITK API EncounterSet Sync Hourly IST Business Hours").one()
    assert row.queue == "maintenance"
    assert row.crontab_minute == "30"
    assert row.crontab_hour == "1-12"
    assert row.task_name == "celery_tasks.tasks.iitk_tasks.queue_active_iitk_syncs_task"


def test_iitk_stale_recovery_schedule_is_seeded(db_session):
    row = db_session.query(CeleryBeatSchedule).filter_by(name="IITK API Stale Sync Recovery").one()
    assert row.queue == "maintenance"
    assert row.schedule_type == "interval"
    assert row.interval_seconds == 300
    assert row.task_name == "celery_tasks.tasks.iitk_tasks.recover_stale_iitk_syncs_task"


def test_only_stale_iitk_heartbeat_locks_are_reclaimed(db_session, core_test_data, app):
    stale_runtime = setup_config(db_session, core_test_data)
    recent_runtime = setup_config(db_session, core_test_data)
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    stale = db_session.get(IITKApiProjectConfig, stale_runtime.id)
    recent = db_session.get(IITKApiProjectConfig, recent_runtime.id)
    stale.sync_started_at = now - timedelta(minutes=16)
    recent.sync_started_at = now - timedelta(minutes=14)
    db_session.flush()

    reclaimed = reclaim_stale_sync_locks(now=now)

    assert reclaimed == [stale.id]
    assert stale.sync_started_at is None
    assert recent.sync_started_at == now - timedelta(minutes=14)


def test_stale_recovery_does_not_queue_api_sync_outside_business_hours(
    db_session, core_test_data, app, monkeypatch
):
    runtime = setup_config(db_session, core_test_data)
    now = datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc)  # 18:30 IST
    config = db_session.get(IITKApiProjectConfig, runtime.id)
    config.sync_started_at = now - timedelta(minutes=16)
    db_session.flush()
    queued_ids = []
    monkeypatch.setattr(
        "iitk_api_integration.service._queue_config_ids",
        lambda config_ids: queued_ids.extend(config_ids) or [],
    )

    result = recover_stale_config_syncs(now=now)

    assert result["reclaimed_config_ids"] == [runtime.id]
    assert result["deferred_count"] == 1
    assert queued_ids == []


def test_session_commit_refreshes_active_sync_heartbeat(db_session, core_test_data, app, monkeypatch, tmp_path):
    runtime = setup_config(db_session, core_test_data)
    config = db_session.get(IITKApiProjectConfig, runtime.id)
    old_heartbeat = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
    config.sync_started_at = old_heartbeat
    db_session.flush()
    monkeypatch.setattr("iitk_api_integration.service.BASE_DIR", tmp_path)

    _persist_session(runtime, source("partial", 0, ()), inventory(), {})

    assert config.sync_started_at > old_heartbeat


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
