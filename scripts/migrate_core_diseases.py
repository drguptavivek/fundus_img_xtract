"""
Migration script to ensure core diseases (Glaucoma, DR, AMD) exist with their specific IDs.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from models import Session, Disease
from ensure_core_diseases import CORE_DISEASES, ensure_core_diseases

def migrate(dry_run=False):
    """
    Ensure core diseases exist in the database.
    
    Args:
        dry_run (bool): If True, only show what would be done without making changes
    """
    print("Preparing to ensure core diseases exist...")
    
    with Session() as db:
        if dry_run:
            print("DRY RUN - No changes will be made")
            
        # Check current state
        print("\nCurrent diseases in database:")
        diseases = db.execute(select(Disease)).scalars().all()
        for disease in diseases:
            core_status = " (CORE)" if disease.id in CORE_DISEASES else ""
            print(f"  ID {disease.id}: {disease.name}{core_status}")
            
        if dry_run:
            print("\nWhat would be done:")
            for disease_id, disease_name in CORE_DISEASES.items():
                existing = db.get(Disease, disease_id)
                if existing:
                    if existing.name != disease_name:
                        print(f"  Update disease ID {disease_id} from '{existing.name}' to '{disease_name}'")
                    else:
                        print(f"  Disease ID {disease_id} '{disease_name}' already exists correctly")
                else:
                    print(f"  Create disease ID {disease_id}: '{disease_name}'")
        else:
            print("\nApplying changes...")
            ensure_core_diseases(db)
            print("Core diseases ensured.")
            
            # Show final state
            print("\nFinal diseases in database:")
            diseases = db.execute(select(Disease)).scalars().all()
            for disease in diseases:
                core_status = " (CORE)" if disease.id in CORE_DISEASES else ""
                print(f"  ID {disease.id}: {disease.name}{core_status}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ensure core diseases exist")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()
    
    migrate(dry_run=args.dry_run)