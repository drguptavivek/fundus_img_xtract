"""
Security-related test fixtures for hospital isolation and cross-hospital grading.

This module provides fixtures for:
- Multi-hospital setup
- Hospital-scoped users (master admin, site admin, ophthalmologists)
- Cross-hospital grading scenarios
- PII protection testing
"""
import pytest
from models import Hospital, LabUnit, User, Role, UserDiseaseUnitRole, Disease
from auth.security import hash_password


@pytest.fixture(scope="session")
def test_hospitals(test_engine):
    """
    Create two test hospitals for isolation testing.
    
    Returns:
        dict: {'hospital_a': Hospital, 'hospital_b': Hospital}
    """
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        # Create hospitals
        hospital_a = Hospital(id=1, name='Hospital A')
        hospital_b = Hospital(id=2, name='Hospital B')
        
        session.add_all([hospital_a, hospital_b])
        session.commit()
        
        # Return as dict for easy access
        hospitals = {
            'hospital_a': hospital_a,
            'hospital_b': hospital_b
        }
        
        yield hospitals
        
    finally:
        session.close()


@pytest.fixture(scope="session")
def test_lab_units(test_engine, test_hospitals):
    """
    Create lab units for both hospitals.
    
    Returns:
        dict: Lab units mapped by hospital
    """
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        # Hospital A lab units
        lab_a1 = LabUnit(id=1, name='Community Ophthalmology', hospital_id=1)
        lab_a2 = LabUnit(id=2, name='Retina Lab', hospital_id=1)
        lab_a3 = LabUnit(id=3, name='Glaucoma Lab', hospital_id=1)
        
        # Hospital B lab units
        lab_b1 = LabUnit(id=4, name='Corena Lab', hospital_id=2)
        lab_b2 = LabUnit(id=5, name='Retina', hospital_id=2)
        lab_b3 = LabUnit(id=6, name='Glaucoma', hospital_id=2)
        
        session.add_all([lab_a1, lab_a2, lab_a3, lab_b1, lab_b2, lab_b3])
        session.commit()
        
        lab_units = {
            'hospital_a': [lab_a1, lab_a2, lab_a3],
            'hospital_b': [lab_b1, lab_b2, lab_b3],
            'lab_a1': lab_a1,
            'lab_a2': lab_a2,
            'lab_a3': lab_a3,
            'lab_b1': lab_b1,
            'lab_b2': lab_b2,
            'lab_b3': lab_b3,
        }
        
        yield lab_units
        
    finally:
        session.close()


@pytest.fixture
def master_admin(db_session):
    """
    Master admin - can access all hospitals.
    
    Attributes:
        is_master_admin=True
        hospital_id=None
    """
    # Get or create admin role
    admin_role = db_session.query(Role).filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin')
        db_session.add(admin_role)
        db_session.flush()
    
    user = User(
        username='master_admin',
        password_hash=hash_password('Test@2026'),
        hospital_id=None,  # No specific hospital
        is_master_admin=True,
        roles=[admin_role]
    )
    db_session.add(user)
    db_session.flush()
    
    return user


@pytest.fixture(scope="session")
def site_admin_hospital_a(test_engine, test_hospitals):
    """
    Site admin for Hospital A only (session-scoped).
    
    Attributes:
        hospital_id=1
        is_master_admin=False
    """
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        # Get or create local_admin role
        role = session.query(Role).filter_by(name='local_admin').first()
        if not role:
            role = Role(name='local_admin')
            session.add(role)
            session.flush()
        
        # Check if user already exists
        user = session.query(User).filter_by(username='site_admin_a').first()
        if not user:
            user = User(
                username='site_admin_a',
                password_hash=hash_password('Test@2026'),
                hospital_id=1,
                is_master_admin=False,
                roles=[role]
            )
            session.add(user)
        
        session.commit()
        return user
    finally:
        session.close()


@pytest.fixture(scope="session")
def site_admin_hospital_b(test_engine, test_hospitals):
    """
    Site admin for Hospital B only (session-scoped).
    
    Attributes:
        hospital_id=2
        is_master_admin=False
    """
    from sqlalchemy.orm import sessionmaker
    
    Session = sessionmaker(bind=test_engine)
    session = Session()
    
    try:
        # Get or create local_admin role
        role = session.query(Role).filter_by(name='local_admin').first()
        if not role:
            role = Role(name='local_admin')
            session.add(role)
            session.flush()
        
        # Check if user already exists
        user = session.query(User).filter_by(username='site_admin_b').first()
        if not user:
            user = User(
                username='site_admin_b',
                password_hash=hash_password('Test@2026'),
                hospital_id=2,
                is_master_admin=False,
                roles=[role]
            )
            session.add(user)
        
        session.commit()
        return user
    finally:
        session.close()


@pytest.fixture
def ophthalmologist_hospital_a(db_session, test_hospitals, test_lab_units, core_test_data):
    """
    Ophthalmologist from Hospital A.
    Can grade cross-hospital via ABAC.
    
    Attributes:
        hospital_id=1
        lab_units=[lab_a1]
        Can grade Glaucoma in lab_a1
    """
    # Get or create ophthalmologist role
    role = db_session.query(Role).filter_by(name='ophthalmologist').first()
    if not role:
        role = Role(name='ophthalmologist')
        db_session.add(role)
        db_session.flush()
    
    # Merge lab_unit to current session
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    
    user = User(
        username='ophth_a',
        password_hash=hash_password('Test@2026'),
        hospital_id=1,
        is_master_admin=False,
        roles=[role],
        lab_units=[lab_a1]
    )
    db_session.add(user)
    db_session.flush()
    
    # Add ABAC grading permission for Hospital A
    permission = UserDiseaseUnitRole(
        user_id=user.id,
        disease_id=core_test_data['glaucoma'].id,
        lab_unit_id=1,  # Hospital A lab
        can_grade_resident=True,
        can_grade_resident2=True,
        can_arbitrate=False
    )
    db_session.add(permission)
    db_session.flush()
    
    return user


@pytest.fixture
def ophthalmologist_cross_hospital(db_session, test_hospitals, test_lab_units, core_test_data):
    """
    Ophthalmologist who can grade tasks from BOTH hospitals.
    
    Attributes:
        hospital_id=1 (belongs to Hospital A)
        Can grade in lab_a1 (Hospital A)
        Can also grade in lab_b1 (Hospital B) - CROSS-HOSPITAL
    """
    role = db_session.query(Role).filter_by(name='ophthalmologist').first()
    if not role:
        role = Role(name='ophthalmologist')
        db_session.add(role)
        db_session.flush()
    
    # Merge lab_unit to current session
    lab_a1 = db_session.merge(test_lab_units['lab_a1'])
    
    user = User(
        username='ophth_cross',
        password_hash=hash_password('Test@2026'),
        hospital_id=1,  # Belongs to Hospital A
        is_master_admin=False,
        roles=[role],
        lab_units=[lab_a1]  # Only A for uploads
    )
    db_session.add(user)
    db_session.flush()
    
    # Can grade in Hospital A
    perm_a = UserDiseaseUnitRole(
        user_id=user.id,
        disease_id=core_test_data['glaucoma'].id,
        lab_unit_id=1,
        can_grade_resident=True,
        can_grade_resident2=True,
        can_arbitrate=False
    )
    
    # Can ALSO grade in Hospital B (cross-hospital grading)
    perm_b = UserDiseaseUnitRole(
        user_id=user.id,
        disease_id=core_test_data['glaucoma'].id,
        lab_unit_id=4,  # Hospital B lab!
        can_grade_resident=True,
        can_grade_resident2=True,
        can_arbitrate=False
    )
    
    db_session.add_all([perm_a, perm_b])
    db_session.flush()
    
    return user


@pytest.fixture
def optometrist_hospital_a(db_session, test_hospitals, test_lab_units):
    """
    Optometrist for Hospital A - verification and anonymization.
    
    Attributes:
        hospital_id=1
        lab_units=[lab_a1, lab_a2, lab_a3]
    """
    role = db_session.query(Role).filter_by(name='optometrist').first()
    if not role:
        role = Role(name='optometrist')
        db_session.add(role)
        db_session.flush()
    
    # Merge all Hospital A lab units to current session
    hospital_a_labs = [
        db_session.merge(test_lab_units['lab_a1']),
        db_session.merge(test_lab_units['lab_a2']),
        db_session.merge(test_lab_units['lab_a3']),
    ]
    
    user = User(
        username='optom_a',
        password_hash=hash_password('Test@2026'),
        hospital_id=1,
        is_master_admin=False,
        roles=[role],
        lab_units=hospital_a_labs
    )
    db_session.add(user)
    db_session.flush()
    
    return user


@pytest.fixture
def dataset_creator(db_session):
    """
    Dataset creator - can access all hospitals for AI training datasets.
    
    Attributes:
        hospital_id=1 (belongs to a hospital)
        But can export from all hospitals (cross-hospital)
    """
    role = db_session.query(Role).filter_by(name='dataset_creator').first()
    if not role:
        role = Role(name='dataset_creator')
        db_session.add(role)
        db_session.flush()
    
    user = User(
        username='dataset_creator',
        password_hash=hash_password('Test@2026'),
        hospital_id=1,
        is_master_admin=False,
        roles=[role]
    )
    db_session.add(user)
    db_session.flush()
    
    return user
