from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from PIL import Image

from models import (
    Disease,
    EncounterSetAttachment,
    EncounterSetImage,
    EncounterSetType,
    Project,
    RemidioConnection,
    RemidioExam,
    RemidioImage,
    RemidioReport,
)
from remidio_api_integration.models import ProjectUploadProfileRemidioApiBinding, RemidioApiSourceRule
from remidio_api_integration.ingest import ingest_staged_files
from upload_profiles.models import (
    PatientEncounterTargetDisease,
    ProjectUploadProfile,
    UploadProfile,
    UploadProfileEncounterSetType,
    UploadProfileEncounterSetTypeImageGradingScheme,
    UploadProfileKind,
)
from upload_profiles.service import UPLOAD_KIND_ENCOUNTER_SET


class FakeRemidioClient:
    def download_file(self, file_url, *, max_bytes):
        if file_url.endswith(".pdf"):
            return b"%PDF-1.4\n%test\n", "application/pdf"
        image = Image.new("RGB", (16, 16), color=(255, 0, 0))
        output = BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue(), "image/jpeg"


def test_ingest_staged_files_creates_encounter_set_image_pdf_and_targets(db_session, core_test_data, tmp_path, monkeypatch):
    from remidio_api_integration import ingest as ingest_module

    monkeypatch.setattr(ingest_module, "BASE_DIR", tmp_path)

    project = Project(
        title=f"Remidio Test Project {uuid4()}",
        code=f"RT-{uuid4().hex[:8]}",
        active=True,
    )
    db_session.add(project)
    db_session.flush()

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
    project_profile = ProjectUploadProfile(project=project, profile=upload_profile, active=True)
    source_rule = RemidioApiSourceRule(
        remidio_connection_id=connection.id,
        site_custom_identifier="rpc_test",
        remidio_device_type="FOP",
        active=True,
    )
    db_session.add_all([encounter_scheme, encounter_set_type, upload_profile, project_profile, source_rule])
    db_session.flush()

    binding = ProjectUploadProfileRemidioApiBinding(
        project_upload_profile_id=project_profile.id,
        remidio_api_source_rule_id=source_rule.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        camera_id=core_test_data["camera"].id,
        active_from_date=datetime(2026, 1, 1, tzinfo=timezone.utc).date(),
        active=True,
    )
    db_session.add(binding)

    exam = RemidioExam(
        remidio_connection_id=connection.id,
        remidio_exam_id="exam-1",
        site_custom_identifier="rpc_test",
        remidio_patient_id="patient-1",
        remidio_patient_mrn="mrn-1",
        exam_local_id="local-1",
        device_types=["FOP"],
        exam_state="ACTIVE",
        exam_date=datetime(2026, 4, 1, 8, 30, tzinfo=timezone.utc),
        pull_source="test",
    )
    db_session.add(exam)
    db_session.flush()

    image = RemidioImage(
        remidio_exam_id=exam.id,
        remidio_image_id="image-1",
        device_type="FOP",
        image_bucket="fopImages",
        image_variant="STANDARD",
        laterality="RIGHT",
        remidio_path="https://files.example.test/image-1.jpg",
    )
    report = RemidioReport(
        remidio_exam_id=exam.id,
        remidio_report_id="report-1",
        report_type="report",
        remidio_path="https://files.example.test/report-1.pdf",
    )
    db_session.add_all([image, report])
    db_session.flush()

    result = ingest_staged_files(
        db_session,
        connection_id=connection.id,
        client=FakeRemidioClient(),
        payload={"limit": 10},
    )

    db_session.refresh(exam)
    db_session.refresh(image)
    db_session.refresh(report)

    assert result["summary"]["encounters_created"] == 1
    assert result["summary"]["images_downloaded"] == 1
    assert result["summary"]["reports_downloaded"] == 1
    assert result["summary"]["tasks_created"] == 0
    assert exam.patient_encounter_id is not None
    assert image.encounter_set_image_id is not None
    assert report.encounter_set_attachment_id is not None

    encounter_image = db_session.get(EncounterSetImage, image.encounter_set_image_id)
    attachment = db_session.get(EncounterSetAttachment, report.encounter_set_attachment_id)
    assert encounter_image.project_id == project.id
    assert encounter_image.camera_id == core_test_data["camera"].id
    assert encounter_image.hospital_id == core_test_data["lab_unit"].hospital_id
    assert encounter_image.asset_kind == "clinical_image"
    assert encounter_image.creates_task is True
    assert encounter_image.metadata_json["remidio_image_id"] == "image-1"
    assert attachment.project_id == project.id
    assert attachment.upload_profile_id == upload_profile.id
    assert attachment.asset_kind == "pdf"
    assert attachment.creates_task is False
    assert (tmp_path / encounter_image.folder_rel / encounter_image.original_filename).exists()
    assert (tmp_path / attachment.folder_rel / attachment.stored_filename).exists()
    assert (
        db_session.query(PatientEncounterTargetDisease)
        .filter_by(patient_encounter_id=exam.patient_encounter_id, disease_id=core_test_data["dr"].id, is_default=True)
        .count()
        == 1
    )

    duplicate_report = RemidioReport(
        remidio_exam_id=exam.id,
        remidio_report_id="report-1",
        report_type="aiReport",
        remidio_path="https://files.example.test/report-1.pdf",
    )
    db_session.add(duplicate_report)
    db_session.flush()

    second_result = ingest_staged_files(
        db_session,
        connection_id=connection.id,
        client=FakeRemidioClient(),
        payload={"limit": 10},
    )

    db_session.refresh(duplicate_report)
    assert second_result["summary"]["reports_downloaded"] == 0
    assert second_result["summary"]["reports_skipped"] == 2
    assert duplicate_report.encounter_set_attachment_id == attachment.id
    assert (
        db_session.query(EncounterSetAttachment)
        .filter_by(patient_encounter_id=exam.patient_encounter_id)
        .count()
        == 1
    )
