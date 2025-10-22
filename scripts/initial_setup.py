#!/usr/bin/env python3
"""Initial setup script for the Fundus Image Manager."""

from __future__ import annotations

import shutil
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from models import Base, engine, Session, Hospital, LabUnit, Camera, Area, Disease, DiseaseGrading, User
from models import UPLOAD_DIR, PROCESSED_DIR, PROCESSING_ERROR_DIR, IMAGE_DIR
from models import DIRECT_UPLOAD_DIR, PDF_DIR, DR_PDF_DIR, GLAUCOMA_PDF_DIR
from models import SUCCESS_LOG, ERROR_LOG
from scripts.add_test_users import add_test_users
from scripts.create_test_admin import create_test_admin

# Core data that must always exist

# Core hospitals
CORE_HOSPITALS = [
    {"id": 1, "name": "RPC AIIMS"},
    {"id": 2, "name": "GTB Hospital"}
]

# Core lab units (associated with hospitals)
CORE_LAB_UNITS = [
    {"id": 1, "name": "Community Ophthalmology", "hospital_id": 1},
    {"id": 2, "name": "Retina Lab", "hospital_id": 1},
    {"id": 3, "name": "Glaucoma Lab", "hospital_id": 1},
    {"id": 4, "name": "Corena Lab", "hospital_id": 2},
    {"id": 5, "name": "Retina", "hospital_id": 2},
    {"id": 6, "name": "Glaucoma", "hospital_id": 2}
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
        {"impression": "Suspect", "display_order": 2, "is_active": True, "guidelines": "<ul><li>Vertical CDR &gt;= 0.8&nbsp;</li><li>ISNT Rule &nbsp;violated&nbsp;</li><li>Baring of Circulminear vessels&nbsp;</li><li>Bayonet Sign&nbsp;</li><li>Beta Zone PPA &nbsp;</li><li>OD haemmorhages</li></ul>"},
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

def reset_files_directory() -> None:
    """Clear the files directory and recreate required sub-directories."""
    files_root = project_root / "files"
    resolved_root = files_root.resolve()
    if project_root not in resolved_root.parents and resolved_root != project_root:
        raise RuntimeError(f"Refusing to delete non-project directory: {resolved_root}")

    if resolved_root.exists():
        print(f"Clearing files directory at {resolved_root}...")
        shutil.rmtree(resolved_root)
    resolved_root.mkdir(parents=True, exist_ok=True)
    print(f"  Recreated files directory: {resolved_root}")

    create_directories()


def create_directories() -> None:
    """Create all required directories if they are missing."""
    print("Preparing required directories...")

    directories = [
        UPLOAD_DIR,
        PROCESSED_DIR,
        PROCESSING_ERROR_DIR,
        IMAGE_DIR,
        DIRECT_UPLOAD_DIR,
        PDF_DIR,
        DR_PDF_DIR,
        GLAUCOMA_PDF_DIR,
        SUCCESS_LOG.parent,
        ERROR_LOG.parent,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"  Ready: {directory}")

def create_database():
    """Create a new blank database with all tables."""
    print("Creating database tables...")
    
    # Drop all tables first (if they exist)
    Base.metadata.drop_all(engine)
    
    # Create all tables
    Base.metadata.create_all(engine)
    print("  Database tables created successfully!")

def setup_core_entities(db):
    """Setup core hospitals, lab units, cameras, and areas."""
    print("Setting up core entities...")
    
    # Setup hospitals
    for hospital_data in CORE_HOSPITALS:
        hospital = Hospital(id=hospital_data["id"], name=hospital_data["name"])
        db.add(hospital)
        print(f"  Created hospital: {hospital_data['name']}")
    
    # Setup areas
    for area_data in CORE_AREAS:
        area = Area(id=area_data["id"], name=area_data["name"])
        db.add(area)
        print(f"  Created area: {area_data['name']}")
    
    # Setup cameras
    for camera_data in CORE_CAMERAS:
        camera = Camera(id=camera_data["id"], name=camera_data["name"])
        db.add(camera)
        print(f"  Created camera: {camera_data['name']}")
    
    # Setup lab units
    for lab_unit_data in CORE_LAB_UNITS:
        lab_unit = LabUnit(id=lab_unit_data["id"], name=lab_unit_data["name"], hospital_id=lab_unit_data["hospital_id"])
        db.add(lab_unit)
        print(f"  Created lab unit: {lab_unit_data['name']}")

def setup_core_diseases(db):
    """Setup core diseases (Glaucoma, DR, AMD)."""
    print("Setting up core diseases...")
    
    for disease_id, disease_name in CORE_DISEASES.items():
        disease = Disease(id=disease_id, name=disease_name)
        db.add(disease)
        print(f"  Created disease: {disease_name}")

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

def main():
    """Main function to run the initial setup."""
    print("🚀 Starting initial setup for Fundus Image Manager...")
    print("=" * 50)
    
    try:
        # Reset storage directories
        reset_files_directory()
        print()
        
        # Create database
        create_database()
        print()
        
        # Setup core data
        with Session() as db:
            setup_core_entities(db)
            setup_core_diseases(db)
            setup_core_disease_gradings(db)
            db.commit()
        print()

        print("Seeding default admin user...")
        create_test_admin()
        print()

        print("Seeding development test users...")
        add_test_users()
        
        print()
        print("✅ Initial setup completed successfully!")
        print()
        print("Summary:")
        with Session() as db:
            hospitals = db.execute(select(Hospital)).scalars().all()
            lab_units = db.execute(select(LabUnit)).scalars().all()
            cameras = db.execute(select(Camera)).scalars().all()
            areas = db.execute(select(Area)).scalars().all()
            diseases = db.execute(select(Disease)).scalars().all()
            gradings = db.execute(select(DiseaseGrading)).scalars().all()
            users = db.execute(select(User)).scalars().all()
            
            print(f"  Hospitals: {len(hospitals)}")
            print(f"  Lab Units: {len(lab_units)}")
            print(f"  Cameras: {len(cameras)}")
            print(f"  Areas: {len(areas)}")
            print(f"  Diseases: {len(diseases)}")
            print(f"  Disease Gradings: {len(gradings)}")
            print(f"  Users: {len(users)}")
        
        print()
        print("Default admin credentials -> username: admin / password: Vivek@2026")
        print("All seeded test users share the password: Vivek@2026")
        print()
        print("Next steps:")
        print("1. Create users: python scripts/create_user.py <username>")
        print("2. Assign roles: python scripts/assign_roles.py <username> --roles <role1> <role2>")
        print("3. Start the application: python app.py")
        
    except Exception as e:
        print(f"\n❌ Error during initial setup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
