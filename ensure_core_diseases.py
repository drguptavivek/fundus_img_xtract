"""
Utility functions to ensure core diseases are always present and protected.
"""

from models import Disease

# Core diseases that must always exist
CORE_DISEASES = {
    1: "Glaucoma",
    2: "DR",  # Diabetic Retinopathy
    3: "AMD"  # Age-related Macular Degeneration
}

def ensure_core_diseases(db):
    """
    Ensure that the core diseases (Glaucoma, DR, AMD) exist with their specific IDs.
    This function should be called during application startup and database initialization.
    """
    for disease_id, disease_name in CORE_DISEASES.items():
        # Check if disease with this ID already exists
        existing = db.get(Disease, disease_id)
        if existing:
            # If it exists but has a different name, update it
            if existing.name != disease_name:
                existing.name = disease_name
                db.add(existing)
        else:
            # Create the disease with the specific ID
            disease = Disease(id=disease_id, name=disease_name)
            db.add(disease)
    
    db.commit()

def is_core_disease(disease_id):
    """
    Check if a disease ID corresponds to one of the core diseases.
    """
    return disease_id in CORE_DISEASES

def get_core_diseases():
    """
    Get the core diseases mapping.
    """
    return CORE_DISEASES.copy()