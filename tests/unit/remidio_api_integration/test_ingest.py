from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4

from PIL import Image

from models import (
    EncounterFile,
    EncounterFilePDF,
    Project,
    RemidioConnection,
    RemidioExam,
    RemidioImage,
    RemidioReport,
    RemidioRoutingRule,
)
from remidio_api_integration.ingest import ingest_staged_files


class FakeRemidioClient:
    def download_file(self, file_url, *, max_bytes):
        if file_url.endswith(".pdf"):
            return b"%PDF-1.4\n%test\n", "application/pdf"
        image = Image.new("RGB", (16, 16), color=(255, 0, 0))
        output = BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue(), "image/jpeg"


def test_ingest_staged_files_creates_encounter_image_pdf_and_task(db_session, core_test_data, tmp_path, monkeypatch):
    from remidio_api_integration import ingest as ingest_module
    from models import GradingTask

    monkeypatch.setattr(ingest_module, "IMAGE_DIR", tmp_path / "images")
    monkeypatch.setattr(ingest_module, "PDF_DIR", tmp_path / "pdfs")

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

    rule = RemidioRoutingRule(
        remidio_connection_id=connection.id,
        site_custom_identifier="rpc_test",
        remidio_device_type="FOP",
        project_id=project.id,
        lab_unit_id=core_test_data["lab_unit"].id,
        camera_id=core_test_data["camera"].id,
        default_disease_id=core_test_data["dr"].id,
        active=True,
    )
    db_session.add(rule)

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
    assert result["summary"]["tasks_created"] == 1
    assert exam.patient_encounter_id is not None
    assert image.encounter_file_id is not None
    assert report.encounter_file_pdf_id is not None

    encounter_file = db_session.get(EncounterFile, image.encounter_file_id)
    pdf = db_session.get(EncounterFilePDF, report.encounter_file_pdf_id)
    assert encounter_file.project_id == project.id
    assert encounter_file.lab_unit_id == core_test_data["lab_unit"].id
    assert encounter_file.camera_id == core_test_data["camera"].id
    assert encounter_file.eye_side == "right"
    assert pdf.project_id == project.id
    assert (tmp_path / "images" / "2026_04_01" / encounter_file.filename).exists()
    assert (tmp_path / "pdfs" / "2026_04_01" / pdf.filename).exists()
    assert db_session.query(GradingTask).filter_by(encounter_file_id=encounter_file.id).count() == 1
