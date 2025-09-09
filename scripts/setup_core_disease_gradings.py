# scripts/setup_core_disease_gradings.py
"""
Script to set up standard gradings for core diseases (Glaucoma, DR, AMD).
"""

import argparse
import sys
from pathlib import Path

# Add the project root to the path so we can import models
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from models import Session, Disease, DiseaseGrading
from ensure_core_diseases import CORE_DISEASES


# Standard gradings for each core disease
STANDARD_GRADINGS = {
    # Glaucoma gradings
    "Glaucoma": [
        {"impression": "Normal", "display_order": 1, "is_active": True, "guidelines": "No signs of glaucomatous changes. No Other Referrable disease"},
        {"impression": "Suspect", "display_order": 2, "is_active": True, "guidelines": "Vertical CDR >= 0.8 / ISNT Rule  violated / Baring of Circulminear vessels / Bayonet Sign / Beta Zone PPA  OD haemmorhages "},
        {"impression": "Glaucoma", "display_order": 3, "is_active": True, "guidelines": "<b>Hard Signs of Glaucoma </b>:  RNFL Loss / Focal NRR defects / Total cupping."},
        {"impression": "Other Retinal", "display_order": 4, "is_active": True, "guidelines": "If  No Glaucoma/ Not Glaucoma suspect BUT Any other retinal or disc pathology. Note disease in remarks"},
        {"impression": "Not Gradable", "display_order": 5, "is_active": True, "guidelines": "If cannot grade, mark as not gradable. Note signs in remarks."},
    ],
    
    # Diabetic Retinopathy (DR) gradings
    "DR": [
        {"impression": "No DR", "display_order": 1, "is_active": True, "guidelines": "No signs of diabetic retinopathy."},
        {"impression": "Minimal/Mild DR", "display_order": 2, "is_active": True, "guidelines": "Few microaneurysms only."},
        {"impression": "Moderate NPDR", "display_order": 3, "is_active": True, "guidelines": "Microaneurysms, small hemorrhages, and hard exudates only."},
        {"impression": "PDR/DME", "display_order": 4, "is_active": True, "guidelines": "Any of the following: >20 hemorrhages in each of 4 quadrants, definite venous beading in 2+ quadrants, prominent IRMA in 1+ quadrant."},
        {"impression": "Other Retinal", "display_order": 5, "is_active": True, "guidelines": "If  No DR / DME , BUT Any other retinal or disc pathology. Note disease in remarks."},
        {"impression": "Not Gradable", "display_order": 6, "is_active": True, "guidelines": " If cannot grade, mark as not gradable. Note signs in remarks."}
    ],
    
    # Age-related Macular Degeneration (AMD) gradings
    "AMD": [
        {"impression": "No AMD", "display_order": 1, "is_active": True, "guidelines": "No signs of age-related macular degeneration."},
        {"impression": "Early AMD", "display_order": 2, "is_active": True, "guidelines": "Few small drusen, pigmentary changes in the macula."},
        {"impression": "Intermediate AMD", "display_order": 3, "is_active": True, "guidelines": "Many medium-sized drusen, one or more large drusen, pigmentary changes."},
        {"impression": "Late AMD", "display_order": 4, "is_active": True, "guidelines": "Geographic atrophy (dry) or neovascular AMD (wet)."},
        {"impression": "Other Retinal", "display_order": 5, "is_active": True, "guidelines": "If  No AMD , BUT Any other retinal or disc pathology. Note disease in remarks."},
        {"impression": "Not Gradable", "display_order": 6, "is_active": True, "guidelines": " If cannot grade, mark as not gradable. Note signs in remarks."}
    ]
}


def setup_core_disease_gradings(dry_run: bool = False) -> None:
    """
    Set up standard gradings for core diseases.
    
    Args:
        dry_run: If True, only print what would be done without making changes
    """
    print("Preparing to set up standard gradings for core diseases...")
    
    with Session() as db:
        # Get core diseases from database
        core_diseases = {}
        for disease_id, disease_name in CORE_DISEASES.items():
            disease = db.get(Disease, disease_id)
            if disease:
                core_diseases[disease_name] = disease
            else:
                print(f"Warning: Core disease '{disease_name}' (ID: {disease_id}) not found in database.")
        
        if not core_diseases:
            print("No core diseases found in database. Please ensure core diseases exist first.")
            return
        
        total_gradings_added = 0
        total_gradings_updated = 0
        
        for disease_name, disease in core_diseases.items():
            if disease_name not in STANDARD_GRADINGS:
                print(f"No standard gradings defined for disease: {disease_name}")
                continue
            
            standard_gradings = STANDARD_GRADINGS[disease_name]
            print(f"Setting up gradings for {disease_name}...")
            
            # Get existing gradings for this disease
            existing_gradings = db.query(DiseaseGrading).filter(
                DiseaseGrading.disease_id == disease.id
            ).all()
            
            # Create a mapping of existing gradings by impression
            existing_by_impression = {g.impression: g for g in existing_gradings}
            
            for grading_data in standard_gradings:
                impression = grading_data["impression"]
                
                if impression in existing_by_impression:
                    # Update existing grading
                    existing_grading = existing_by_impression[impression]
                    changes_made = False
                    
                    # Update fields if they differ
                    if existing_grading.display_order != grading_data["display_order"]:
                        if not dry_run:
                            existing_grading.display_order = grading_data["display_order"]
                        changes_made = True
                    
                    if existing_grading.is_active != grading_data["is_active"]:
                        if not dry_run:
                            existing_grading.is_active = grading_data["is_active"]
                        changes_made = True
                    
                    new_guidelines = grading_data["guidelines"] or None
                    if existing_grading.guidelines != new_guidelines:
                        if not dry_run:
                            existing_grading.guidelines = new_guidelines
                        changes_made = True
                    
                    if changes_made:
                        total_gradings_updated += 1
                        if dry_run:
                            print(f"  Would update grading: {impression}")
                        else:
                            print(f"  Updated grading: {impression}")
                else:
                    # Create new grading
                    if dry_run:
                        print(f"  Would create grading: {impression}")
                    else:
                        new_grading = DiseaseGrading(
                            disease_id=disease.id,
                            impression=impression,
                            display_order=grading_data["display_order"],
                            is_active=grading_data["is_active"],
                            guidelines=grading_data["guidelines"] or None
                        )
                        db.add(new_grading)
                        print(f"  Created grading: {impression}")
                    total_gradings_added += 1
        
        if not dry_run:
            db.commit()
            print(f"Setup completed: {total_gradings_added} gradings created, {total_gradings_updated} gradings updated.")
        else:
            print(f"Dry run completed: Would create {total_gradings_added} gradings, update {total_gradings_updated} gradings.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up standard gradings for core diseases")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    args = parser.parse_args()
    
    setup_core_disease_gradings(dry_run=args.dry_run)