from models import Disease, PatientEncounters, Project, ProjectReferralDisease
from encounter_sets.models import EncounterSetAttachment
from services.encounter_referral_suggestion import (
    REFERRAL_SUGGESTION_MISSING,
    REFERRAL_SUGGESTION_NO,
    REFERRAL_SUGGESTION_YES,
    derive_referral_suggestion_from_attachment_metadata,
    derive_referral_positive_diseases_from_attachment_metadata,
    normalize_referral_positive_diseases,
    update_encounter_referral_suggestion_from_attachments,
)


def test_derive_referral_suggestion_uses_structured_remidio_flags():
    assert (
        derive_referral_suggestion_from_attachment_metadata(
            [
                {"ai_suggested_refer": False, "gma_suggested_refer": False},
                {"refer_required": True},
            ]
        )
        == REFERRAL_SUGGESTION_YES
    )
    assert (
        derive_referral_suggestion_from_attachment_metadata(
            [{"ai_suggested_refer": False, "gma_suggested_refer": False}]
        )
        == REFERRAL_SUGGESTION_NO
    )


def test_derive_referral_suggestion_uses_parsed_remidio_ocr_text():
    assert (
        derive_referral_suggestion_from_attachment_metadata(
            [
                {
                    "ocr": {
                        "glaucoma_report": {
                            "glaucoma_data": {
                                "result": "Disc Suspect (High vCDR) - Referral suggested for further evaluation"
                            }
                        }
                    }
                }
            ]
        )
        == REFERRAL_SUGGESTION_YES
    )
    assert (
        derive_referral_suggestion_from_attachment_metadata(
            [
                {
                    "ocr": {
                        "dr_report": {"dr_data": {"result": "No signs of DR detected. Re-examine after 12 months."}},
                        "glaucoma_report": {
                            "glaucoma_data": {"result": "No Referable Glaucoma - Re-examine after 12 months"}
                        },
                    }
                }
            ]
        )
        == REFERRAL_SUGGESTION_NO
    )
    assert derive_referral_suggestion_from_attachment_metadata([{"ocr": {"status": "completed"}}]) == REFERRAL_SUGGESTION_MISSING


def test_derive_referral_suggestion_handles_combined_dr_amd_negative_text():
    assert (
        derive_referral_suggestion_from_attachment_metadata(
            [
                {
                    "ocr": {
                        "dr_report": {
                            "dr_data": {
                                "result": "No signs of DR or AMD detected. Re-examine after 12 months for AI"
                            }
                        },
                        "amd_report": {
                            "amd_data": {
                                "result": "No signs of DR or AMD detected. Re-examine after 12 months for AI"
                            }
                        },
                    }
                }
            ]
        )
        == REFERRAL_SUGGESTION_NO
    )


def test_derive_referral_positive_diseases_uses_parsed_remidio_ocr_text():
    assert derive_referral_positive_diseases_from_attachment_metadata(
        [
            {
                "ocr": {
                    "dr_report": {"dr_data": {"result": "No signs of DR detected."}},
                    "amd_report": {"amd_data": {"result": "Signs of AMD detected. Examples of lesions are highlighted."}},
                    "glaucoma_report": {
                        "glaucoma_data": {
                            "result": "Disc Suspect (High vCDR) - Referral suggested for further evaluation"
                        }
                    },
                }
            }
        ]
    ) == ["AMD", "Glaucoma"]


def test_normalize_referral_positive_diseases_accepts_free_text_lists_and_comma_values():
    assert normalize_referral_positive_diseases(["DR, dry AMD", "corneal opacity", "dr"]) == [
        "DR",
        "dry AMD",
        "corneal opacity",
    ]
    assert normalize_referral_positive_diseases("strabismus; wet AMD, neoplasm") == [
        "strabismus",
        "wet AMD",
        "neoplasm",
    ]


def test_update_encounter_referral_suggestion_from_attachments(db_session):
    encounter = PatientEncounters(
        name="Referral Test",
        patient_id="MRN-REF",
        capture_date="2026-07-29",
        is_set_based=True,
    )
    db_session.add(encounter)
    db_session.flush()
    db_session.add(
        EncounterSetAttachment(
            patient_encounter_id=encounter.id,
            asset_kind="pdf",
            original_filename="report.pdf",
            stored_filename="report.pdf",
            folder_rel="files/test",
            metadata_json={
                "ocr": {
                    "dr_report": {"dr_data": {"result": "Signs of DR detected. Examples of lesions are highlighted."}}
                }
            },
        )
    )
    db_session.flush()

    suggestion = update_encounter_referral_suggestion_from_attachments(db_session, encounter.id)
    db_session.refresh(encounter)

    assert suggestion == REFERRAL_SUGGESTION_YES
    assert encounter.referral_suggestion == REFERRAL_SUGGESTION_YES
    assert encounter.referral_positive_diseases_json == ["DR"]
    assert encounter.referral_suggestion_updated_at is not None


def test_update_filters_ocr_positive_diseases_to_project_options(db_session):
    project = Project(title="OCR Referral Project", code="OCR_REFERRAL", active=True)
    dr = Disease(name="OCR Referral DR", remidio_ocr_linkage="dr")
    db_session.add_all([project, dr])
    db_session.flush()
    db_session.add(ProjectReferralDisease(project_id=project.id, disease_id=dr.id))
    encounter = PatientEncounters(
        name="Project Referral Test",
        patient_id="MRN-PROJECT-REF",
        capture_date="2026-08-11",
        is_set_based=True,
        project_id=project.id,
    )
    db_session.add(encounter)
    db_session.flush()
    db_session.add(
        EncounterSetAttachment(
            patient_encounter_id=encounter.id,
            asset_kind="pdf",
            original_filename="combined-report.pdf",
            stored_filename="combined-report.pdf",
            folder_rel="files/test",
            metadata_json={
                "ocr": {
                    "dr_report": {
                        "dr_data": {"result": "Signs of DR or AMD detected."}
                    },
                    "amd_report": {
                        "amd_data": {"result": "Signs of DR or AMD detected."}
                    },
                }
            },
        )
    )
    db_session.flush()

    suggestion = update_encounter_referral_suggestion_from_attachments(
        db_session,
        encounter.id,
    )
    db_session.refresh(encounter)

    assert suggestion == REFERRAL_SUGGESTION_YES
    assert encounter.referral_positive_diseases_json == ["OCR Referral DR"]
