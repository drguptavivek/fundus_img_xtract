"""
Simplified fixtures that query seeded test data.

These fixtures provide convenient access to the data seeded by seed_test_database.
They are session-scoped and simply query the database rather than creating new data.
"""
import pytest
from models import Hospital, LabUnit, Camera, Disease, Area, User


@pytest.fixture(scope="session")
def test_hospitals(seed_test_database):
    """Get seeded hospitals."""
    return seed_test_database['hospitals']


@pytest.fixture(scope="session")
def test_lab_units(seed_test_database):
    """Get seeded lab units."""
    return {
        'lab_a1': seed_test_database['lab_units']['Lab A1'],
        'lab_a2': seed_test_database['lab_units']['Lab A2'],
        'lab_b1': seed_test_database['lab_units']['Lab B1'],
        'lab_b2': seed_test_database['lab_units']['Lab B2'],
    }


@pytest.fixture(scope="session")
def test_metadata(seed_test_database):
    """Get seeded metadata (Camera, Disease, Area)."""
    return {
        'camera': seed_test_database['cameras']['Test Camera'],
        'disease': seed_test_database['diseases']['Test Disease'],
        'area': seed_test_database['areas']['Test Area'],
    }


@pytest.fixture(scope="session")
def site_admin_hospital_a(seed_test_database):
    """Get seeded Site Admin for Hospital A."""
    return seed_test_database['users']['site_admin_a']


@pytest.fixture(scope="session")
def site_admin_hospital_b(seed_test_database):
    """Get seeded Site Admin for Hospital B."""
    return seed_test_database['users']['site_admin_b']


@pytest.fixture(scope="session")
def master_admin(seed_test_database):
    """Get seeded Master Admin."""
    return seed_test_database['users']['master_admin']


@pytest.fixture(scope="session")
def ophthalmologist_hospital_a(seed_test_database):
    """Get seeded Ophthalmologist for Hospital A."""
    return seed_test_database['users']['ophthalmologist_a']


@pytest.fixture(scope="session")
def ophthalmologist_hospital_b(seed_test_database):
    """Get seeded Ophthalmologist for Hospital B."""
    return seed_test_database['users']['ophthalmologist_b']


@pytest.fixture(scope="session")
def ophthalmologist_cross_hospital(seed_test_database):
    """Get seeded cross-hospital Ophthalmologist."""
    return seed_test_database['users']['ophthalmologist_cross']
