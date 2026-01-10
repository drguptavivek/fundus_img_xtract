"""
Test Data Factories

Provides factory functions to create test data with proper relationships.
"""

from typing import List, Optional
from models import User, Role, Hospital, LabUnit, Disease, UserDiseaseUnitRole
from auth.security import hash_password


class UserFactory:
    """Factory to create users with specific roles and permissions"""
    
    @staticmethod
    def create_admin(db_session, username='test_admin', password='Test@2026'):
        """Create admin user with all permissions"""
        admin_role = db_session.query(Role).filter_by(name='admin').first()
        if not admin_role:
            admin_role = Role(name='admin')
            db_session.add(admin_role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            roles=[admin_role],
            is_active=True,
            full_name=f'Test Admin ({username})'
        )
        db_session.add(user)
        db_session.flush()
        return user
    
    @staticmethod
    def create_ophthalmologist(db_session, username='test_ophthalmologist', 
                              password='Test@2026', lab_units=None):
        """Create ophthalmologist with specific lab units"""
        oph_role = db_session.query(Role).filter_by(name='ophthalmologist').first()
        if not oph_role:
            oph_role = Role(name='ophthalmologist')
            db_session.add(oph_role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            roles=[oph_role],
            is_active=True,
            full_name=f'Test Ophthalmologist ({username})'
        )
        db_session.add(user)
        db_session.flush()
        
        if lab_units:
            user.lab_units.extend(lab_units)
            db_session.flush()
        
        return user
    
    @staticmethod
    def create_by_role(db_session, role_name, username=None, password='Test@2026', **kwargs):
        """Generic factory for any role"""
        if username is None:
            username = f'test_{role_name}'
        
        role = db_session.query(Role).filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            roles=[role],
            is_active=kwargs.get('is_active', True),
            full_name=kwargs.get('full_name', f'Test {role_name.title()} ({username})')
        )
        db_session.add(user)
        db_session.flush()
        
        # Add lab units if provided
        if 'lab_units' in kwargs:
            user.lab_units.extend(kwargs['lab_units'])
            db_session.flush()
        
        return user
   
    @staticmethod
    def create_with_permissions(db_session, role_name, disease_id, lab_unit_id,
                                can_grade_resident=False, can_grade_resident2=False,
                                can_arbitrate=False, username=None, password='Test@2026'):
        """Create user with specific grading permissions"""
        user = UserFactory.create_by_role(db_session, role_name, username, password)
        
        # Grant specific permission
        permission = UserDiseaseUnitRole(
            user_id=user.id,
            disease_id=disease_id,
            lab_unit_id=lab_unit_id,
            can_grade_resident=can_grade_resident,
            can_grade_resident2=can_grade_resident2,
            can_arbitrate=can_arbitrate
        )
        db_session.add(permission)
        db_session.flush()
        
        return user


class CoreEntityFactory:
    """Factory to create core entities (hospitals, lab units, diseases)"""
    
    @staticmethod
    def create_hospital(db_session, name='Test Hospital', hospital_id=None):
        """Create a test hospital"""
        hospital = Hospital(
            id=hospital_id,
            name=name
        )
        db_session.add(hospital)
        db_session.flush()
        return hospital
    
    @staticmethod
    def create_lab_unit(db_session, name='Test Lab Unit', hospital_id=1, lab_unit_id=None):
        """Create a test lab unit"""
        lab_unit = LabUnit(
            id=lab_unit_id,
            name=name,
            hospital_id=hospital_id
        )
        db_session.add(lab_unit)
        db_session.flush()
        return lab_unit
    
    @staticmethod
    def create_disease(db_session, name='Test Disease', disease_id=None):
        """Create a test disease"""
        disease = Disease(
            id=disease_id,
            name=name
        )
        db_session.add(disease)
        db_session.flush()
        return disease
    
    @staticmethod
    def setup_core_entities(db_session):
        """Setup standard core entities for testing"""
        # Check if they already exist
        hospital = db_session.query(Hospital).filter_by(id=1).first()
        if not hospital:
            hospital = CoreEntityFactory.create_hospital(db_session, 'RPC AIIMS', 1)
        
        lab_unit = db_session.query(LabUnit).filter_by(id=1).first()
        if not lab_unit:
            lab_unit = CoreEntityFactory.create_lab_unit(
                db_session, 'Community Ophthalmology', 1, 1
            )
        
        glaucoma = db_session.query(Disease).filter_by(id=1).first()
        if not glaucoma:
            glaucoma = CoreEntityFactory.create_disease(db_session, 'Glaucoma', 1)
        
        dr = db_session.query(Disease).filter_by(id=2).first()
        if not dr:
            dr = CoreEntityFactory.create_disease(db_session, 'DR', 2)
        
        return {
            'hospital': hospital,
            'lab_unit': lab_unit,
            'glaucoma': glaucoma,
            'dr': dr
        }
