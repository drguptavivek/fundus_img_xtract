"""
Utility functions for managing user disease specializations.
"""

from models import Session, User, Disease, user_disease_specializations, Role
from sqlalchemy import select, delete


def get_all_diseases():
    """Get all diseases in the system."""
    db = Session()
    try:
        diseases = db.query(Disease).order_by(Disease.name).all()
        return diseases
    finally:
        db.close()


def get_all_ophthalmologists():
    """Get all users with ophthalmologist role."""
    db = Session()
    try:
        # Get the ophthalmologist role
        ophthalmologist_role = db.query(Role).filter(Role.name == 'ophthalmologist').first()
        if not ophthalmologist_role:
            return []
            
        # Get all users with this role
        ophthalmologists = db.query(User).filter(
            User.roles.any(Role.id == ophthalmologist_role.id)
        ).order_by(User.username).all()
        return ophthalmologists
    finally:
        db.close()


def get_user_disease_specializations(user_id: int):
    """Get all diseases that a user is specialized in."""
    db = Session()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return user.disease_specializations
        return []
    finally:
        db.close()


def get_disease_specialists(disease_id: int):
    """Get all users specialized in a particular disease."""
    db = Session()
    try:
        disease = db.query(Disease).filter(Disease.id == disease_id).first()
        if disease:
            return disease.specialists
        return []
    finally:
        db.close()


def add_user_disease_specialization(user_id: int, disease_id: int):
    """Add a disease specialization for a user."""
    db = Session()
    try:
        # Check if the specialization already exists
        existing = db.execute(
            select(user_disease_specializations).where(
                user_disease_specializations.c.user_id == user_id,
                user_disease_specializations.c.disease_id == disease_id
            )
        ).first()
        
        if not existing:
            # Add the specialization
            db.execute(
                user_disease_specializations.insert().values(
                    user_id=user_id, disease_id=disease_id
                )
            )
            db.commit()
            return True
        return False
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def remove_user_disease_specialization(user_id: int, disease_id: int):
    """Remove a disease specialization for a user."""
    db = Session()
    try:
        # Remove the specialization
        result = db.execute(
            delete(user_disease_specializations).where(
                user_disease_specializations.c.user_id == user_id,
                user_disease_specializations.c.disease_id == disease_id
            )
        )
        db.commit()
        return result.rowcount > 0
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def set_user_disease_specializations(user_id: int, disease_ids: list):
    """Set the complete list of disease specializations for a user."""
    db = Session()
    try:
        # Remove all existing specializations for this user
        db.execute(
            delete(user_disease_specializations).where(
                user_disease_specializations.c.user_id == user_id
            )
        )
        
        # Add new specializations
        if disease_ids:
            values = [{'user_id': user_id, 'disease_id': did} for did in disease_ids]
            db.execute(user_disease_specializations.insert(), values)
        
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()