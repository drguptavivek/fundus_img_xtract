from __future__ import annotations

from datetime import date
from uuid import uuid4

from models import (
    AIInferenceRun,
    AIModel,
    AIModelIntegration,
    EncounterSetImage,
    GradingTask,
    PatientEncounters,
)
from services.encounter_set_ai_inference import (
    create_wadhwani_task_ids_for_encounter,
    encounter_set_report_evidence,
)
from services.wadhwani_glaucoma_inference import WADHWANI_PROVIDER
from upload_profiles.models import UploadProfile, UploadProfileAIWorkflow, UploadProfileKind
from upload_profiles.service import UPLOAD_KIND_ENCOUNTER_SET


def _encounter_set_wadhwani_profile(db_session, glaucoma):
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
    db_session.add_all([profile, ai_model])
    db_session.flush()
    profile.ai_workflows.append(
        UploadProfileAIWorkflow(
            disease_id=glaucoma.id,
            ai_model_id=ai_model.id,
            upload_kind=UPLOAD_KIND_ENCOUNTER_SET,
            auto_inference_policy="remidio_glaucoma_report_present",
            active=True,
        )
    )
    db_session.flush()
    return profile, ai_model


def _encounter_with_image(db_session, core_test_data, profile, *, metadata):
    lab_unit = core_test_data["lab_unit"]
    encounter = PatientEncounters(
        name=f"Disc Evidence Encounter {uuid4()}",
        patient_id=f"mrn-{uuid4()}",
        capture_date="2026-07-29",
        capture_date_dt=date(2026, 7, 29),
        is_set_based=True,
        lab_unit_id=lab_unit.id,
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
