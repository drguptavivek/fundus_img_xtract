from __future__ import annotations

from datetime import date
from uuid import uuid4

from encounter_sets.models import EncounterSetAttachment
from models import (
    AIInferenceRun,
    AIModel,
    AIModelDisease,
    AIModelIntegration,
    EncounterSetImage,
    GradingTask,
    PatientEncounters,
    Project,
)
from remote_inference.models import DiseaseReportLinkage, ProjectAutomatedRemoteInferenceRule
from services.encounter_set_ai_inference import (
    create_wadhwani_task_ids_for_encounter,
    encounter_ids_from_ingest_result,
    encounter_set_report_evidence,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from upload_profiles.models import UploadProfile, UploadProfileKind
from upload_profiles.service import UPLOAD_KIND_ENCOUNTER_SET


def test_encounter_ids_from_project_sync_ingest_groups_are_requeued_after_recovery():
    result = {
        "groups": [
            {
                "ingest": {
                    "exams": [
                        {
                            "patient_encounter_id": 3988,
                            "images": [
                                {"patient_encounter_id": 3988, "status": "downloaded"},
                                {"patient_encounter_id": 3993, "status": "downloaded"},
                            ],
                        }
                    ]
                }
            },
            {"ingest": {"exams": [{"patient_encounter_id": 3993, "images": []}]}},
        ]
    }

    assert encounter_ids_from_ingest_result(result) == [3988, 3993]


def test_encounter_ids_from_ingest_result_preserves_direct_sync_shape():
    result = {
        "exams": [
            {
                "patient_encounter_id": 17,
                "images": [{"patient_encounter_id": 17}],
                "reports": [{"patient_encounter_id": 18}],
            }
        ]
    }

    assert encounter_ids_from_ingest_result(result) == [17, 18]


def _encounter_set_wadhwani_profile(db_session, glaucoma):
    project = Project(title=f"Wadhwani Project {uuid4()}", code=f"WAI{str(uuid4())[:8]}", active=True)
    profile = UploadProfile(
        name=f"EncounterSet Wadhwani {uuid4()}",
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
    )
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_ENCOUNTER_SET))
    ai_model = AIModel(name=f"Wadhwani EncounterSet {uuid4()}", version="test")
    ai_model.integration = AIModelIntegration(
        provider=WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    db_session.add_all([project, profile, ai_model])
    db_session.flush()
    db_session.add(
        ProjectAutomatedRemoteInferenceRule(
            project_id=project.id,
            disease_id=glaucoma.id,
            ai_model_id=ai_model.id,
            upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
            trigger_timing="on_image_received",
            encounter_eligibility="always",
            image_selection="disc_focused_images",
            active=True,
        )
    )
    db_session.flush()
    profile._test_project_id = project.id
    return profile, ai_model


def _encounter_with_image(db_session, core_test_data, profile, *, metadata, project_id=None):
    lab_unit = core_test_data["lab_unit"]
    encounter = PatientEncounters(
        name=f"Disc Evidence Encounter {uuid4()}",
        patient_id=f"mrn-{uuid4()}",
        capture_date="2026-07-29",
        capture_date_dt=date(2026, 7, 29),
        is_set_based=True,
        lab_unit_id=lab_unit.id,
        project_id=project_id or getattr(profile, "_test_project_id", None),
        upload_profile_id=profile.id,
    )
    db_session.add(encounter)
    db_session.flush()
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename=f"{uuid4()}.jpg",
        folder_rel="encounter-set-tests",
        hospital_id=lab_unit.hospital_id,
        camera_id=core_test_data["camera"].id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
        metadata_json=metadata,
    )
    db_session.add(image)
    db_session.flush()
    return encounter, image


def _remote_policy_project(db_session, core_test_data, glaucoma, *, trigger_timing, encounter_eligibility, image_selection):
    project = Project(title=f"Remote Policy Project {uuid4()}", code=f"RIP{str(uuid4())[:8]}", active=True)
    profile = UploadProfile(
        name=f"Remote Policy Profile {uuid4()}",
        active=True,
        allow_mydriatic=True,
        allow_non_mydriatic=True,
    )
    profile.upload_kinds.append(UploadProfileKind(upload_kind=UPLOAD_KIND_ENCOUNTER_SET))
    ai_model = AIModel(name=f"Remote Policy Wadhwani {uuid4()}", version="test")
    ai_model.integration = AIModelIntegration(
        provider=WADHWANI_PROVIDER,
        is_enabled=True,
        client_id="test-client",
        bearer_token="test-token",
    )
    ai_model.disease_links.append(AIModelDisease(disease_id=glaucoma.id, active=True))
    rule = ProjectAutomatedRemoteInferenceRule(
            project=project,
            disease_id=glaucoma.id,
            ai_model=ai_model,
            upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
            trigger_timing=trigger_timing,
            encounter_eligibility=encounter_eligibility,
            image_selection=image_selection,
            active=True,
        )
    db_session.add_all([project, profile, ai_model, rule])
    db_session.flush()
    return project, profile, ai_model


def test_disc_focused_remidio_image_satisfies_glaucoma_wadhwani_policy(db_session, core_test_data):
    profile, _ai_model = _encounter_set_wadhwani_profile(db_session, core_test_data["glaucoma"])
    encounter, image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"fundus_field": "macula", "image_segment": "optic_disc"},
    )

    evidence = encounter_set_report_evidence(encounter)
    task_ids = create_wadhwani_task_ids_for_encounter(db_session, encounter)

    assert evidence == {"glaucoma", "glaucoma_disc_image"}
    assert len(task_ids) == 1
    task = db_session.get(GradingTask, task_ids[0])
    assert task.encounter_set_image_id == image.id
    assert task.disease_id == core_test_data["glaucoma"].id
    assert task.task_source == "encounter_set_ai_inference"


def test_non_disc_remidio_image_does_not_satisfy_glaucoma_wadhwani_policy(db_session, core_test_data):
    profile, _ai_model = _encounter_set_wadhwani_profile(db_session, core_test_data["glaucoma"])
    encounter, _image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"fundus_field": "macula", "image_segment": "posterior"},
    )

    assert encounter_set_report_evidence(encounter) == set()
    assert create_wadhwani_task_ids_for_encounter(db_session, encounter) == []


def test_disc_image_evidence_queues_only_disc_focused_images(db_session, core_test_data):
    profile, _ai_model = _encounter_set_wadhwani_profile(db_session, core_test_data["glaucoma"])
    encounter, disc_image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"image_segment": "disc centered"},
    )
    macula_image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename=f"{uuid4()}.jpg",
        folder_rel="encounter-set-tests",
        hospital_id=core_test_data["lab_unit"].hospital_id,
        camera_id=core_test_data["camera"].id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
        metadata_json={"image_segment": "posterior", "fundus_field": "macula"},
    )
    db_session.add(macula_image)
    db_session.flush()

    task_ids = create_wadhwani_task_ids_for_encounter(db_session, encounter)

    assert len(task_ids) == 1
    task = db_session.get(GradingTask, task_ids[0])
    assert task.encounter_set_image_id == disc_image.id


def test_project_rule_image_selection_remains_disc_focused_when_report_exists(db_session, core_test_data):
    profile, _ai_model = _encounter_set_wadhwani_profile(db_session, core_test_data["glaucoma"])
    encounter, disc_image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"image_segment": "disc centered"},
    )
    macula_image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename=f"{uuid4()}.jpg",
        folder_rel="encounter-set-tests",
        hospital_id=core_test_data["lab_unit"].hospital_id,
        camera_id=core_test_data["camera"].id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
        metadata_json={"fundus_field": "macula"},
    )
    peripheral_image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=3,
        original_filename=f"{uuid4()}.jpg",
        folder_rel="encounter-set-tests",
        hospital_id=core_test_data["lab_unit"].hospital_id,
        camera_id=core_test_data["camera"].id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
        metadata_json={"fundus_field": "peripheral retina", "image_segment": "nasal"},
    )
    attachment = EncounterSetAttachment(
        patient_encounter_id=encounter.id,
        asset_kind="pdf",
        original_filename="glaucoma-report.pdf",
        stored_filename="glaucoma-report.pdf",
        folder_rel="encounter-set-tests",
        mime_type="application/pdf",
        metadata_json={"remidio_report_type": "glaucoma"},
    )
    db_session.add_all([macula_image, peripheral_image, attachment])
    db_session.flush()

    task_ids = create_wadhwani_task_ids_for_encounter(db_session, encounter)
    task_image_ids = {
        db_session.get(GradingTask, task_id).encounter_set_image_id
        for task_id in task_ids
    }

    assert task_image_ids == {disc_image.id}
    assert peripheral_image.id not in task_image_ids


def test_existing_queued_wadhwani_run_is_not_requeued(db_session, core_test_data):
    profile, ai_model = _encounter_set_wadhwani_profile(db_session, core_test_data["glaucoma"])
    encounter, _image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"image_segment": "disc centered"},
    )
    task_ids = create_wadhwani_task_ids_for_encounter(db_session, encounter)
    db_session.add(
        AIInferenceRun(
            task_id=task_ids[0],
            ai_model_id=ai_model.id,
            status="queued",
        )
    )
    db_session.flush()

    assert create_wadhwani_task_ids_for_encounter(db_session, encounter) == []


def test_remote_policy_trigger_and_image_selection_control_wadhwani_tasks(db_session, core_test_data):
    project, profile, _ai_model = _remote_policy_project(
        db_session,
        core_test_data,
        core_test_data["glaucoma"],
        trigger_timing="on_image_received",
        encounter_eligibility="always",
        image_selection="macula_focused_images",
    )
    encounter, _disc_image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"image_segment": "disc centered"},
        project_id=project.id,
    )
    macula_image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=2,
        original_filename=f"{uuid4()}.jpg",
        folder_rel="encounter-set-tests",
        hospital_id=core_test_data["lab_unit"].hospital_id,
        camera_id=core_test_data["camera"].id,
        asset_kind="clinical_image",
        creates_task=True,
        visible_to_grader=True,
        is_not_gradable=False,
        metadata_json={"fundus_field": "macula"},
    )
    db_session.add(macula_image)
    db_session.flush()

    assert create_wadhwani_task_ids_for_encounter(db_session, encounter, trigger_timing="after_verification") == []
    task_ids = create_wadhwani_task_ids_for_encounter(db_session, encounter, trigger_timing="on_image_received")

    assert len(task_ids) == 1
    task = db_session.get(GradingTask, task_ids[0])
    assert task.encounter_set_image_id == macula_image.id


def test_matching_report_policy_requires_explicit_disease_report_linkage(db_session, core_test_data):
    project, profile, _ai_model = _remote_policy_project(
        db_session,
        core_test_data,
        core_test_data["glaucoma"],
        trigger_timing="on_report_received",
        encounter_eligibility="if_matching_report_present",
        image_selection="disc_or_macula_images",
    )
    encounter, disc_image = _encounter_with_image(
        db_session,
        core_test_data,
        profile,
        metadata={"image_segment": "disc centered"},
        project_id=project.id,
    )
    attachment = EncounterSetAttachment(
        patient_encounter_id=encounter.id,
        asset_kind="pdf",
        original_filename="glaucoma-report.pdf",
        stored_filename="glaucoma-report.pdf",
        folder_rel="encounter-set-tests",
        mime_type="application/pdf",
        metadata_json={"remidio_report_type": "glaucoma"},
    )
    db_session.add(attachment)
    db_session.flush()

    assert create_wadhwani_task_ids_for_encounter(db_session, encounter, trigger_timing="on_report_received") == []

    db_session.add(
        DiseaseReportLinkage(
            disease_id=core_test_data["glaucoma"].id,
            report_source="remidio",
            report_type="glaucoma",
            active=True,
        )
    )
    db_session.flush()
    task_ids = create_wadhwani_task_ids_for_encounter(db_session, encounter, trigger_timing="on_report_received")

    assert len(task_ids) == 1
    task = db_session.get(GradingTask, task_ids[0])
    assert task.encounter_set_image_id == disc_image.id
