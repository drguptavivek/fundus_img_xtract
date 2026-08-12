from uuid import uuid4

from models import EncounterSetImage, Hospital, LabUnit, PatientEncounters


def test_image_hospital_follows_parent_encounter_lab(db_session, core_test_data):
    encounter = PatientEncounters(
        name="Custody Test",
        patient_id=f"CUSTODY-{uuid4().hex[:8]}",
        capture_date="2026-08-12",
        lab_unit_id=core_test_data["lab_unit"].id,
        is_set_based=True,
    )
    db_session.add(encounter)
    db_session.flush()

    # The database must correct missing or caller-supplied custody values.
    image = EncounterSetImage(
        patient_encounter_id=encounter.id,
        spatial_position=1,
        original_filename="custody.jpg",
        folder_rel="tests/custody",
        hospital_id=None,
    )
    db_session.add(image)
    db_session.flush()
    db_session.refresh(image)
    assert image.hospital_id == core_test_data["hospital"].id

    new_hospital = Hospital(name=f"Custody Hospital {uuid4()}")
    db_session.add(new_hospital)
    db_session.flush()
    new_lab = LabUnit(name=f"Custody Lab {uuid4()}", hospital_id=new_hospital.id)
    db_session.add(new_lab)
    db_session.flush()

    encounter.lab_unit_id = new_lab.id
    db_session.flush()
    db_session.refresh(image)
    assert image.hospital_id == new_hospital.id
