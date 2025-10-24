#!/usr/bin/env python3
"""Script to populate sample features for disease gradings based on existing grading guidelines."""

from __future__ import annotations

import sys
import json
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, delete
from models import Base, engine, Session, Disease, DiseaseGrading, GradingsFeatures

# Sample features for each disease grading - using simplified sr_no and label structure
SAMPLE_FEATURES = {
    "Glaucoma": {
        "Normal": {
            "features": [],
            "remarks": "No signs of glaucomatous changes. No Other Referrable disease"
        },
        "Suspect": {
            "features": [
                {"sr_no": 1, "label": "Vertical CDR >= 0.8"},
                {"sr_no": 2, "label": "ISNT Rule violated"},
                {"sr_no": 3, "label": "Baring of Circumlinear vessels"},
                {"sr_no": 4, "label": "Bayonet Sign"},
                {"sr_no": 5, "label": "Beta Zone PPA"},
                {"sr_no": 6, "label": "Optic disc hemorrhages"}
            ],
            "remarks": "Suspect glaucoma based on clinical signs"
        },
        "Glaucoma": {
            "features": [
                {"sr_no": 1, "label": "RNFL Loss"},
                {"sr_no": 2, "label": "Focal NRR defects"},
                {"sr_no": 3, "label": "Total cupping"}
            ],
            "remarks": "Definite glaucoma with hard signs"
        },
        "Other Retinal": {
            "features": [],
            "remarks": "No Glaucoma/Not Glaucoma suspect BUT Any other retinal or disc pathology. Note disease in remarks"
        },
        "Not Gradable": {
            "features": [],
            "remarks": "Cannot grade due to poor image quality or other factors"
        }
    },
    "DR": {
        "No DR": {
            "features": [],
            "remarks": "No signs of diabetic retinopathy"
        },
        "Mild DR": {
            "features": [
                {"sr_no": 1, "label": "Microaneurysms"}
            ],
            "remarks": "Mild non-proliferative diabetic retinopathy"
        },
        "Moderate NPDR": {
            "features": [
                {"sr_no": 1, "label": "Microaneurysms"},
                {"sr_no": 2, "label": "Dot and blot hemorrhages"},
                {"sr_no": 3, "label": "Hard exudates"},
                {"sr_no": 4, "label": "Cotton wool spots"}
            ],
            "remarks": "Moderate non-proliferative diabetic retinopathy"
        },
        "Severe NPDR": {
            "features": [
                {"sr_no": 1, "label": ">20 hemorrhages in each of 4 quadrants"},
                {"sr_no": 2, "label": "Definite venous beading in 2+ quadrants"},
                {"sr_no": 3, "label": "Prominent IRMA in 1+ quadrant"}
            ],
            "remarks": "Severe non-proliferative diabetic retinopathy"
        },
        "PDR": {
            "features": [
                {"sr_no": 1, "label": "Neovascularization"},
                {"sr_no": 2, "label": "Vitreous/Preretinal Hemorrhage"}
            ],
            "remarks": "Proliferative diabetic retinopathy"
        },
        "Other Retinal": {
            "features": [],
            "remarks": "No DR/DME BUT Any other retinal or disc pathology. Note disease in remarks"
        },
        "Not Gradable": {
            "features": [],
            "remarks": "Cannot grade due to poor image quality or other factors"
        }
    },
    "AMD": {
        "No AMD": {
            "features": [],
            "remarks": "No signs of age-related macular degeneration"
        },
        "Early AMD": {
            "features": [
                {"sr_no": 1, "label": "Few small drusen"},
                {"sr_no": 2, "label": "Pigmentary changes"}
            ],
            "remarks": "Early age-related macular degeneration"
        },
        "Intermediate AMD": {
            "features": [
                {"sr_no": 1, "label": "Many medium-sized drusen"},
                {"sr_no": 2, "label": "One or more large drusen"},
                {"sr_no": 3, "label": "Pigmentary changes"}
            ],
            "remarks": "Intermediate age-related macular degeneration"
        },
        "Late AMD": {
            "features": [
                {"sr_no": 1, "label": "Geographic atrophy"},
                {"sr_no": 2, "label": "Neovascular AMD"}
            ],
            "remarks": "Late age-related macular degeneration"
        },
        "Other Retinal": {
            "features": [],
            "remarks": "No AMD BUT Any other retinal or disc pathology. Note disease in remarks"
        },
        "Not Gradable": {
            "features": [],
            "remarks": "Cannot grade due to poor image quality or other factors"
        }
    }
}

def populate_sample_features():
    """Populate sample features for all existing disease gradings."""
    print("🚀 Starting to populate sample features for disease gradings...")
    print("=" * 60)
    
    try:
        with Session() as db:
            # Get all diseases
            diseases = db.execute(select(Disease)).scalars().all()
            print(f"Found {len(diseases)} diseases in the database")
            
            total_updated = 0
            total_skipped = 0
            
            for disease in diseases:
                print(f"\nProcessing disease: {disease.name}")
                
                # Get all gradings for this disease
                gradings = db.execute(
                    select(DiseaseGrading).where(DiseaseGrading.disease_id == disease.id)
                ).scalars().all()
                
                print(f"  Found {len(gradings)} gradings for {disease.name}")
                
                for grading in gradings:
                    # Check if we have sample features for this disease and impression
                    if disease.name in SAMPLE_FEATURES and grading.impression in SAMPLE_FEATURES[disease.name]:
                        sample_data = SAMPLE_FEATURES[disease.name][grading.impression]
                        
                        # Create the JSON structure
                        features_json = json.dumps({
                            "features": sample_data["features"],
                            "remarks": sample_data["remarks"]
                        }, indent=2)
                        
                        # Update the grading with new features structure
                        # Delete existing features and create new ones
                        db.execute(
                            delete(GradingsFeatures).where(GradingsFeatures.disease_grading_id == grading.id)
                        )
                        
                        # Add new features from sample data
                        for i, feature_data in enumerate(sample_data["features"], 1):
                            feature = GradingsFeatures(
                                disease_grading_id=grading.id,
                                sr_no=feature_data["sr_no"],
                                label=feature_data["label"]
                            )
                            db.add(feature)
                        
                        # Note: We're not setting features_json anymore as it's deprecated
                        total_updated += 1
                        print(f"    ✓ Updated: {grading.impression}")
                    else:
                        total_skipped += 1
                        print(f"    ⚠ Skipped: {grading.impression} (no sample features defined)")
            
            # Commit all changes
            db.commit()
            
            print("\n" + "=" * 60)
            print("✅ Sample features population completed!")
            print(f"Total gradings updated: {total_updated}")
            print(f"Total gradings skipped: {total_skipped}")
            
            # Show summary of what was updated
            print("\nSummary of updated gradings:")
            for disease_name in SAMPLE_FEATURES:
                print(f"\n{disease_name}:")
                for impression_name in SAMPLE_FEATURES[disease_name]:
                    sample_data = SAMPLE_FEATURES[disease_name][impression_name]
                    features_count = len(sample_data["features"])
                    print(f"  - {impression_name}: {features_count} features")
            
    except Exception as e:
        print(f"\n❌ Error during sample features population: {e}")
        sys.exit(1)

def main():
    """Main function to run the sample features population."""
    print("Fundus Image Manager - Sample Features Population Script")
    print("This script will populate sample features for all existing disease gradings")
    print("based on the grading guidelines defined in scripts/initial_setup.py")
    print()
    
    # Skip interactive confirmation for automated execution
    print("Proceeding with sample features population...")
    
    populate_sample_features()
    
    print("\nNext steps:")
    print("1. Review the updated disease gradings in the admin interface")
    print("2. Test the grading interface to ensure features are displayed correctly")
    print("3. Modify the sample features as needed for your specific use case")

if __name__ == "__main__":
    main()