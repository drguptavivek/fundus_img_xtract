"""
Comprehensive grading pool fixtures for hospital isolation testing.

Provides:
- Complete grading pools per hospital (4 residents + 2 arbitrators)
- Disease slots across Glaucoma and DR
- Cross-hospital graders
- Test various slotting scenarios
"""
import pytest
from tests.helpers.factories import UserFactory


@pytest.fixture
def hospital_a_grading_pool(db_session, test_lab_units, core_test_data):
    """
    Complete grading pool for Hospital A.
    
    Returns 4 residents + 2 arbitrators with slots for Glaucoma and DR.
    Each user has different slot configurations for testing eligibility.
    """
    pool = UserFactory.create_grader_pool(
        db_session,
        hospital_id=1,
        lab_unit_id=1,  # Community Ophthalmology
        glaucoma_id=core_test_data['glaucoma'].id,
        dr_id=core_test_data['dr'].id
    )
    
    return pool


@pytest.fixture
def hospital_b_grading_pool(db_session, test_lab_units, core_test_data):
    """
    Complete grading pool for Hospital B.
    
    Returns 4 residents + 2 arbitrators with slots for Glaucoma and DR.
    """
    pool = UserFactory.create_grader_pool(
        db_session,
        hospital_id=2,
        lab_unit_id=4,  # Corena Lab
        glaucoma_id=core_test_data['glaucoma'].id,
        dr_id=core_test_data['dr'].id
    )
    
    return pool


@pytest.fixture
def hosp_a_res_1(hospital_a_grading_pool):
    """Hospital A Resident 1 - can grade R1/R2 for both Glaucoma and DR."""
    return hospital_a_grading_pool['residents'][0]


@pytest.fixture
def hosp_a_res_2(hospital_a_grading_pool):
    """Hospital A Resident 2 - can grade R1/R2 for Glaucoma, only R2 for DR."""
    return hospital_a_grading_pool['residents'][1]


@pytest.fixture
def hosp_a_res_3(hospital_a_grading_pool):
    """Hospital A Resident 3 - can grade R1/R2 for DR, only R1 for Glaucoma."""
    return hospital_a_grading_pool['residents'][2]


@pytest.fixture
def hosp_a_res_4(hospital_a_grading_pool):
    """Hospital A Resident 4 - can grade R1/R2 for both diseases."""
    return hospital_a_grading_pool['residents'][3]


@pytest.fixture
def hosp_a_arb_1(hospital_a_grading_pool):
    """Hospital A Arbitrator 1 - can arbitrate both Glaucoma and DR."""
    return hospital_a_grading_pool['arbitrators'][0]


@pytest.fixture
def hosp_a_arb_2(hospital_a_grading_pool):
    """Hospital A Arbitrator 2 - can arbitrate Glaucoma only."""
    return hospital_a_grading_pool['arbitrators'][1]


@pytest.fixture
def hosp_b_res_1(hospital_b_grading_pool):
    """Hospital B Resident 1 - can grade R1/R2 for both Glaucoma and DR."""
    return hospital_b_grading_pool['residents'][0]


@pytest.fixture
def hosp_b_res_2(hospital_b_grading_pool):
    """Hospital B Resident 2 - can grade R1/R2 for Glaucoma, only R2 for DR."""
    return hospital_b_grading_pool['residents'][1]


@pytest.fixture
def hosp_b_res_3(hospital_b_grading_pool):
    """Hospital B Resident 3 - can grade R1/R2 for DR, only R1 for Glaucoma."""
    return hospital_b_grading_pool['residents'][2]


@pytest.fixture
def hosp_b_res_4(hospital_b_grading_pool):
    """Hospital B Resident 4 - can grade R1/R2 for both diseases."""
    return hospital_b_grading_pool['residents'][3]


@pytest.fixture
def hosp_b_arb_1(hospital_b_grading_pool):
    """Hospital B Arbitrator 1 - can arbitrate both Glaucoma and DR."""
    return hospital_b_grading_pool['arbitrators'][0]


@pytest.fixture
def hosp_b_arb_2(hospital_b_grading_pool):
    """Hospital B Arbitrator 2 - can arbitrate Glaucoma only."""
    return hospital_b_grading_pool['arbitrators'][1]


@pytest.fixture
def cross_grader_a_to_b(db_session, test_lab_units, core_test_data):
    """
    Cross-hospital grader: Belongs to Hospital A, can grade Hospital B tasks.
    
    Attributes:
        hospital_id=1 (Hospital A)
        Can grade in lab_unit_id=4 (Hospital B)
    """
    from models import UserDiseaseUnitRole
    
    # Create user in Hospital A
    user = UserFactory.create_with_hospital(
        db_session,
        role_name='ophthalmologist',
        hospital_id=1,
        lab_unit_ids=[1],  # Hospital A lab for uploads
        username='cross_grader_a_to_b'
    )
    
    # Add slots for Hospital B grading (cross-hospital)
    for disease_id in [core_test_data['glaucoma'].id, core_test_data['dr'].id]:
        perm = UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=disease_id,
            lab_unit_id=4,  # Hospital B lab unit!
            can_grade_resident=True,
            can_grade_resident2=True,
            can_arbitrate=False
        )
        db_session.add(perm)
    
    db_session.flush()
    return user


@pytest.fixture
def cross_grader_b_to_a(db_session, test_lab_units, core_test_data):
    """
    Cross-hospital grader: Belongs to Hospital B, can grade Hospital A tasks.
    
    Attributes:
        hospital_id=2 (Hospital B)
        Can grade in lab_unit_id=1 (Hospital A)
    """
    from models import UserDiseaseUnitRole
    
    # Create user in Hospital B
    user = UserFactory.create_with_hospital(
        db_session,
        role_name='ophthalmologist',
        hospital_id=2,
        lab_unit_ids=[4],  # Hospital B lab for uploads
        username='cross_grader_b_to_a'
    )
    
    # Add slots for Hospital A grading (cross-hospital)
    for disease_id in [core_test_data['glaucoma'].id, core_test_data['dr'].id]:
        perm = UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=disease_id,
            lab_unit_id=1,  # Hospital A lab unit!
            can_grade_resident=True,
            can_grade_resident2=True,
            can_arbitrate=False
        )
        db_session.add(perm)
    
    db_session.flush()
    return user
