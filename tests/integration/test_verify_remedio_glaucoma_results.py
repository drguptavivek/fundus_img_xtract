from sqlalchemy import func

from models import GlaucomaResultsCleaned, PatientEncounters
from verify_remedio.access import classical_verification_rows


def test_unique_glaucoma_patient_count_can_be_scoped(db_session, admin_user):
    query = db_session.query(
        func.count(func.distinct(PatientEncounters.patient_id))
    ).select_from(GlaucomaResultsCleaned)
    query = classical_verification_rows(db_session, query, admin_user).join(
        PatientEncounters,
        GlaucomaResultsCleaned.patient_encounter_id == PatientEncounters.id,
    )

    assert query.scalar() == 0
