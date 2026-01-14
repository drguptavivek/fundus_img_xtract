"""
Role-based user fixtures for hospital isolation testing.

Provides complete user coverage for all roles across both hospitals.
"""
import pytest
from tests.helpers.factories import UserFactory


# ============================================================================
# Hospital A - Support Roles
# ============================================================================

@pytest.fixture
def hosp_a_file_uploader(db_session, test_lab_units):
    """File uploader for Hospital A."""
    # Merge LabUnits into current session to avoid DetachedInstanceError
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    lab_a2 = db_session.merge(test_lab_units['lab_a2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='fileUploader',
        hospital_id=1,
        lab_unit_ids=[lab_a1.id, lab_a2.id],  # All Hospital A labs
        username='hosp_a_file_uploader'
    )


@pytest.fixture
def hosp_a_optometrist(db_session, test_lab_units):
    """Optometrist for Hospital A - PII gatekeeper."""
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    lab_a2 = db_session.merge(test_lab_units['lab_a2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='optometrist',
        hospital_id=1,
        lab_unit_ids=[lab_a1.id, lab_a2.id],  # All Hospital A labs
        username='hosp_a_optometrist'
    )


@pytest.fixture
def hosp_a_data_manager(db_session, test_lab_units):
    """Data manager for Hospital A."""
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    lab_a2 = db_session.merge(test_lab_units['lab_a2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='data_manager',
        hospital_id=1,
        lab_unit_ids=[lab_a1.id, lab_a2.id],
        username='hosp_a_data_manager'
    )


@pytest.fixture
def hosp_a_data_exporter(db_session, test_lab_units):
    """Data exporter for Hospital A."""
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    lab_a2 = db_session.merge(test_lab_units['lab_a2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='data_exporter',
        hospital_id=1,
        lab_unit_ids=[lab_a1.id, lab_a2.id],
        username='hosp_a_data_exporter'
    )


@pytest.fixture
def hosp_a_analyst(db_session, test_lab_units):
    """Analyst for Hospital A - read-only stats."""
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    lab_a2 = db_session.merge(test_lab_units['lab_a2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='analyst',
        hospital_id=1,
        lab_unit_ids=[lab_a1.id, lab_a2.id],
        username='hosp_a_analyst'
    )


@pytest.fixture
def hosp_a_site_admin(db_session, test_hospitals):
    """Site admin for Hospital A."""
    return UserFactory.create_with_hospital(
        db_session,
        role_name='local_admin',
        hospital_id=1,
        username='hosp_a_site_admin'
    )


# ============================================================================
# Hospital B - Support Roles
# ============================================================================

@pytest.fixture
def hosp_b_file_uploader(db_session, test_lab_units):
    """File uploader for Hospital B."""
    lab_b1 = db_session.merge(test_lab_units['lab_b1'])
    lab_b2 = db_session.merge(test_lab_units['lab_b2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='fileUploader',
        hospital_id=2,
        lab_unit_ids=[lab_b1.id, lab_b2.id],  # All Hospital B labs
        username='hosp_b_file_uploader'
    )


@pytest.fixture
def hosp_b_optometrist(db_session, test_lab_units):
    """Optometrist for Hospital B - PII gatekeeper."""
    lab_b1 = db_session.merge(test_lab_units['lab_b1'])
    lab_b2 = db_session.merge(test_lab_units['lab_b2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='optometrist',
        hospital_id=2,
        lab_unit_ids=[lab_b1.id, lab_b2.id],  # All Hospital B labs
        username='hosp_b_optometrist'
    )


@pytest.fixture
def hosp_b_data_manager(db_session, test_lab_units):
    """Data manager for Hospital B."""
    lab_b1 = db_session.merge(test_lab_units['lab_b1'])
    lab_b2 = db_session.merge(test_lab_units['lab_b2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='data_manager',
        hospital_id=2,
        lab_unit_ids=[lab_b1.id, lab_b2.id],
        username='hosp_b_data_manager'
    )


@pytest.fixture
def hosp_b_data_exporter(db_session, test_lab_units):
    """Data exporter for Hospital B."""
    lab_b1 = db_session.merge(test_lab_units['lab_b1'])
    lab_b2 = db_session.merge(test_lab_units['lab_b2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='data_exporter',
        hospital_id=2,
        lab_unit_ids=[lab_b1.id, lab_b2.id],
        username='hosp_b_data_exporter'
    )


@pytest.fixture
def hosp_b_analyst(db_session, test_lab_units):
    """Analyst for Hospital B - read-only stats."""
    lab_b1 = db_session.merge(test_lab_units['lab_b1'])
    lab_b2 = db_session.merge(test_lab_units['lab_b2'])
    return UserFactory.create_with_hospital(
        db_session,
        role_name='analyst',
        hospital_id=2,
        lab_unit_ids=[lab_b1.id, lab_b2.id],
        username='hosp_b_analyst'
    )


@pytest.fixture
def hosp_b_site_admin(db_session, test_hospitals):
    """Site admin for Hospital B."""
    return UserFactory.create_with_hospital(
        db_session,
        role_name='local_admin',
        hospital_id=2,
        username='hosp_b_site_admin'
    )


# ============================================================================
# Global/Cross-Hospital Roles
# ============================================================================

@pytest.fixture
def analytics_viewer_global(db_session):
    """Analytics viewer with cross-hospital read access."""
    return UserFactory.create_with_hospital(
        db_session,
        role_name='analytics_viewer',
        hospital_id=1,  # Belongs to Hospital A but can view all
        username='analytics_viewer_global'
    )


@pytest.fixture
def dataset_creator_global(db_session):
    """Dataset creator with cross-hospital access."""
    return UserFactory.create_with_hospital(
        db_session,
        role_name='dataset_creator',
        hospital_id=1,
        username='dataset_creator_global'
    )


# ============================================================================
# Convenience Fixtures - Complete Hospital User Sets
# ============================================================================

@pytest.fixture
def all_hospital_a_users(
    hosp_a_file_uploader,
    hosp_a_optometrist,
    hosp_a_data_manager,
    hosp_a_data_exporter,
    hosp_a_analyst,
    hosp_a_site_admin,
    hospital_a_grading_pool
):
    """
    All users for Hospital A.
    
    Returns:
        dict: All Hospital A users by role
    """
    return {
        'file_uploader': hosp_a_file_uploader,
        'optometrist': hosp_a_optometrist,
        'data_manager': hosp_a_data_manager,
        'data_exporter': hosp_a_data_exporter,
        'analyst': hosp_a_analyst,
        'site_admin': hosp_a_site_admin,
        'grading_pool': hospital_a_grading_pool,
    }


@pytest.fixture
def all_hospital_b_users(
    hosp_b_file_uploader,
    hosp_b_optometrist,
    hosp_b_data_manager,
    hosp_b_data_exporter,
    hosp_b_analyst,
    hosp_b_site_admin,
    hospital_b_grading_pool
):
    """
    All users for Hospital B.
    
    Returns:
        dict: All Hospital B users by role
    """
    return {
        'file_uploader': hosp_b_file_uploader,
        'optometrist': hosp_b_optometrist,
        'data_manager': hosp_b_data_manager,
        'data_exporter': hosp_b_data_exporter,
        'analyst': hosp_b_analyst,
        'site_admin': hosp_b_site_admin,
        'grading_pool': hospital_b_grading_pool,
    }
