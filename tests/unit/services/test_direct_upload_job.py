from __future__ import annotations

import io
from itertools import count

from PIL import Image
from werkzeug.datastructures import FileStorage

from models import AIInferenceRun, AIModel, AIModelIntegration, Area, Camera, DirectImageUpload, DirectImageVerify, DiseaseGrading, Grade, GradingTask, Hospital, Job, JobItem, LabUnit, Project, User
from services.uploads.direct import DirectUploadActor, DirectUploadJobRequest, create_direct_upload_job, direct_upload_response_payload
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from tests.helpers.factories import UserFactory
from upload_profiles.models import (
    UploadProfile,
    UploadProfileAIWorkflow,
    UploadProfileArea,
    UploadProfileAssignment,
    UploadProfileCamera,
    UploadProfileDisease,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_DIRECT_IMAGE


_SEQUENCE = count(1)


def test_direct_upload_service_creates_job_items_and_upload_records(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Direct Service Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Direct Service Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Direct Service Project {suffix}", code=f"DIRECT_SERVICE_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Direct Service Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Direct Service Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"direct_service_uploader_{suffix}",
        lab_units=[lab],
    )
    profile = UploadProfile(
        name=f"Direct Service Profile {suffix}",
        lab_unit_id=lab.id,
        project_id=project.id,
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
    )
    profile.assignments.append(UploadProfileAssignment(user_id=uploader.id, active=True))
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    db_session.add(profile)
    db_session.flush()

    result = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
            is_mydriatic=False,
            remarks="plain service remarks",
        ),
        files=[_png_file("direct-service.png")],
        upload_type="test direct image",
    )

    assert result.accepted_count == 1
    assert result.uploaded_count == 1
    assert result.duplicate_count == 0
    assert result.rejected_count == 0
    assert result.job.status == "completed"
    assert result.job.upload_kind == UPLOAD_KIND_DIRECT_IMAGE
    assert result.job.upload_profile_id == profile.id

    job = db_session.query(Job).filter_by(token=result.job.token).one()
    assert job.upload_type == "test direct image"
    item = db_session.query(JobItem).filter_by(job_id=job.id).one()
    assert item.state == "completed"
    assert item.source_type == "direct_image"
    assert item.source_id is not None
    assert item.source_uuid is not None

    upload = db_session.query(DirectImageUpload).filter_by(id=item.source_id).one()
    assert upload.remarks == "plain service remarks"

    payload = direct_upload_response_payload(result)
    assert payload["upload_token"] == job.token
    assert payload["accepted_count"] == 1
    assert payload["uploaded_count"] == 1
    assert payload["duplicate_count"] == 0


def test_direct_upload_duplicate_links_existing_image_and_task(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Direct Duplicate Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Direct Duplicate Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Direct Duplicate Project {suffix}", code=f"DIRECT_DUP_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Direct Duplicate Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Direct Duplicate Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"direct_duplicate_uploader_{suffix}",
        lab_units=[lab],
    )
    profile = UploadProfile(
        name=f"Direct Duplicate Profile {suffix}",
        lab_unit_id=lab.id,
        project_id=project.id,
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
    )
    profile.assignments.append(UploadProfileAssignment(user_id=uploader.id, active=True))
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    ai_model = AIModel(name=f"Duplicate Wadhwani {suffix}", version="test")
    ai_model.integration = AIModelIntegration(
        provider=WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    db_session.add(ai_model)
    db_session.flush()
    profile.ai_workflows.append(
        UploadProfileAIWorkflow(
            disease_id=disease.id,
            ai_model_id=ai_model.id,
            upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
            active=True,
        )
    )
    db_session.add(profile)
    db_session.flush()

    first = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
        ),
        files=[_png_file("same.png")],
    )
    first_item = db_session.query(JobItem).filter_by(job_id=first.job.id).one()

    duplicate = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
        ),
        files=[_png_file("same-again.png")],
    )

    duplicate_item = db_session.query(JobItem).filter_by(job_id=duplicate.job.id).one()
    assert duplicate.accepted_count == 1
    assert duplicate.uploaded_count == 0
    assert duplicate.duplicate_count == 1
    assert duplicate_item.state == "duplicate"
    assert duplicate_item.source_type == "direct_image"
    assert duplicate_item.source_id == first_item.source_id
    assert duplicate_item.source_uuid == first_item.source_uuid
    assert duplicate_item.task_id is not None
    assert duplicate.upload_ids_for_post_commit == ()
    assert db_session.query(GradingTask).filter_by(direct_image_upload_id=first_item.source_id).count() == 1
    assert direct_upload_response_payload(duplicate)["duplicate_count"] == 1


def test_direct_upload_duplicate_does_not_create_verification_or_requeue_running_inference(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Direct Duplicate Verify Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Direct Duplicate Verify Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Direct Duplicate Verify Project {suffix}", code=f"DIRECT_DUP_VERIFY_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Direct Duplicate Verify Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Direct Duplicate Verify Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"direct_duplicate_verify_uploader_{suffix}",
        lab_units=[lab],
    )
    profile = UploadProfile(
        name=f"Direct Duplicate Verify Profile {suffix}",
        lab_unit_id=lab.id,
        project_id=project.id,
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
    )
    profile.assignments.append(UploadProfileAssignment(user_id=uploader.id, active=True))
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    ai_model = AIModel(name=f"Duplicate Running Wadhwani {suffix}", version="test")
    ai_model.integration = AIModelIntegration(
        provider=WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    db_session.add(ai_model)
    db_session.flush()
    profile.ai_workflows.append(
        UploadProfileAIWorkflow(
            disease_id=disease.id,
            ai_model_id=ai_model.id,
            upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
            active=True,
        )
    )
    db_session.add(profile)
    db_session.flush()

    first = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
            verification_remarks="AI workflow verification marker",
            verification_user_id=uploader.id,
        ),
        files=[_png_file("verify-duplicate.png")],
    )
    first_item = db_session.query(JobItem).filter_by(job_id=first.job.id).one()
    db_session.add(
        AIInferenceRun(
            task_id=first_item.task_id,
            ai_model_id=ai_model.id,
            integration_id=ai_model.integration.id,
            source="internal",
            status="running",
        )
    )
    db_session.flush()

    duplicate = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
            verification_remarks="AI workflow verification marker",
            verification_user_id=uploader.id,
        ),
        files=[_png_file("verify-duplicate-again.png")],
    )

    duplicate_item = db_session.query(JobItem).filter_by(job_id=duplicate.job.id).one()
    assert duplicate_item.state == "duplicate"
    assert duplicate_item.source_id == first_item.source_id
    assert db_session.query(DirectImageUpload).count() == 1
    assert db_session.query(DirectImageVerify).count() == 1
    assert duplicate.inference_task_ids_for_post_commit == ()


def test_direct_upload_duplicate_with_existing_current_model_grade_is_not_queued(db_session, core_test_data):
    suffix = next(_SEQUENCE)
    hospital = Hospital(name=f"Direct Duplicate Grade Hospital {suffix}")
    db_session.add(hospital)
    db_session.flush()

    lab = LabUnit(name=f"Direct Duplicate Grade Lab {suffix}", hospital_id=hospital.id)
    project = Project(title=f"Direct Duplicate Grade Project {suffix}", code=f"DIRECT_DUP_GRADE_{suffix}", active=True)
    disease = db_session.merge(core_test_data["glaucoma"])
    camera = Camera(name=f"Direct Duplicate Grade Camera {suffix}", is_zip_upload_enabled=True)
    area = Area(name=f"Direct Duplicate Grade Area {suffix}")
    db_session.add_all([lab, project, camera, area])
    db_session.flush()

    uploader = UserFactory.create_by_role(
        db_session,
        "fileUploader",
        username=f"direct_duplicate_grade_uploader_{suffix}",
        lab_units=[lab],
    )
    profile = UploadProfile(
        name=f"Direct Duplicate Grade Profile {suffix}",
        lab_unit_id=lab.id,
        project_id=project.id,
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
        default_is_mydriatic=False,
    )
    profile.assignments.append(UploadProfileAssignment(user_id=uploader.id, active=True))
    profile.diseases.append(UploadProfileDisease(disease_id=disease.id, is_default=True))
    profile.cameras.append(UploadProfileCamera(camera_id=camera.id))
    profile.areas.append(UploadProfileArea(area_id=area.id))
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_DIRECT_IMAGE))
    ai_model = AIModel(name=f"Duplicate Grade Wadhwani {suffix}", version="test")
    ai_model.integration = AIModelIntegration(
        provider=WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    db_session.add(ai_model)
    db_session.flush()
    profile.ai_workflows.append(
        UploadProfileAIWorkflow(
            disease_id=disease.id,
            ai_model_id=ai_model.id,
            upload_kind=UPLOAD_KIND_DIRECT_IMAGE,
            active=True,
        )
    )
    db_session.add(profile)
    db_session.flush()

    first = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
        ),
        files=[_png_file("grade-duplicate.png")],
    )
    first_item = db_session.query(JobItem).filter_by(job_id=first.job.id).one()
    ai_system = db_session.query(User).filter_by(username="ai_system").one()
    grading = db_session.query(DiseaseGrading).filter_by(disease_id=disease.id).first()
    db_session.add(
        Grade(
            task_id=first_item.task_id,
            grader_user_id=ai_system.id,
            role_slot="ai",
            disease_grading_id=grading.id,
            ai_model_id=ai_model.id,
            time_taken=0,
        )
    )
    db_session.flush()

    duplicate = create_direct_upload_job(
        db=db_session,
        actor=DirectUploadActor(user_id=uploader.id, username=uploader.username, remote_addr="127.0.0.1"),
        request=DirectUploadJobRequest(
            profile_id=profile.id,
            project_id=project.id,
            lab_unit_id=lab.id,
            disease_id=disease.id,
            camera_id=camera.id,
            area_id=area.id,
        ),
        files=[_png_file("grade-duplicate-again.png")],
    )

    assert duplicate.duplicate_count == 1
    assert duplicate.inference_task_ids_for_post_commit == ()


def _png_file(filename: str) -> FileStorage:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(0, 255, 0)).save(buffer, format="PNG")
    buffer.seek(0)
    return FileStorage(stream=buffer, filename=filename, content_type="image/png")
