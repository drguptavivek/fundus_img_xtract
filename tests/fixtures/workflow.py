"""
Workflow fixtures for testing the complete grading pipeline.

This module provides fixtures for creating complete workflow scenarios:
- Encounters → Images → Tasks → Grades → Consensus → Review

These fixtures work with the seeded disease gradings from migrations.
All queries use NAME-based lookups instead of ID to be resilient to ID changes.

All fixtures are function-scoped (default) to ensure test isolation.
"""
import pytest
from typing import Optional, List, Dict, Any
from models import (
    DiseaseGrading,
    GradingsFeatures,
    AIModel,
    Grade,
    Consensus,
    User,
    GradingTask,
    Disease,
    LabUnit,
)
from auth.utils import utcnow


def _get_grading_by_name(db_session, disease_name: str, impression: str) -> Optional[DiseaseGrading]:
    """
    Helper to query for a disease grading by disease name and impression.

    This is more resilient than querying by ID since IDs may vary
    between production and test environments.
    """
    return db_session.query(DiseaseGrading).join(Disease).filter(
        Disease.name == disease_name,
        DiseaseGrading.impression == impression
    ).first()


# ============================================================================
# DISEASE GRADING FIXTURES (Query by name, not ID)
# ============================================================================

@pytest.fixture
def disease_grading_glaucoma_normal(db_session):
    """Query for Normal Glaucoma grading (by name)."""
    return _get_grading_by_name(db_session, 'Glaucoma', 'Normal')


@pytest.fixture
def disease_grading_glaucoma_suspect(db_session):
    """Query for Suspect Glaucoma grading (by name)."""
    return _get_grading_by_name(db_session, 'Glaucoma', 'Suspect')


@pytest.fixture
def disease_grading_glaucoma(db_session):
    """Query for definite Glaucoma grading (by name)."""
    return _get_grading_by_name(db_session, 'Glaucoma', 'Glaucoma')


@pytest.fixture
def disease_grading_dr_no_dr(db_session):
    """Query for No DR grading (by name)."""
    return _get_grading_by_name(db_session, 'DR', 'No DR')


@pytest.fixture
def disease_grading_dr_mild(db_session):
    """Query for Mild DR grading (by name)."""
    return _get_grading_by_name(db_session, 'DR', 'Mild DR')


@pytest.fixture
def disease_grading_dr_moderate(db_session):
    """Query for Moderate NPDR grading (by name)."""
    return _get_grading_by_name(db_session, 'DR', 'Moderate NPDR')


@pytest.fixture
def disease_grading_with_features(db_session):
    """Query for Suspect Glaucoma grading which has features (by name)."""
    grading = _get_grading_by_name(db_session, 'Glaucoma', 'Suspect')
    if not grading:
        raise ValueError("Suspect Glaucoma grading not found.")
    features = db_session.query(GradingsFeatures).filter_by(disease_grading_id=grading.id).all()
    if not features:
        raise ValueError("Expected features for Suspect grading, but none found.")
    return grading


# Legacy aliases for backward compatibility
disease_grading_glaucoma_mild = disease_grading_glaucoma_suspect
disease_grading_glaucoma_moderate = disease_grading_glaucoma
disease_grading_glaucoma_severe = disease_grading_glaucoma
disease_grading_dr_severe = disease_grading_dr_moderate


# ============================================================================
# AI MODEL FIXTURES
# ============================================================================

@pytest.fixture
def ai_model_glaucoma_v1(db_session):
    """Query for GlaucomaNet v1.0 AI model."""
    return db_session.query(AIModel).filter_by(name='GlaucomaNet').first()


@pytest.fixture
def ai_model_dr_v2(db_session):
    """Query for DRNet v2.0 AI model."""
    return db_session.query(AIModel).filter_by(name='DRNet').first()


# ============================================================================
# GRADE CREATION FIXTURES
# ============================================================================

@pytest.fixture
def create_resident_grade(db_session):
    """
    Factory fixture to create a resident grade for a task.

    Usage:
        grade = create_resident_grade(task, user, grading, comment="Good")
    """
    def _create_grade(
        task: GradingTask,
        user: User,
        grading: DiseaseGrading,
        comment: Optional[str] = None,
        time_taken: Optional[float] = None,
        selected_features: Optional[List[int]] = None,
    ) -> Grade:
        grade = Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot='resident',
            disease_grading_id=grading.id,
            comment=comment,
            time_taken=time_taken or 120.0,
            start_time=utcnow(),
            disease_name=grading.disease.name,
            grade_name=grading.impression,
            grade_description=grading.guidelines,
        )

        if selected_features:
            import json
            grade.selected_features_json = json.dumps([
                {'id': f_id, 'sr_no': i + 1}
                for i, f_id in enumerate(selected_features)
            ])

        db_session.add(grade)
        db_session.flush()
        return grade

    return _create_grade


@pytest.fixture
def create_resident2_grade(db_session):
    """Factory fixture to create a resident2 grade for a task."""
    def _create_grade(
        task: GradingTask,
        user: User,
        grading: DiseaseGrading,
        comment: Optional[str] = None,
        time_taken: Optional[float] = None,
    ) -> Grade:
        grade = Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot='resident2',
            disease_grading_id=grading.id,
            comment=comment,
            time_taken=time_taken or 90.0,
            start_time=utcnow(),
            disease_name=grading.disease.name,
            grade_name=grading.impression,
            grade_description=grading.guidelines,
        )
        db_session.add(grade)
        db_session.flush()
        return grade

    return _create_grade


@pytest.fixture
def create_arbitrator_grade(db_session):
    """Factory fixture to create an arbitrator grade for a task."""
    def _create_grade(
        task: GradingTask,
        user: User,
        grading: DiseaseGrading,
        comment: Optional[str] = None,
        time_taken: Optional[float] = None,
    ) -> Grade:
        grade = Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot='arbitrator',
            disease_grading_id=grading.id,
            comment=comment,
            time_taken=time_taken or 150.0,
            start_time=utcnow(),
            disease_name=grading.disease.name,
            grade_name=grading.impression,
            grade_description=grading.guidelines,
        )
        db_session.add(grade)
        db_session.flush()
        return grade

    return _create_grade


@pytest.fixture
def create_ai_grade(db_session):
    """Factory fixture to create an AI grade for a task."""
    def _create_grade(
        task: GradingTask,
        ai_model: AIModel,
        grading: DiseaseGrading,
        comment: Optional[str] = None,
    ) -> Grade:
        ai_user = db_session.query(User).filter_by(username='ai_system').first()

        grade = Grade(
            task_id=task.id,
            grader_user_id=ai_user.id,
            role_slot='ai',
            disease_grading_id=grading.id,
            comment=comment,
            time_taken=0,
            start_time=utcnow(),
            disease_name=grading.disease.name,
            grade_name=grading.impression,
            grade_description=grading.guidelines,
            ai_model_id=ai_model.id,
            ai_model_name=ai_model.name,
            ai_model_version=ai_model.version,
        )
        db_session.add(grade)
        db_session.flush()
        return grade

    return _create_grade


@pytest.fixture
def create_review_grade(db_session):
    """
    Factory fixture to create a review grade for a task.
    Also updates the original grade with AI review status.
    """
    def _create_grade(
        task: GradingTask,
        user: User,
        original_grade: Grade,
        approved: bool = True,
        comment: Optional[str] = None,
    ) -> Grade:
        grade = Grade(
            task_id=task.id,
            grader_user_id=user.id,
            role_slot='review',
            disease_grading_id=original_grade.disease_grading_id,
            comment=comment or ('Approved' if approved else 'Rejected'),
            time_taken=30.0,
            start_time=utcnow(),
            disease_name=original_grade.disease_name,
            grade_name=original_grade.grade_name,
            grade_description=original_grade.grade_description,
        )
        db_session.add(grade)
        db_session.flush()

        original_grade.ai_review_status = 'approved' if approved else 'rejected'
        original_grade.ai_review_comment = comment
        original_grade.ai_reviewed_by_user_id=user.id
        original_grade.ai_reviewed_at = utcnow()
        db_session.flush()
        return grade

    return _create_grade


# ============================================================================
# CONSENSUS FIXTURE
# ============================================================================

@pytest.fixture
def create_consensus(db_session):
    """Factory fixture to create a Consensus for a task."""
    def _create_consensus(
        task: GradingTask,
        final_grading: DiseaseGrading,
        method: str = 'match',
        decided_by: Optional[User] = None,
    ) -> Consensus:
        consensus = Consensus(
            task_id=task.id,
            final_disease_grading_id=final_grading.id,
            method=method,
            decided_by_user_id=decided_by.id if decided_by else None,
            decided_at=utcnow(),
            final_disease_name=final_grading.disease.name,
            final_grade_name=final_grading.impression,
            final_grade_description=final_grading.guidelines,
        )
        db_session.add(consensus)
        db_session.flush()

        if method in ('match', 'adjudication', 'task_review'):
            task.state = 'final'
        db_session.flush()
        return consensus

    return _create_consensus


# ============================================================================
# WORKFLOW SCENARIO FIXTURES
# ============================================================================

@pytest.fixture
def dual_grading_scenario(
    db_session,
    create_resident_grade,
    create_resident2_grade,
):
    """Create a dual grading scenario with resident and resident2 grades."""
    def _create_scenario(
        task: GradingTask,
        resident: User,
        resident2: User,
        resident_grading: DiseaseGrading,
        resident2_grading: Optional[DiseaseGrading] = None,
        create_consensus_if_match: bool = False,
    ) -> dict:
        grade1 = create_resident_grade(task, resident, resident_grading)
        grade2 = create_resident2_grade(
            task,
            resident2,
            resident2_grading or resident_grading
        )

        task.state = 'resident2_done'
        db_session.flush()

        consensus = None
        if create_consensus_if_match and grade1.disease_grading_id == grade2.disease_grading_id:
            from tests.fixtures.workflow import create_consensus as _create_consensus
            consensus_fixture = _create_consensus(db_session)
            consensus = consensus_fixture(
                task,
                resident_grading,
                method='match',
            )

        return {
            'task': task,
            'resident_grade': grade1,
            'resident2_grade': grade2,
            'consensus': consensus,
        }

    return _create_scenario


@pytest.fixture
def arbitration_scenario(
    db_session,
    create_resident_grade,
    create_resident2_grade,
    create_arbitrator_grade,
    create_consensus,
):
    """Create an arbitration scenario with disagreeing grades."""
    def _create_scenario(
        task: GradingTask,
        resident: User,
        resident2: User,
        arbitrator: User,
        resident_grading: DiseaseGrading,
        resident2_grading: DiseaseGrading,
        final_grading: DiseaseGrading,
    ) -> dict:
        grade1 = create_resident_grade(task, resident, resident_grading)
        grade2 = create_resident2_grade(task, resident2, resident2_grading)
        grade3 = create_arbitrator_grade(task, arbitrator, final_grading)

        consensus = create_consensus(
            task,
            final_grading,
            method='adjudication',
            decided_by=arbitrator,
        )

        task.state = 'final'
        db_session.flush()

        return {
            'task': task,
            'resident_grade': grade1,
            'resident2_grade': grade2,
            'arbitrator_grade': grade3,
            'consensus': consensus,
        }

    return _create_scenario


@pytest.fixture
def ai_grading_scenario(
    db_session,
    create_ai_grade,
    create_review_grade,
):
    """Create an AI grading scenario with review."""
    def _create_scenario(
        task: GradingTask,
        ai_model: AIModel,
        ai_grading: DiseaseGrading,
        reviewer: User,
        approved: bool = True,
        comment: Optional[str] = None,
    ) -> dict:
        ai_grade = create_ai_grade(task, ai_model, ai_grading)
        review = create_review_grade(
            task,
            reviewer,
            ai_grade,
            approved=approved,
            comment=comment,
        )

        return {
            'task': task,
            'ai_grade': ai_grade,
            'review_grade': review,
        }

    return _create_scenario


# ============================================================================
# PRE-CONFIGURED QUICK SCENARIOS
# ============================================================================

@pytest.fixture
def sample_grading_task_with_grades(
    db_session,
    TestDataFactory,
    create_resident_grade,
    create_resident2_grade,
    disease_grading_glaucoma,
    ophthalmologist_hospital_a,
):
    """Pre-configured grading task with resident and resident2 grades."""
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=1,
    )
    file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=1,
    )

    glaucoma = db_session.query(Disease).filter_by(name='Glaucoma').first()
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=1,
        disease_id=glaucoma.id,
        encounter_file_id=file.id,
    )

    grade1 = create_resident_grade(
        task,
        ophthalmologist_hospital_a,
        disease_grading_glaucoma,
    )

    from tests.helpers.factories import UserFactory
    res2 = UserFactory.create_ophthalmologist(
        db_session,
        username='test_resident2',
        lab_units=[db_session.query(LabUnit).filter_by(id=1).first()],
    )

    grade2 = create_resident2_grade(
        task,
        res2,
        disease_grading_glaucoma,
    )

    return {
        'task': task,
        'encounter': encounter,
        'file': file,
        'resident_grade': grade1,
        'resident2_grade': grade2,
    }


@pytest.fixture
def sample_task_with_consensus(
    db_session,
    sample_grading_task_with_grades,
    create_consensus,
    disease_grading_glaucoma,
):
    """Pre-configured task with consensus."""
    task = sample_grading_task_with_grades['task']

    consensus = create_consensus(
        task,
        disease_grading_glaucoma,
        method='match',
    )

    return {
        **sample_grading_task_with_grades,
        'consensus': consensus,
    }


@pytest.fixture
def sample_ai_grading_with_review(
    db_session,
    TestDataFactory,
    create_ai_grade,
    create_review_grade,
    ai_model_glaucoma_v1,
    disease_grading_glaucoma,
    master_admin,
):
    """Pre-configured AI grading with human review."""
    encounter = TestDataFactory.create_patient_encounter(
        db_session,
        lab_unit_id=1,
    )
    file = TestDataFactory.create_encounter_file(
        db_session,
        patient_encounter_id=encounter.id,
        lab_unit_id=1,
    )

    glaucoma = db_session.query(Disease).filter_by(name='Glaucoma').first()
    task = TestDataFactory.create_grading_task(
        db_session,
        lab_unit_id=1,
        disease_id=glaucoma.id,
        encounter_file_id=file.id,
    )

    ai_grade = create_ai_grade(task, ai_model_glaucoma_v1, disease_grading_glaucoma)
    review = create_review_grade(
        task,
        master_admin,
        ai_grade,
        approved=True,
        comment='AI assessment looks correct',
    )

    return {
        'task': task,
        'encounter': encounter,
        'file': file,
        'ai_grade': ai_grade,
        'review_grade': review,
    }
