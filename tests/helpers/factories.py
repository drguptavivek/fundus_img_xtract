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


    @staticmethod
    def create_with_hospital(db_session, role_name, hospital_id, lab_unit_ids=None, 
                           username=None, password='Test@2026', **kwargs):
        """Create user with hospital assignment and lab units."""
        if username is None:
            username = f'test_{role_name}_h{hospital_id}'
        
        role = db_session.query(Role).filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            db_session.add(role)
            db_session.flush()
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            hospital_id=hospital_id,
            is_master_admin=kwargs.get('is_master_admin', False),
            roles=[role],
            is_active=kwargs.get('is_active', True),
            full_name=kwargs.get('full_name', f'Test {role_name.title()} H{hospital_id}')
        )
        db_session.add(user)
        db_session.flush()
        
        # Add lab units if provided
        if lab_unit_ids:
            for lu_id in lab_unit_ids:
                lab_unit = db_session.query(LabUnit).filter_by(id=lu_id).first()
                if lab_unit:
                    user.lab_units.append(lab_unit)
            db_session.flush()
        
        return user
    
    @staticmethod
    def create_grader_with_slots(db_session, username, hospital_id, lab_unit_id, 
                                  disease_slots, password='Test@2026'):
        """
        Create grader (ophthalmologist) with specific disease slots.
        
        Args:
            db_session: Database session
            username: Username for the grader
            hospital_id: Hospital ID
            lab_unit_id: Primary lab unit ID
            disease_slots: List of dicts with disease slot config
                Example: [
                    {'disease_id': 1, 'can_grade_resident': True, 'can_grade_resident2': False},
                    {'disease_id': 2, 'can_grade_resident': False, 'can_grade_resident2': True},
                ]
            password: Password
        
        Returns:
            User with slots configured
        """
        # Create user
        user = UserFactory.create_with_hospital(
            db_session,
            role_name='ophthalmologist',
            hospital_id=hospital_id,
            lab_unit_ids=[lab_unit_id],
            username=username,
            password=password
        )
        
        # Create disease slots (UserDiseaseUnitRole)
        for slot in disease_slots:
            permission = UserDiseaseUnitRole(
                user_id=user.id,
                disease_id=slot['disease_id'],
                lab_unit_id=lab_unit_id,
                can_grade_resident=slot.get('can_grade_resident', False),
                can_grade_resident2=slot.get('can_grade_resident2', False),
                can_arbitrate=slot.get('can_arbitrate', False)
            )
            db_session.add(permission)
        
        db_session.flush()
        return user
    
    @staticmethod
    def create_grader_pool(db_session, hospital_id, lab_unit_id, glaucoma_id, dr_id, prefix='res'):
        """
        Create a pool of 4 residents + 2 arbitrators with slots across Glaucoma and DR.
        
        Returns:
            dict: {'residents': [user1, user2, user3, user4], 'arbitrators': [arb1, arb2]}
        """
        hospital_letter = 'a' if hospital_id == 1 else 'b'
        residents = []
        
        # Resident 1: Can grade R1 for both Glaucoma and DR
        res_1 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_1',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': True},
                {'disease_id': dr_id, 'can_grade_resident': True, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_1)
        
        # Resident 2: Can grade R1/R2 for Glaucoma, only R2 for DR
        res_2 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_2',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': True},
                {'disease_id': dr_id, 'can_grade_resident': False, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_2)
        
        # Resident 3: Can grade R1/R2 for DR, only R1 for Glaucoma
        res_3 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_3',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': False},
                {'disease_id': dr_id, 'can_grade_resident': True, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_3)
        
        # Resident 4: Can grade R1/R2 for both diseases
        res_4 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_res_4',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_grade_resident': True, 'can_grade_resident2': True},
                {'disease_id': dr_id, 'can_grade_resident': True, 'can_grade_resident2': True},
            ]
        )
        residents.append(res_4)
        
        # Arbitrator 1: Can arbitrate Glaucoma and DR
        arb_1 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_arb_1',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_arbitrate': True},
                {'disease_id': dr_id, 'can_arbitrate': True},
            ]
        )
        
        # Arbitrator 2: Can arbitrate Glaucoma only
        arb_2 = UserFactory.create_grader_with_slots(
            db_session,
            username=f'hosp_{hospital_letter}_arb_2',
            hospital_id=hospital_id,
            lab_unit_id=lab_unit_id,
            disease_slots=[
                {'disease_id': glaucoma_id, 'can_arbitrate': True},
            ]
        )
        
        return {
            'residents': residents,
            'arbitrators': [arb_1, arb_2],
            'all': residents + [arb_1, arb_2]
        }


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
        from models import Camera, Area
        
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
        
        # Add Camera
        camera = db_session.query(Camera).filter_by(id=1).first()
        if not camera:
            camera = Camera(id=1, name='Remedio FOP')
            db_session.add(camera)
            db_session.flush()
        
        # Add Area
        area = db_session.query(Area).filter_by(id=1).first()
        if not area:
            area = Area(id=1, name='Retina Disc Focus')
            db_session.add(area)
            db_session.flush()
        
        return {
            'hospital': hospital,
            'lab_unit': lab_unit,
            'glaucoma': glaucoma,
            'dr': dr,
            'camera': camera,
            'area': area,
        }
