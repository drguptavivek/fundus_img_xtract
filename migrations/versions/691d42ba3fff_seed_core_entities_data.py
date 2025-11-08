"""Seed core entities data

Revision ID: 691d42ba3fff
Revises: 5a49784f68f1
Create Date: 2025-11-07 18:26:00.251215

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '691d42ba3fff'
down_revision: Union[str, Sequence[str], None] = '5a49784f68f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Seed core entities data safely."""
    import sys
    from pathlib import Path
    
    # Add project root to Python path
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    # Import the safe setup functions
    from scripts.setup_core_entities import setup_all_core_entities
    from models import Session
    
    # Use the safe, idempotent setup function
    with Session() as db:
        # Setup core entities first
        setup_all_core_entities(db)
        db.commit()
        print("✅ Core entities data seeded successfully")
        
        # Now populate sample features in the same session
        from scripts.setup_core_entities import populate_sample_features
        populate_sample_features()
        db.commit()  # Commit the features
        print("✅ Sample features populated successfully")


def downgrade() -> None:
    """Remove seeded core entities data."""
    import sys
    from pathlib import Path
    
    # Add project root to Python path
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))
    
    from models import Session, Hospital, LabUnit, Camera, Area, Disease, DiseaseGrading, GradingsFeatures
    from sqlalchemy import delete
    
    with Session() as db:
        # Remove in correct order due to foreign key constraints
        # Start with dependent data first
        
        # Remove sample features for core disease gradings
        db.execute(
            delete(GradingsFeatures).where(
                GradingsFeatures.disease_grading_id.in_(
                    db.execute(
                        sa.select(DiseaseGrading.id).where(
                            DiseaseGrading.disease_id.in_([1, 2, 3])  # Core disease IDs
                        )
                    ).scalars().all()
                )
            )
        )
        
        # Remove disease gradings for core diseases
        db.execute(
            delete(DiseaseGrading).where(
                DiseaseGrading.disease_id.in_([1, 2, 3])  # Core disease IDs
            )
        )
        
        # Remove core diseases
        db.execute(delete(Disease).where(Disease.id.in_([1, 2, 3])))
        
        # Remove core areas
        db.execute(delete(Area).where(Area.id.in_([1, 2, 3, 4])))
        
        # Remove core cameras
        db.execute(delete(Camera).where(Camera.id.in_([1, 2, 3, 4, 5, 6, 7, 8, 9])))
        
        # Remove core lab units
        db.execute(delete(LabUnit).where(LabUnit.id.in_([1, 2, 3, 4])))
        
        # Remove core hospitals
        db.execute(delete(Hospital).where(Hospital.id.in_([1, 2])))
        
        db.commit()
        print("✅ Core entities data removed successfully")
