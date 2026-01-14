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


@pytest.fixture(scope="function")
def hospital_data(db_session):
    """
    Get hospitals with their lab units in a convenient structure (function-scoped).

    Queries by NAME for resilience to ID changes.
    Returns all 6 lab units (3 per hospital).
    """
    # Query hospitals and lab units from the database by NAME
    hosp_a = db_session.query(Hospital).filter_by(name='Hospital A').first()
    hosp_b = db_session.query(Hospital).filter_by(name='Hospital B').first()

    # Hospital A lab units (IDs 1-3)
    lab_a1 = db_session.query(LabUnit).filter_by(name='Lab A1').first()
    lab_a2 = db_session.query(LabUnit).filter_by(name='Lab A2').first()
    lab_a3 = db_session.query(LabUnit).filter_by(name='Lab A3').first()

    # Hospital B lab units (IDs 4-6)
    lab_b1 = db_session.query(LabUnit).filter_by(name='Lab B1').first()
    lab_b2 = db_session.query(LabUnit).filter_by(name='Lab B2').first()
    lab_b3 = db_session.query(LabUnit).filter_by(name='Lab B3').first()

    return {
        'hospital_a': {
            'hospital': hosp_a,
            'lab_units': [lab_a1, lab_a2, lab_a3]  # 3 labs
        },
        'hospital_b': {
            'hospital': hosp_b,
            'lab_units': [lab_b1, lab_b2, lab_b3]  # 3 labs
        }
    }



@pytest.fixture(scope="session")
def test_lab_units(seed_test_database):
    """
    Get seeded lab units.

    Returns all 6 lab units (3 per hospital) in a structure compatible
    with security.py fixture format.
    """
    return {
        # Hospital A (IDs 1-3)
        'hospital_a': [
            seed_test_database['lab_units']['Lab A1'],
            seed_test_database['lab_units']['Lab A2'],
            seed_test_database['lab_units']['Lab A3'],
        ],
        # Hospital B (IDs 4-6)
        'hospital_b': [
            seed_test_database['lab_units']['Lab B1'],
            seed_test_database['lab_units']['Lab B2'],
            seed_test_database['lab_units']['Lab B3'],
        ],
        # Individual access (backward compatibility)
        'lab_a1': seed_test_database['lab_units']['Lab A1'],
        'lab_a2': seed_test_database['lab_units']['Lab A2'],
        'lab_a3': seed_test_database['lab_units']['Lab A3'],
        'lab_b1': seed_test_database['lab_units']['Lab B1'],
        'lab_b2': seed_test_database['lab_units']['Lab B2'],
        'lab_b3': seed_test_database['lab_units']['Lab B3'],
    }


@pytest.fixture(scope="function")
def test_metadata(db_session):
    """Get seeded metadata (Camera, Disease, Area) - function-scoped."""
    # Query metadata from database
    test_camera = db_session.query(Camera).filter_by(name='Test Camera').first()
    dr = db_session.query(Disease).filter_by(name='DR').first()
    glaucoma = db_session.query(Disease).filter_by(name='Glaucoma').first()
    amd = db_session.query(Disease).filter_by(name='AMD').first()
    test_disease = db_session.query(Disease).filter_by(name='Test Disease').first()
    test_area = db_session.query(Area).filter_by(name='Test Area').first()
    
    return {
        'cameras': {
            'test_camera': test_camera,
        },
        'diseases': {
            'dr': dr,
            'glaucoma': glaucoma,
            'amd': amd,
            'test_disease': test_disease,
        },
        'areas': {
            'test_area': test_area,
        },
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
