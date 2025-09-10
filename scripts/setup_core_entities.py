#!/usr/bin/env python3
"""
Setup script to initialize core hospitals, lab units, cameras, and areas in the database.
This script should be run once to populate the database with initial data.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from models import Session, Hospital, LabUnit, Camera, Area

# Core data that must always exist
# Note: These are example data. You should modify these lists based on your actual requirements.

# Core hospitals
CORE_HOSPITALS = [
    {"id": 1, "name": "RPC AIIMS"},
    {"id": 2, "name": "GTB Hospital"}]

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

def main():
    """Main function to setup all core data."""
    print("Setting up core hospitals, lab units, cameras, and areas...")
    
    with Session() as db:
        try:
            # Setup all core data
            setup_core_hospitals(db)
            setup_core_lab_units(db)
            setup_core_cameras(db)
            setup_core_areas(db)
            
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
            
        except Exception as e:
            db.rollback()
            print(f"\n❌ Error setting up core data: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()