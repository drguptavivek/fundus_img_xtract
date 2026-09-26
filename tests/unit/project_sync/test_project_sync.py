from datetime import date, timedelta

import pytest
from sqlalchemy import select

from auth.utils import utcnow
from data_authorization.models import LAB_UNIT_SCOPE, PROJECT_SCOPE, ProjectRoleGrant
from grading.workbench.models import AnnotationInstance, AnnotationSet
from models import (
    DiseaseGrading,
    EncounterSetImage,
    Grade,
    GradingTask,
    GradingsFeatures,
    PatientEncounters,
    Project,
    Role,
    SensitiveOperationAudit,
    User,
)
from project_configuration.models import ProjectLabUnit
from project_sync import inventory, service
from project_sync.dto import RequestMeta, SyncGrantRequest
from project_sync.exceptions import (
    ProjectSyncAuthError,
    ProjectSyncConflict,
    ProjectSyncDisabled,
    ProjectSyncNotFound,
    ProjectSyncPermissionDenied,
    ProjectSyncValidationError,
)
from tests.helpers.factories import UserFactory

META = RequestMeta(ip_address="10.0.0.1", user_agent="pytest")


@pytest.fixture
def sync_on(app):
    app.config["PROJECT_SYNC_ENABLED"] = True
    app.config["PROJECT_SYNC_GRANT_DAYS"] = 90
    yield app
    app.config["PROJECT_SYNC_ENABLED"] = False


def _role(db, name):
    role = db.query(Role).filter_by(name=name).one_or_none()
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _user(db, username, email="pi@example.org"):
    user = User(username=username, password_hash="x", is_active=True, email=email)
    db.add(user)
    db.flush()
    return user


def _grant_role(db, user, project, role_name, lab_unit_id=None):
    db.add(
        ProjectRoleGrant(
            project_id=project.id,
            user_id=user.id,
            role_id=_role(db, role_name).id,
            scope_type=LAB_UNIT_SCOPE if lab_unit_id else PROJECT_SCOPE,
            lab_unit_id=lab_unit_id,
            active=True,
        )
    )
    db.flush()


@pytest.fixture
def world(db_session, core_test_data):
    lab_a1 = core_test_data["lab_a1"]
    lab_a2 = core_test_data["lab_a2"]
    project = Project(title="Sync Project", code="SYNC_P", active=True)
    other = Project(title="Other Project", code="SYNC_O", active=True)
    db_session.add_all([project, other])
    db_session.flush()
    db_session.add_all(
        ProjectLabUnit(project_id=project.id, lab_unit_id=lab.id, active=True) for lab in (lab_a1, lab_a2)
    )
    db_session.flush()
    admin = UserFactory.create_admin(db_session, username="sync_admin")
    pi = _user(db_session, "sync_pi", "pi@example.org")
    _grant_role(db_session, pi, project, "project_pi")
    dm = _user(db_session, "sync_dm", "dm@example.org")
    _grant_role(db_session, dm, project, "data_manager", lab_unit_id=lab_a1.id)
    outsider = _user(db_session, "sync_outsider", "out@example.org")
    _grant_role(db_session, outsider, project, "collaborator")

    def encounter(lab, proj=project, uuid_suffix="1"):
        row = PatientEncounters(
            name="Jane Patient", patient_id=f"PID-{uuid_suffix}", capture_date="2026-09-14",
            capture_date_dt=date(2026, 9, 14), lab_unit_id=lab.id, project_id=proj.id,
            disease_id=core_test_data["dr"].id, is_set_based=True,
        )
        db_session.add(row)
        db_session.flush()
        return row

    def set_image(enc, position, *, is_pii=False):
        row = EncounterSetImage(
            patient_encounter_id=enc.id, spatial_position=position,
            original_filename=f"img{position}.jpg", folder_rel="files/test",
            project_id=enc.project_id, is_pii=is_pii,
        )
        db_session.add(row)
        db_session.flush()
        return row

    enc_a1 = encounter(lab_a1, uuid_suffix="A1")
    img_ok = set_image(enc_a1, 1)
    img_pii = set_image(enc_a1, 2, is_pii=True)
    enc_a2 = encounter(lab_a2, uuid_suffix="A2")
    img_a2 = set_image(enc_a2, 1)
    enc_other = encounter(lab_a1, proj=other, uuid_suffix="O")
    img_other = set_image(enc_other, 1)
    return {
        "project": project, "other": other, "admin": admin, "pi": pi, "dm": dm, "outsider": outsider,
        "lab_a1": lab_a1, "lab_a2": lab_a2, "enc_a1": enc_a1, "enc_a2": enc_a2, "enc_other": enc_other,
        "img_ok": img_ok, "img_pii": img_pii, "img_a2": img_a2, "img_other": img_other,
        "dr": core_test_data["dr"],
    }


def _approved_credential(db, world, user, *, include_pii=False):
    result = service.request_grant(
        db, user=user, request=SyncGrantRequest(project_id=world["project"].id,
                                                purpose="Local study archive", include_pii=include_pii),
        meta=META,
    )
    service.confirm_email(db, user=user, token=result.email_token, meta=META)
    service.approve_grant(db, admin=world["admin"], grant_id=result.grant.id, note=None, valid_days=30, meta=META)
    issued = service.issue_credential(db, user=user, grant_id=result.grant.id, meta=META)
    return result.grant.id, issued.credential


# ---------------------------------------------------------------------------
# Lifecycle gates
# ---------------------------------------------------------------------------


def test_server_switch_blocks_requests_and_credentials(app, db_session, world):
    app.config["PROJECT_SYNC_ENABLED"] = False
    with pytest.raises(ProjectSyncDisabled):
        service.request_grant(
            db_session, user=world["pi"],
            request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
        )
    with pytest.raises(ProjectSyncDisabled):
        service.authenticate_credential(db_session, credential="pds_x", meta=META)


def test_only_pi_or_data_manager_may_request(sync_on, db_session, world):
    with pytest.raises(ProjectSyncPermissionDenied):
        service.request_grant(
            db_session, user=world["outsider"],
            request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
        )
    with pytest.raises(ProjectSyncPermissionDenied):
        service.request_grant(
            db_session, user=world["admin"],
            request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
        )


def test_identifier_sync_requires_pi_or_pii_exporter(sync_on, db_session, world):
    with pytest.raises(ProjectSyncPermissionDenied):
        service.request_grant(
            db_session, user=world["dm"],
            request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive", include_pii=True),
            meta=META,
        )
    result = service.request_grant(
        db_session, user=world["pi"],
        request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive", include_pii=True),
        meta=META,
    )
    assert result.grant.include_pii is True


def test_purpose_and_email_are_required(sync_on, db_session, world):
    with pytest.raises(ProjectSyncValidationError):
        service.request_grant(
            db_session, user=world["pi"],
            request=SyncGrantRequest(project_id=world["project"].id, purpose="short"), meta=META,
        )
    world["pi"].email = None
    with pytest.raises(ProjectSyncValidationError):
        service.request_grant(
            db_session, user=world["pi"],
            request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
        )


def test_full_lifecycle_requires_email_then_admin_then_credential(sync_on, db_session, world):
    pi, admin = world["pi"], world["admin"]
    result = service.request_grant(
        db_session, user=pi,
        request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
    )
    grant_id = result.grant.id
    assert result.grant.status == "pending_email"

    with pytest.raises(ProjectSyncConflict):
        service.request_grant(
            db_session, user=pi,
            request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
        )
    with pytest.raises(ProjectSyncConflict):
        service.approve_grant(db_session, admin=admin, grant_id=grant_id, note=None, valid_days=None, meta=META)
    with pytest.raises(ProjectSyncValidationError):
        service.confirm_email(db_session, user=world["dm"], token=result.email_token, meta=META)

    confirmed = service.confirm_email(db_session, user=pi, token=result.email_token, meta=META)
    assert confirmed.status == "pending_approval"
    with pytest.raises(ProjectSyncValidationError):
        service.confirm_email(db_session, user=pi, token=result.email_token, meta=META)
    with pytest.raises(ProjectSyncConflict):
        service.issue_credential(db_session, user=pi, grant_id=grant_id, meta=META)
    with pytest.raises(ProjectSyncPermissionDenied):
        service.approve_grant(db_session, admin=world["dm"], grant_id=grant_id, note=None, valid_days=None, meta=META)
    with pytest.raises(ProjectSyncValidationError):
        service.approve_grant(db_session, admin=admin, grant_id=grant_id, note=None, valid_days=365, meta=META)

    approved = service.approve_grant(db_session, admin=admin, grant_id=grant_id, note="ok", valid_days=30, meta=META)
    assert approved.status == "approved" and approved.is_usable is False
    with pytest.raises(ProjectSyncNotFound):
        service.issue_credential(db_session, user=world["dm"], grant_id=grant_id, meta=META)

    issued = service.issue_credential(db_session, user=pi, grant_id=grant_id, meta=META)
    assert issued.credential.startswith("pds_")
    ctx = service.authenticate_credential(db_session, credential=issued.credential, meta=META)
    assert ctx.project_id == world["project"].id
    assert ctx.lab_unit_ids == {world["lab_a1"].id, world["lab_a2"].id}
    assert ctx.pii_lab_unit_ids == frozenset()

    rotated = service.issue_credential(db_session, user=pi, grant_id=grant_id, meta=META)
    with pytest.raises(ProjectSyncAuthError):
        service.authenticate_credential(db_session, credential=issued.credential, meta=META)
    service.authenticate_credential(db_session, credential=rotated.credential, meta=META)

    service.revoke_grant(db_session, actor=admin, grant_id=grant_id, reason="done", meta=META)
    db_session.flush()
    with pytest.raises(ProjectSyncAuthError):
        service.authenticate_credential(db_session, credential=rotated.credential, meta=META)

    statuses = set(
        db_session.execute(
            select(SensitiveOperationAudit.status).where(SensitiveOperationAudit.operation_type == "project_data_sync")
        ).scalars()
    )
    assert {"requested", "email_confirmed", "approved", "credential_issued", "credential_rotated", "revoked"} <= statuses


def test_admin_cannot_approve_own_request(sync_on, db_session, world):
    admin = world["admin"]
    admin.email = "admin@example.org"
    _grant_role(db_session, admin, world["project"], "data_manager")
    result = service.request_grant(
        db_session, user=admin,
        request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
    )
    service.confirm_email(db_session, user=admin, token=result.email_token, meta=META)
    with pytest.raises(ProjectSyncPermissionDenied):
        service.approve_grant(db_session, admin=admin, grant_id=result.grant.id, note=None, valid_days=None, meta=META)


def test_expired_email_token_is_rejected(sync_on, db_session, world):
    result = service.request_grant(
        db_session, user=world["pi"],
        request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
    )
    from project_sync.models import ProjectSyncGrant

    db_session.get(ProjectSyncGrant, result.grant.id).email_token_expires_at = utcnow() - timedelta(minutes=1)
    with pytest.raises(ProjectSyncValidationError):
        service.confirm_email(db_session, user=world["pi"], token=result.email_token, meta=META)


def test_losing_project_role_or_expiry_kills_credential(sync_on, db_session, world):
    _, credential = _approved_credential(db_session, world, world["dm"])
    ctx = service.authenticate_credential(db_session, credential=credential, meta=META)
    assert ctx.lab_unit_ids == {world["lab_a1"].id}

    grant_row = db_session.execute(
        select(ProjectRoleGrant).where(ProjectRoleGrant.user_id == world["dm"].id)
    ).scalar_one()
    grant_row.active = False
    db_session.flush()
    with pytest.raises(ProjectSyncAuthError):
        service.authenticate_credential(db_session, credential=credential, meta=META)

    grant_row.active = True
    db_session.flush()
    from project_sync.models import ProjectSyncGrant

    row = db_session.execute(select(ProjectSyncGrant).where(ProjectSyncGrant.user_id == world["dm"].id)).scalar_one()
    row.expires_at = utcnow() - timedelta(seconds=1)
    db_session.flush()
    with pytest.raises(ProjectSyncAuthError):
        service.authenticate_credential(db_session, credential=credential, meta=META)


# ---------------------------------------------------------------------------
# Inventory scope
# ---------------------------------------------------------------------------


def test_listing_is_scoped_to_project_labs_and_masks_identifiers(sync_on, db_session, world):
    _, credential = _approved_credential(db_session, world, world["dm"])
    ctx = service.authenticate_credential(db_session, credential=credential, meta=META)
    page = inventory.list_encounters(db_session, ctx, after_id=0, limit=200)
    uuids = {item["uuid"] for item in page["items"]}
    assert uuids == {world["enc_a1"].uuid}  # lab A2 and other project excluded
    item = page["items"][0]
    assert item["patient_id"] is None and item["patient_name"] is None
    image_uuids = {image["uuid"] for image in item["images"]}
    assert image_uuids == {world["img_ok"].uuid}  # PII-flagged image withheld

    with pytest.raises(ProjectSyncNotFound):
        inventory.authorize_sync_media(db_session, ctx, world["img_pii"].uuid)
    with pytest.raises(ProjectSyncNotFound):
        inventory.authorize_sync_media(db_session, ctx, world["img_a2"].uuid)
    with pytest.raises(ProjectSyncNotFound):
        inventory.authorize_sync_media(db_session, ctx, world["img_other"].uuid)
    assert inventory.authorize_sync_media(db_session, ctx, world["img_ok"].uuid).uuid == world["img_ok"].uuid


def test_pi_identifier_grant_includes_identifiers_and_pii_images(sync_on, db_session, world):
    _, credential = _approved_credential(db_session, world, world["pi"], include_pii=True)
    ctx = service.authenticate_credential(db_session, credential=credential, meta=META)
    page = inventory.list_encounters(db_session, ctx, after_id=0, limit=200)
    by_uuid = {item["uuid"]: item for item in page["items"]}
    assert set(by_uuid) == {world["enc_a1"].uuid, world["enc_a2"].uuid}
    assert by_uuid[world["enc_a1"].uuid]["patient_id"] == "PID-A1"
    assert {i["uuid"] for i in by_uuid[world["enc_a1"].uuid]["images"]} == {world["img_ok"].uuid, world["img_pii"].uuid}
    assert inventory.authorize_sync_media(db_session, ctx, world["img_pii"].uuid)


def test_pagination_cursor(sync_on, db_session, world):
    _, credential = _approved_credential(db_session, world, world["pi"])
    ctx = service.authenticate_credential(db_session, credential=credential, meta=META)
    first = inventory.list_encounters(db_session, ctx, after_id=0, limit=1)
    assert len(first["items"]) == 1 and first["next_after_id"] == first["items"][0]["id"]
    second = inventory.list_encounters(db_session, ctx, after_id=first["next_after_id"], limit=1)
    assert second["items"][0]["uuid"] != first["items"][0]["uuid"]


def test_sidecars_include_every_grader_with_annotations_and_coco(sync_on, db_session, world):
    _, credential = _approved_credential(db_session, world, world["pi"])
    ctx = service.authenticate_credential(db_session, credential=credential, meta=META)
    image = world["img_ok"]
    task = GradingTask(encounter_set_image_id=image.id, disease_id=world["dr"].id, lab_unit_id=world["lab_a1"].id)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    label = db_session.execute(
        select(DiseaseGrading).where(DiseaseGrading.disease_id == world["dr"].id).limit(1)
    ).scalar_one()
    grades = []
    for slot, grader in (("resident", world["dm"]), ("resident2", world["outsider"])):
        grade = Grade(task_id=task.id, grader_user_id=grader.id, role_slot=slot,
                      disease_grading_id=label.id, grade_name=label.impression)
        db_session.add(grade)
        db_session.flush()
        grades.append(grade)
    annotation_set = AnnotationSet(grade_id=grades[0].id, policy_source="project", policy_revision=1,
                                   source_image_width=100, source_image_height=80)
    db_session.add(annotation_set)
    db_session.flush()
    feature = GradingsFeatures(disease_grading_id=label.id, sr_no=9001, label="Sync lesion")
    db_session.add(feature)
    db_session.flush()
    if feature is not None:
        db_session.add(AnnotationInstance(
            annotation_set_id=annotation_set.id, image_uuid=image.uuid, class_source="grading_feature",
            grading_feature_id=feature.id, class_key_snapshot="lesion", class_label_snapshot="Lesion",
            policy_revision=1, geometry_type="box", geometry_json={}, bbox_x=10, bbox_y=10, bbox_w=20, bbox_h=15,
        ))
        db_session.flush()

    listing = inventory.list_encounters(db_session, ctx, after_id=0, limit=200)
    fingerprint_before = next(
        i["sidecar_fingerprint"] for e in listing["items"] for i in e["images"] if i["uuid"] == image.uuid
    )
    result = inventory.build_sidecars(db_session, ctx, encounter_uuids=[world["enc_a1"].uuid],
                                      image_uuids=[image.uuid, world["img_other"].uuid])
    assert world["img_other"].uuid in result["missing"]
    records = result["images"][image.uuid]
    grade_records = [r for r in records if r["record_type"] == "grade"]
    assert {r["grader_user_id"] for r in grade_records} == {world["dm"].id, world["outsider"].id}
    assert all(r["created_at"] for r in grade_records)
    coco = [r for r in records if r["record_type"] == "coco"]
    assert len(coco) == 1 and coco[0]["image"]["width"] == 100
    assert len(coco[0]["annotations"]) == 1
    assert coco[0]["annotations"][0]["source_grader_user_id"] == world["dm"].id
    assert coco[0]["categories"]
    encounter_records = result["encounters"][world["enc_a1"].uuid]
    assert encounter_records[0]["record_type"] == "encounter"
    assert len([r for r in encounter_records if r["record_type"] == "grade"]) == 2

    db_session.add(AnnotationInstance(
        annotation_set_id=annotation_set.id, image_uuid=image.uuid, class_source="grading_feature",
        grading_feature_id=feature.id, class_key_snapshot="lesion", class_label_snapshot="Lesion",
        policy_revision=1, geometry_type="box", geometry_json={}, bbox_x=40, bbox_y=40, bbox_w=5, bbox_h=5,
        instance_order=1,
    ))
    db_session.flush()
    listing = inventory.list_encounters(db_session, ctx, after_id=0, limit=200)
    fingerprint_annotated = next(
        i["sidecar_fingerprint"] for e in listing["items"] for i in e["images"] if i["uuid"] == image.uuid
    )
    assert fingerprint_annotated != fingerprint_before
    fingerprint_before = fingerprint_annotated

    grades[1].grade_name = "changed"
    grades[1].updated_at = utcnow() + timedelta(seconds=5)
    db_session.flush()
    listing = inventory.list_encounters(db_session, ctx, after_id=0, limit=200)
    fingerprint_after = next(
        i["sidecar_fingerprint"] for e in listing["items"] for i in e["images"] if i["uuid"] == image.uuid
    )
    assert fingerprint_after != fingerprint_before


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_sync_api_rejects_missing_or_bad_credentials(sync_on, client, world):
    assert client.get("/api/sync/v1/whoami").status_code == 401
    response = client.get("/api/sync/v1/whoami", headers={"Authorization": "Bearer pds_wrong"})
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


def test_sync_api_serves_scoped_inventory(sync_on, client, db_session, world):
    _, credential = _approved_credential(db_session, world, world["dm"])
    headers = {"Authorization": f"Bearer {credential}"}
    whoami = client.get("/api/sync/v1/whoami", headers=headers)
    assert whoami.status_code == 200
    assert whoami.get_json()["project"]["code"] == "SYNC_P"
    encounters = client.get("/api/sync/v1/encounters?limit=10", headers=headers).get_json()
    assert [e["uuid"] for e in encounters["items"]] == [world["enc_a1"].uuid]
    assert client.get(f"/api/sync/v1/media/{world['img_other'].uuid}", headers=headers).status_code == 404
    assert client.get(f"/api/sync/v1/media/{world['img_ok'].uuid}?variant=bogus", headers=headers).status_code == 400
    sidecars = client.post("/api/sync/v1/sidecars", json={"images": [world["img_ok"].uuid]}, headers=headers)
    assert sidecars.status_code == 200 and world["img_ok"].uuid in sidecars.get_json()["images"]


def test_sync_api_refuses_browser_session(sync_on, db_session, world, app):
    from tests.conftest import create_authenticated_client

    browser = create_authenticated_client(app, world["pi"], db_session)
    assert browser.get("/api/sync/v1/whoami").status_code == 401


def test_session_api_requires_reauth_for_request(sync_on, db_session, world, app):
    from tests.conftest import create_authenticated_client

    browser = create_authenticated_client(app, world["pi"], db_session)
    response = browser.post("/api/project-sync/grants", json={"project_id": world["project"].id, "purpose": "Local study archive"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "reauth_required"


@pytest.fixture(autouse=True)
def _no_shared_redis(monkeypatch):
    """Keep tests off the shared Redis sync gate; gate behaviour is tested explicitly."""
    import api.sync.routes as routes

    released = []
    monkeypatch.setattr(routes, "acquire_slot", lambda: "slot")
    monkeypatch.setattr(routes, "release_slot", lambda token: released.append(token))
    return released


def test_busy_gate_returns_429_with_retry_after(sync_on, client, db_session, world, monkeypatch):
    import api.sync.routes as routes
    from project_sync.throttle import ProjectSyncBusy

    _, credential = _approved_credential(db_session, world, world["pi"])

    def busy():
        raise ProjectSyncBusy(retry_after=7)

    monkeypatch.setattr(routes, "acquire_slot", busy)
    response = client.get("/api/sync/v1/whoami", headers={"Authorization": f"Bearer {credential}"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"


def test_slot_released_after_response(sync_on, client, db_session, world, _no_shared_redis):
    _, credential = _approved_credential(db_session, world, world["pi"])
    response = client.get("/api/sync/v1/whoami", headers={"Authorization": f"Bearer {credential}"})
    response.close()
    assert _no_shared_redis == ["slot"]
    assert response.get_json()["client_policy"]["max_concurrency"] == 1


def test_throttle_semaphore_caps_inflight(app, monkeypatch):
    from project_sync import throttle

    class FakeRedis:
        def __init__(self):
            self.members = {}

        def eval(self, script, numkeys, key, now, expiry, limit, token, ttl):
            self.members = {k: v for k, v in self.members.items() if v > now}
            if len(self.members) < int(limit):
                self.members[token] = expiry
                return 1
            return 0

        def zrem(self, key, token):
            self.members.pop(token, None)

    fake = FakeRedis()
    monkeypatch.setattr(throttle, "_redis", lambda: fake)
    app.config["PROJECT_SYNC_MAX_CONCURRENT"] = 1
    first = throttle.acquire_slot()
    with pytest.raises(throttle.ProjectSyncBusy):
        throttle.acquire_slot()
    throttle.release_slot(first)
    throttle.release_slot(throttle.acquire_slot())
    monkeypatch.setattr(throttle, "_redis", lambda: None)
    with pytest.raises(throttle.ProjectSyncBusy):
        throttle.acquire_slot()


def test_export_is_queued_once_and_honours_grant(sync_on, db_session, world, monkeypatch, app):
    from project_sync import exports

    queued = []
    monkeypatch.setattr(exports, "enqueue_project_export", lambda app_, token, data: queued.append((token, data)))
    _, credential = _approved_credential(db_session, world, world["dm"])
    ctx = service.authenticate_credential(db_session, credential=credential, meta=META)
    job = exports.request_export(db_session, ctx, app=app, ip_address="10.0.0.1")
    assert job.status == "queued"
    assert queued[0][1]["sync_grant_uuid"] == ctx.grant_uuid
    with pytest.raises(ProjectSyncConflict):
        exports.request_export(db_session, ctx, app=app, ip_address="10.0.0.1")

    labs = service.grant_export_lab_unit_ids(
        db_session, grant_uuid=ctx.grant_uuid, user_id=ctx.user_id, project_id=ctx.project_id
    )
    assert labs == {world["lab_a1"].id}
    assert service.grant_export_lab_unit_ids(
        db_session, grant_uuid=ctx.grant_uuid, user_id=world["pi"].id, project_id=ctx.project_id
    ) == frozenset()
    with pytest.raises(ProjectSyncNotFound):
        exports.export_file(db_session, ctx, token=job.token, filename="project_encounterset_export.xlsx")


def test_pages_render_for_requester_and_admin(sync_on, db_session, world, app):
    from tests.conftest import create_authenticated_client

    service.request_grant(
        db_session, user=world["pi"],
        request=SyncGrantRequest(project_id=world["project"].id, purpose="Local study archive"), meta=META,
    )
    pi_client = create_authenticated_client(app, world["pi"], db_session)
    page = pi_client.get("/project-sync/")
    assert page.status_code == 200 and b"SYNC_P" in page.data
    assert pi_client.get("/project-sync/workspace").status_code == 200
    assert pi_client.get("/project-sync/confirm?token=abc").status_code == 200
    assert pi_client.get("/project-sync/admin").status_code == 403
    from flask import g

    # The fixture's app context is shared across clients; drop Flask-Login's cached user.
    g.pop("_login_user", None)
    admin_client = create_authenticated_client(app, world["admin"], db_session)
    admin_page = admin_client.get("/project-sync/admin")
    assert admin_page.status_code == 200 and b"sync_pi" in admin_page.data
    g.pop("_login_user", None)
    status = pi_client.get("/api/project-sync/status").get_json()
    assert status["enabled"] is True and status["eligible_projects"][0]["code"] == "SYNC_P"
