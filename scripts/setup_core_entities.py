#!/usr/bin/env python3
"""
Setup script to initialize core entities in the database.
This script contains all core entity definitions and setup functions.
"""

import sys
import json
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select, delete
from models import Session, Hospital, LabUnit, Camera, Area, Disease, DiseaseGrading, GradingsFeatures

# Core data that must always exist

# Core hospitals
CORE_HOSPITALS = [
    {"id": 1, "name": "RPC AIIMS"},
    {"id": 2, "name": "UCMS GTB Hosp"}
]

# Core lab units (associated with hospitals)
CORE_LAB_UNITS = [
    {"id": 1, "name": "Community Ophthalmology", "hospital_id": 1},
    {"id": 2, "name": "Retina Lab", "hospital_id": 1},
    {"id": 3, "name": "Glaucoma Lab", "hospital_id": 1},
    {"id": 4, "name": "Glaucoma-GTBH", "hospital_id": 2}
]

# Core cameras
CORE_CAMERAS = [
    {"id": 1, "name": "Remedio FOP"},
    {"id": 2, "name": "Zeiss Cirrus HD-OCT"},
    {"id": 3, "name": "Heidelberg Spectralis"},
    {"id": 4, "name": "Optos Daytona"},
    {"id": 5, "name": "Nidek RS-3000 Advance"},
    {"id": 6, "name": "Kowa VX-10"},
    {"id": 7, "name": "Canon CR-2 AF"},
    {"id": 8, "name": "Carl Zeiss Meditec VISUCAM 500"},
    {"id": 9, "name": "Topcon Maestro2"}
]

# Core areas
CORE_AREAS = [
    {"id": 1, "name": "Retina Macular Focus"},
    {"id": 2, "name": "Retina Disc Focus"},
    {"id": 3, "name": "Cornea"},
    {"id": 4, "name": "Both Eyes"}
]

# Core diseases
CORE_DISEASES = {
    1: "Glaucoma",
    2: "DR",  # Diabetic Retinopathy
    3: "AMD"  # Age-related Macular Degeneration
}

# Standard gradings for each core disease
STANDARD_GRADINGS = {
    # Glaucoma gradings
    "Glaucoma": [
        {"impression": "Normal", "display_order": 1, "is_active": True, "guidelines": "No signs of glaucomatous changes. No Other Referrable disease"},
        {"impression": "Suspect", "display_order": 2, "is_active": True, "guidelines": "<ul><li>Vertical CDR >= 0.8&nbsp;</li><li>ISNT Rule &nbsp;violated&nbsp;</li><li>Baring of Circulminear vessels&nbsp;</li><li>Bayonet Sign&nbsp;</li><li>Beta Zone PPA &nbsp;</li><li>OD haemmorhages</li></ul>"},
        {"impression": "Glaucoma", "display_order": 3, "is_active": True, "guidelines": "<p><strong>Hard Signs of Glaucoma&nbsp;</strong></p><ul><li>RNFL Loss&nbsp;</li><li>Focal NRR defects&nbsp;</li><li>Total cupping.</li></ul>"},
        {"impression": "Other Retinal", "display_order": 4, "is_active": True, "guidelines": "If  No Glaucoma/ Not Glaucoma suspect BUT Any other retinal or disc pathology. Note disease in remarks"},
        {"impression": "Not Gradable", "display_order": 5, "is_active": True, "guidelines": "<p>If cannot grade, mark as not gradable.&nbsp;</p><p>Note reason not gradable in remarks.</p>"},
    ],
    
    # Diabetic Retinopathy (DR) gradings
    "DR": [
        {"impression": "No DR", "display_order": 1, "is_active": True, "guidelines": "No signs of diabetic retinopathy."},
        {"impression": "Mild DR", "display_order": 2, "is_active": True, "guidelines": "Few microaneurysms only."},
        {"impression": "Moderate NPDR", "display_order": 3, "is_active": True, "guidelines": "Microaneurysms and other signs (such as dot and blot haemorrhages, hard exudates,cotton wool spots), but less than severe nonproliferative diabetic retinopathy."},
        {"impression": "Severe NPDR", "display_order": 4, "is_active": True, "guidelines": "Moderate NPDR with Any of the following: <ul> <li> >20 hemorrhages in each of 4 quadrants,</li> <li> definite venous beading in 2+ quadrants, </li> <li>  prominent IRMA in 1+ quadrant.</li> </ul> "},
        {"impression": "PDR", "display_order": 5, "is_active": True, "guidelines": "Severe nonproliferative diabetic retinopathy and one or more of the following:<ul><li> Neovascularization </li> <li> Vitreous / Preretinal Haemmorhage </li> </ul>"},
        {"impression": "Other Retinal", "display_order": 6, "is_active": True, "guidelines": "<p>If No DR / DME , <strong>BUT Any other retinal or disc pathology</strong>. Note disease in remarks.</p>"},
        {"impression": "Not Gradable", "display_order": 7, "is_active": True, "guidelines": " If cannot grade, mark as not gradable. Note signs in remarks."}
    ],
    
    # Age-related Macular Degeneration (AMD) gradings
    "AMD": [
        {"impression": "No AMD", "display_order": 1, "is_active": True, "guidelines": "No signs of age-related macular degeneration."},
        {"impression": "Early AMD", "display_order": 2, "is_active": True, "guidelines": "Few small drusen, pigmentary changes in the macula."},
        {"impression": "Intermediate AMD", "display_order": 3, "is_active": True, "guidelines": "Many medium-sized drusen, one or more large drusen, pigmentary changes."},
        {"impression": "Late AMD", "display_order": 4, "is_active": True, "guidelines": "Geographic atrophy (dry) or neovascular AMD (wet)."},
        {"impression": "Other Retinal", "display_order": 5, "is_active": True, "guidelines": "<p>If No AMD , <strong>BUT Any other retinal or disc pathology.</strong> Note disease in remarks.</p>"},
        {"impression": "Not Gradable", "display_order": 6, "is_active": True, "guidelines": "<p>If cannot grade, mark as not gradable. Note reasons in remarks.</p>"}
    ]
}

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

def setup_core_hospitals(db):
    """Setup core hospitals in the database."""
    print("Setting up core hospitals...")
    for hospital_data in CORE_HOSPITALS:
        # Check if hospital with this ID already exists
        existing = db.get(Hospital, hospital_data["id"])
        if existing:
            # If it exists but has a different name, update it
            if existing.name != hospital_data["name"]:
                existing.name = hospital_data["name"]
                db.add(existing)
                print(f"  Updated hospital ID {hospital_data['id']} to '{hospital_data['name']}'")
        else:
            # Create the hospital with the specific ID
            hospital = Hospital(id=hospital_data["id"], name=hospital_data["name"])
            db.add(hospital)
            print(f"  Created hospital ID {hospital_data['id']}: '{hospital_data['name']}'")
    
def setup_core_lab_units(db):
    """Setup core lab units in the database."""
    print("Setting up core lab units...")
    for lab_unit_data in CORE_LAB_UNITS:
        # Check if lab unit with this ID already exists
        existing = db.get(LabUnit, lab_unit_data["id"])
        if existing:
            # If it exists but has different data, update it
            if existing.name != lab_unit_data["name"] or existing.hospital_id != lab_unit_data["hospital_id"]:
                existing.name = lab_unit_data["name"]
                existing.hospital_id = lab_unit_data["hospital_id"]
                db.add(existing)
                print(f"  Updated lab unit ID {lab_unit_data['id']} to '{lab_unit_data['name']}' (Hospital ID: {lab_unit_data['hospital_id']})")
        else:
            # Create the lab unit with the specific ID
            lab_unit = LabUnit(id=lab_unit_data["id"], name=lab_unit_data["name"], hospital_id=lab_unit_data["hospital_id"])
            db.add(lab_unit)
            print(f"  Created lab unit ID {lab_unit_data['id']}: '{lab_unit_data['name']}' (Hospital ID: {lab_unit_data['hospital_id']})")

def setup_core_cameras(db):
    """Setup core cameras in the database."""
    print("Setting up core cameras...")
    for camera_data in CORE_CAMERAS:
        # Check if camera with this ID already exists
        existing = db.get(Camera, camera_data["id"])
        if existing:
            # If it exists but has a different name, update it
            if existing.name != camera_data["name"]:
                existing.name = camera_data["name"]
                db.add(existing)
                print(f"  Updated camera ID {camera_data['id']} to '{camera_data['name']}'")
        else:
            # Create the camera with the specific ID
            camera = Camera(id=camera_data["id"], name=camera_data["name"])
            db.add(camera)
            print(f"  Created camera ID {camera_data['id']}: '{camera_data['name']}'")

def setup_core_areas(db):
    """Setup core areas in the database."""
    print("Setting up core areas...")
    for area_data in CORE_AREAS:
        # Check if area with this ID already exists
        existing = db.get(Area, area_data["id"])
        if existing:
            # If it exists but has a different name, update it
            if existing.name != area_data["name"]:
                existing.name = area_data["name"]
                db.add(existing)
                print(f"  Updated area ID {area_data['id']} to '{area_data['name']}'")
        else:
            # Create the area with the specific ID
            area = Area(id=area_data["id"], name=area_data["name"])
            db.add(area)
            print(f"  Created area ID {area_data['id']}: '{area_data['name']}'")

def setup_core_diseases(db):
    """Setup core diseases (Glaucoma, DR, AMD)."""
    print("Setting up core diseases...")
    
    for disease_id, disease_name in CORE_DISEASES.items():
        # Check if disease with this ID already exists
        existing = db.get(Disease, disease_id)
        if existing:
            # If it exists but has a different name, update it
            if existing.name != disease_name:
                existing.name = disease_name
                db.add(existing)
                print(f"  Updated disease ID {disease_id} to '{disease_name}'")
        else:
            # Create the disease with the specific ID
            disease = Disease(id=disease_id, name=disease_name)
            db.add(disease)
            print(f"  Created disease ID {disease_id}: '{disease_name}'")

def setup_core_disease_gradings(db):
    """Setup standard gradings for core diseases."""
    print("Setting up core disease gradings...")
    
    # Get core diseases from database
    core_diseases = {}
    for disease_id, disease_name in CORE_DISEASES.items():
        disease = db.get(Disease, disease_id)
        if disease:
            core_diseases[disease_name] = disease
    
    total_gradings_added = 0
    
    for disease_name, disease in core_diseases.items():
        if disease_name not in STANDARD_GRADINGS:
            print(f"  No standard gradings defined for disease: {disease_name}")
            continue
        
        standard_gradings = STANDARD_GRADINGS[disease_name]
        print(f"  Setting up gradings for {disease_name}...")
        
        for grading_data in standard_gradings:
            # Check if grading with this disease_id and impression already exists
            existing_grading = db.execute(
                select(DiseaseGrading).where(
                    (DiseaseGrading.disease_id == disease.id) &
                    (DiseaseGrading.impression == grading_data["impression"])
                )
            ).scalar_one_or_none()
            
            if existing_grading:
                # Update existing grading if needed
                if (existing_grading.display_order != grading_data["display_order"] or
                    existing_grading.is_active != grading_data["is_active"] or
                    existing_grading.guidelines != grading_data["guidelines"]):
                    
                    existing_grading.display_order = grading_data["display_order"]
                    existing_grading.is_active = grading_data["is_active"]
                    existing_grading.guidelines = grading_data["guidelines"] or None
                    db.add(existing_grading)
                    print(f"    Updated grading: {grading_data['impression']}")
                else:
                    print(f"    Grading already exists: {grading_data['impression']}")
            else:
                # Create new grading
                new_grading = DiseaseGrading(
                    disease_id=disease.id,
                    impression=grading_data["impression"],
                    display_order=grading_data["display_order"],
                    is_active=grading_data["is_active"],
                    guidelines=grading_data["guidelines"] or None
                )
                db.add(new_grading)
                print(f"    Created grading: {grading_data['impression']}")
                total_gradings_added += 1
    
    print(f"  Created {total_gradings_added} disease gradings")

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

def setup_all_core_entities(db):
    """Setup all core entities (hospitals, lab units, cameras, areas, diseases, and gradings)."""
    print("Setting up all core entities...")
    
    # Setup basic entities
    setup_core_hospitals(db)
    setup_core_lab_units(db)
    setup_core_cameras(db)
    setup_core_areas(db)
    
    # Setup diseases and gradings
    setup_core_diseases(db)
    setup_core_disease_gradings(db)

def main():
    """Main function to setup all core data."""
    print("Setting up core hospitals, lab units, cameras, areas, diseases, and gradings...")
    
    with Session() as db:
        try:
            # Setup all core data
            setup_all_core_entities(db)
            
            # Commit all changes
            db.commit()
            print("\n✅ All core data has been set up successfully!")
            
            # Show final state
            print("\nFinal state:")
            hospitals = db.execute(select(Hospital)).scalars().all()
            print(f"  Hospitals: {len(hospitals)}")
            
            lab_units = db.execute(select(LabUnit)).scalars().all()
            print(f"  Lab Units: {len(lab_units)}")
            
            cameras = db.execute(select(Camera)).scalars().all()
            print(f"  Cameras: {len(cameras)}")
            
            areas = db.execute(select(Area)).scalars().all()
            print(f"  Areas: {len(areas)}")
            
            diseases = db.execute(select(Disease)).scalars().all()
            print(f"  Diseases: {len(diseases)}")
            
            gradings = db.execute(select(DiseaseGrading)).scalars().all()
            print(f"  Disease Gradings: {len(gradings)}")
            
        except Exception as e:
            db.rollback()
            print(f"\n❌ Error setting up core data: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()