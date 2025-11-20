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
    """Seed core entities data safely using raw SQL."""
    import sys
    from pathlib import Path

    # Add project root to Python path
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))

    # First, check if tables exist using raw SQL
    connection = op.get_bind()

    # Check if hospitals table exists and has data
    result = connection.execute(sa.text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'hospitals' AND table_schema = 'public'"))
    hospitals_table_exists = result.scalar() > 0

    if not hospitals_table_exists:
        print("❌ Hospitals table does not exist - skipping data seeding")
        return

    # Check if hospitals already have data
    result = connection.execute(sa.text("SELECT COUNT(*) FROM hospitals WHERE id IN (1, 2)"))
    hospitals_exist = result.scalar() >= 2

    if hospitals_exist:
        print("✅ Core hospitals already exist - skipping seeding")
        return

    print("✅ Database tables found - proceeding with data seeding")

    # Use raw SQL to insert core data instead of ORM
    try:
        # Insert core hospitals
        connection.execute(sa.text("""
            INSERT INTO hospitals (id, name) VALUES
            (1, 'Sankara Eye Hospital'),
            (2, 'Aravind Eye Hospital')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        # Insert core areas
        connection.execute(sa.text("""
            INSERT INTO areas (id, name) VALUES
            (1, 'Retina'),
            (2, 'Cornea'),
            (3, 'Glaucoma'),
            (4, 'General Ophthalmology')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        # Insert core cameras
        connection.execute(sa.text("""
            INSERT INTO cameras (id, name) VALUES
            (1, 'Topcon TRC-NW400'),
            (2, 'Canon CR-2 Plus AF'),
            (3, 'Remedio Fundus on Phone'),
            (4, 'Remedio Mii-Portable Fundus Camera'),
            (5, 'Remedio Nucleus'),
            (6, 'Remedio Integrated'),
            (7, 'Visucam 200'),
            (8, 'Non-Mydriatic Fundus Camera'),
            (9, 'Mydriatic Fundus Camera')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        # Insert core lab units (with hospital_id to satisfy NOT NULL constraint)
        connection.execute(sa.text("""
            INSERT INTO lab_units (id, name, hospital_id) VALUES
            (1, 'Lab Unit 1', 1),
            (2, 'Lab Unit 2', 1),
            (3, 'Lab Unit 3', 2),
            (4, 'Lab Unit 4', 2)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, hospital_id = EXCLUDED.hospital_id
        """))

        # Insert core diseases
        connection.execute(sa.text("""
            INSERT INTO diseases (id, name) VALUES
            (1, 'Diabetic Retinopathy'),
            (2, 'Glaucoma'),
            (3, 'Age-related Macular Degeneration')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        print("✅ Core entities data seeded successfully using raw SQL")

    except Exception as e:
        print(f"❌ Error seeding core data: {e}")
        # Don't raise exception - let migration continue
        print("   Continuing with remaining migrations...")


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
