"""Seed core entities data

Revision ID: 691d42ba3fff
Revises: 5a49784f68f1
Create Date: 2025-11-07 18:26:00.251215

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# Core data definitions mirrored from scripts/setup_core_entities.py
CORE_HOSPITALS = [
    {"id": 1, "name": "RPC AIIMS"},
    {"id": 2, "name": "UCMS GTB Hosp"},
]

CORE_LAB_UNITS = [
    {"id": 1, "name": "Community Ophthalmology", "hospital_id": 1},
    {"id": 2, "name": "Retina Lab", "hospital_id": 1},
    {"id": 3, "name": "Glaucoma Lab", "hospital_id": 1},
    {"id": 4, "name": "Glaucoma-GTBH", "hospital_id": 2},
]

CORE_CAMERAS = [
    {"id": 1, "name": "Remedio FOP"},
    {"id": 2, "name": "Zeiss Cirrus HD-OCT"},
    {"id": 3, "name": "Heidelberg Spectralis"},
    {"id": 4, "name": "Optos Daytona"},
    {"id": 5, "name": "Nidek RS-3000 Advance"},
    {"id": 6, "name": "Kowa VX-10"},
    {"id": 7, "name": "Canon CR-2 AF"},
    {"id": 8, "name": "Carl Zeiss Meditec VISUCAM 500"},
    {"id": 9, "name": "Topcon Maestro2"},
]

CORE_AREAS = [
    {"id": 1, "name": "Retina Macular Focus"},
    {"id": 2, "name": "Retina Disc Focus"},
    {"id": 3, "name": "Cornea"},
    {"id": 4, "name": "Both Eyes"},
]

CORE_DISEASES = {
    1: "Glaucoma",
    2: "DR",
    3: "Dry AMD",
    4: "DME",
}

STANDARD_GRADINGS = {
    "Glaucoma": [
        {
            "impression": "Normal",
            "display_order": 1,
            "is_active": True,
            "guidelines": "No signs of glaucomatous changes. No Other Referrable disease",
        },
        {
            "impression": "Suspect",
            "display_order": 2,
            "is_active": True,
            "guidelines": "<ul><li>Vertical CDR >= 0.8&nbsp;</li><li>ISNT Rule &nbsp;violated&nbsp;</li><li>Baring of Circulminear vessels&nbsp;</li><li>Bayonet Sign&nbsp;</li><li>Beta Zone PPA &nbsp;</li><li>OD haemmorhages</li></ul>",
        },
        {
            "impression": "Glaucoma",
            "display_order": 3,
            "is_active": True,
            "guidelines": "<p><strong>Hard Signs of Glaucoma&nbsp;</strong></p><ul><li>RNFL Loss&nbsp;</li><li>Focal NRR defects&nbsp;</li><li>Total cupping.</li></ul>",
        },
        {
            "impression": "Other Retinal",
            "display_order": 4,
            "is_active": True,
            "guidelines": "If  No Glaucoma/ Not Glaucoma suspect BUT Any other retinal or disc pathology. Note disease in remarks",
        },
        {
            "impression": "Not Gradable",
            "display_order": 5,
            "is_active": True,
            "guidelines": "<p>If cannot grade, mark as not gradable.&nbsp;</p><p>Note reason not gradable in remarks.</p>",
        },
    ],
    "DR": [
        {
            "impression": "No DR",
            "display_order": 1,
            "is_active": True,
            "guidelines": "No signs of diabetic retinopathy.",
        },
        {
            "impression": "Mild DR",
            "display_order": 2,
            "is_active": True,
            "guidelines": "Few microaneurysms only.",
        },
        {
            "impression": "Moderate NPDR",
            "display_order": 3,
            "is_active": True,
            "guidelines": "Microaneurysms and other signs (such as dot and blot haemorrhages, hard exudates,cotton wool spots), but less than severe nonproliferative diabetic retinopathy.",
        },
        {
            "impression": "Severe NPDR",
            "display_order": 4,
            "is_active": True,
            "guidelines": "Moderate NPDR with Any of the following: <ul> <li> >20 hemorrhages in each of 4 quadrants,</li> <li> definite venous beading in 2+ quadrants, </li> <li>  prominent IRMA in 1+ quadrant.</li> </ul> ",
        },
        {
            "impression": "PDR",
            "display_order": 5,
            "is_active": True,
            "guidelines": "Severe nonproliferative diabetic retinopathy and one or more of the following:<ul><li> Neovascularization </li> <li> Vitreous / Preretinal Haemmorhage </li> </ul>",
        },
        {
            "impression": "Other Retinal",
            "display_order": 6,
            "is_active": True,
            "guidelines": "<p>If No DR / DME , <strong>BUT Any other retinal or disc pathology</strong>. Note disease in remarks.</p>",
        },
        {
            "impression": "Not Gradable",
            "display_order": 7,
            "is_active": True,
            "guidelines": " If cannot grade, mark as not gradable. Note signs in remarks.",
        },
    ],
    "Dry AMD": [
        {
            "impression": "No AMD",
            "display_order": 1,
            "is_active": True,
            "guidelines": "No signs of age-related macular degeneration.",
        },
        {
            "impression": "Early AMD",
            "display_order": 2,
            "is_active": True,
            "guidelines": "<p>Medium drusen &gt;63 μm and ≤125 μm and No AMD pigmentary abnormalities within 2 disc diameters of fovea</p>",
        },
        {
            "impression": "Intermediate AMD",
            "display_order": 3,
            "is_active": True,
            "guidelines": "<p>Large drusen &gt; 125 μm and/or Any AMD pigmentary abnormalities within 2 disc diameters of fovea</p>",
        },
        {
            "impression": "Late AMD",
            "display_order": 4,
            "is_active": True,
            "guidelines": "<p>Any geographic atrophy</p>",
        },
        {
            "impression": "Other Retinal",
            "display_order": 5,
            "is_active": True,
            "guidelines": "<p>If No AMD , <strong>BUT Any other retinal or disc pathology.</strong> Note disease in remarks.</p>",
        },
        {
            "impression": "Not Gradable",
            "display_order": 6,
            "is_active": True,
            "guidelines": "<p>If cannot grade, mark as not gradable. Note reasons in remarks.</p>",
        },
    ],
    "DME": [
        {
            "impression": "M0 No DME",
            "display_order": 1,
            "is_active": True,
            "guidelines": "No diabetic macular edema.",
        },
        {
            "impression": "M1 Referable Diabetic Maculopathy",
            "display_order": 2,
            "is_active": True,
            "guidelines": (
                "<ul>"
                "<li>Exudate within 1 disc diameter (DD) of the centre of the fovea, OR</li>"
                "<li>A group of exudates within the macula (area ≥ half the disc area) and this area is all within the macular area.</li>"
                "</ul>"
            ),
        },
        {
            "impression": "Not Gradable",
            "display_order": 3,
            "is_active": True,
            "guidelines": "If cannot grade, mark as not gradable. Note reasons in remarks.",
        },
    ],
}

SAMPLE_FEATURES = {
    "Glaucoma": {
        "Normal": {
            "features": [],
            "remarks": "No signs of glaucomatous changes. No Other Referrable disease",
        },
        "Suspect": {
            "features": [
                {"sr_no": 1, "label": "Vertical CDR >= 0.8"},
                {"sr_no": 2, "label": "ISNT Rule violated"},
                {"sr_no": 3, "label": "Baring of Circumlinear vessels"},
                {"sr_no": 4, "label": "Bayonet Sign"},
                {"sr_no": 5, "label": "Beta Zone PPA"},
                {"sr_no": 6, "label": "Optic disc hemorrhages"},
            ],
            "remarks": "Suspect glaucoma based on clinical signs",
        },
        "Glaucoma": {
            "features": [
                {"sr_no": 1, "label": "RNFL Loss"},
                {"sr_no": 2, "label": "Focal NRR defects"},
                {"sr_no": 3, "label": "Total cupping"},
            ],
            "remarks": "Definite glaucoma with hard signs",
        },
        "Other Retinal": {
            "features": [],
            "remarks": "No Glaucoma/Not Glaucoma suspect BUT Any other retinal or disc pathology. Note disease in remarks",
        },
        "Not Gradable": {
            "features": [
                {"sr_no": 1, "label": "Media opacity (cataract/hemorrhage)"},
                {"sr_no": 2, "label": "Poor focus or defocus"},
                {"sr_no": 3, "label": "Small pupil / inadequate dilation"},
                {"sr_no": 4, "label": "Glare or reflection artifact"},
                {"sr_no": 5, "label": "Incomplete optic disc capture"},
            ],
            "remarks": "Cannot grade due to poor image quality or other factors",
        },
    },
    "DR": {
        "No DR": {
            "features": [],
            "remarks": "No signs of diabetic retinopathy",
        },
        "Mild DR": {
            "features": [
                {"sr_no": 1, "label": "Microaneurysms"},
            ],
            "remarks": "Mild non-proliferative diabetic retinopathy",
        },
        "Moderate NPDR": {
            "features": [
                {"sr_no": 1, "label": "Microaneurysms"},
                {"sr_no": 2, "label": "Dot and blot hemorrhages"},
                {"sr_no": 3, "label": "Hard exudates"},
                {"sr_no": 4, "label": "Cotton wool spots"},
            ],
            "remarks": "Moderate non-proliferative diabetic retinopathy",
        },
        "Severe NPDR": {
            "features": [
                {"sr_no": 1, "label": ">20 hemorrhages in each of 4 quadrants"},
                {"sr_no": 2, "label": "Definite venous beading in 2+ quadrants"},
                {"sr_no": 3, "label": "Prominent IRMA in 1+ quadrant"},
            ],
            "remarks": "Severe non-proliferative diabetic retinopathy",
        },
        "PDR": {
            "features": [
                {"sr_no": 1, "label": "Neovascularization"},
                {"sr_no": 2, "label": "Vitreous/Preretinal Hemorrhage"},
            ],
            "remarks": "Proliferative diabetic retinopathy",
        },
        "Other Retinal": {
            "features": [],
            "remarks": "No DR/DME BUT Any other retinal or disc pathology. Note disease in remarks",
        },
        "Not Gradable": {
            "features": [
                {"sr_no": 1, "label": "Media opacity (cataract/hemorrhage)"},
                {"sr_no": 2, "label": "Poor focus or motion blur"},
                {"sr_no": 3, "label": "Small pupil / inadequate dilation"},
                {"sr_no": 4, "label": "Glare or reflection artifact"},
                {"sr_no": 5, "label": "Inadequate field of view"},
            ],
            "remarks": "Cannot grade due to poor image quality or other factors",
        },
    },
    "DME": {
        "M0 No DME": {
            "features": [],
            "remarks": "No diabetic macular edema",
        },
        "M1 Referable Diabetic Maculopathy": {
            "features": [
                {"sr_no": 1, "label": "Exudate within 1 disc diameter of the centre of the fovea"},
                {"sr_no": 2, "label": "Group of exudates within macula (area ≥ half disc area) within macular area"},
            ],
            "remarks": "Referable diabetic maculopathy",
        },
        "Not Gradable": {
            "features": [],
            "remarks": "Cannot grade due to poor image quality or other factors",
        },
    },
    "Dry AMD": {
        "No AMD": {
            "features": [],
            "remarks": "No signs of age-related macular degeneration",
        },
        "Early AMD": {
            "features": [],
            "remarks": "Early age-related macular degeneration",
        },
        "Intermediate AMD": {
            "features": [
                {"sr_no": 1, "label": "Large drusen > 125 μm"},
                {"sr_no": 2, "label": "Any AMD pigmentary abnormalities"},
            ],
            "remarks": "Intermediate age-related macular degeneration",
        },
        "Late AMD": {
            "features": [],
            "remarks": "Late age-related macular degeneration",
        },
        "Other Retinal": {
            "features": [],
            "remarks": "No AMD BUT Any other retinal or disc pathology. Note disease in remarks",
        },
        "Not Gradable": {
            "features": [
                {"sr_no": 1, "label": "Media opacity (cataract/hemorrhage)"},
                {"sr_no": 2, "label": "Poor focus or motion blur"},
                {"sr_no": 3, "label": "Small pupil / inadequate dilation"},
                {"sr_no": 4, "label": "Glare or reflection artifact"},
                {"sr_no": 5, "label": "Inadequate field of view"},
            ],
            "remarks": "Cannot grade due to poor image quality or other factors",
        },
    },
}


# revision identifiers, used by Alembic.
revision: str = '691d42ba3fff'
down_revision: Union[str, Sequence[str], None] = '5a49784f68f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(connection, table_name: str) -> bool:
    result = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return bool(result.scalar())


def upgrade() -> None:
    """Seed core entities data safely using raw SQL."""
    connection = op.get_bind()

    required_tables = [
        "hospitals",
        "areas",
        "cameras",
        "lab_units",
        "diseases",
        "disease_gradings",
        "gradings_features",
    ]

    missing_tables = [table for table in required_tables if not _table_exists(connection, table)]
    if missing_tables:
        print(f"❌ Required tables missing ({', '.join(missing_tables)}) - skipping data seeding")
        return

    print("✅ Database tables found - proceeding with data seeding")

    # Use raw SQL to insert core data instead of ORM
    try:
        # Insert core hospitals
        connection.execute(sa.text("""
            INSERT INTO hospitals (id, name) VALUES
            (1, 'RPC AIIMS'),
            (2, 'UCMS GTB Hosp')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        # Insert core areas
        connection.execute(sa.text("""
            INSERT INTO areas (id, name) VALUES
            (1, 'Retina Macular Focus'),
            (2, 'Retina Disc Focus'),
            (3, 'Cornea'),
            (4, 'Both Eyes')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        # Insert core cameras
        connection.execute(sa.text("""
            INSERT INTO cameras (id, name) VALUES
            (1, 'Remedio FOP'),
            (2, 'Zeiss Cirrus HD-OCT'),
            (3, 'Heidelberg Spectralis'),
            (4, 'Optos Daytona'),
            (5, 'Nidek RS-3000 Advance'),
            (6, 'Kowa VX-10'),
            (7, 'Canon CR-2 AF'),
            (8, 'Carl Zeiss Meditec VISUCAM 500'),
            (9, 'Topcon Maestro2')
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
        """))

        # Insert core lab units (with hospital_id to satisfy NOT NULL constraint)
        connection.execute(sa.text("""
            INSERT INTO lab_units (id, name, hospital_id) VALUES
            (1, 'Community Ophthalmology', 1),
            (2, 'Retina Lab', 1),
            (3, 'Glaucoma Lab', 1),
            (4, 'Glaucoma-GTBH', 2)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, hospital_id = EXCLUDED.hospital_id
        """))

        # Insert core diseases
        connection.execute(
            sa.text(
                """
                INSERT INTO diseases (id, name) VALUES
                (1, 'Glaucoma'),
                (2, 'DR'),
                (3, 'Dry AMD'),
                (4, 'DME')
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """
            )
        )

        disease_ids_by_name = {name: disease_id for disease_id, name in CORE_DISEASES.items()}

        # Insert standard disease gradings
        for disease_name, gradings in STANDARD_GRADINGS.items():
            disease_id = disease_ids_by_name[disease_name]
            for grading in gradings:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO disease_gradings (disease_id, impression, display_order, is_active, guidelines)
                        VALUES (:disease_id, :impression, :display_order, :is_active, :guidelines)
                        ON CONFLICT (disease_id, impression)
                        DO UPDATE SET display_order = EXCLUDED.display_order,
                                      is_active = EXCLUDED.is_active,
                                      guidelines = EXCLUDED.guidelines
                        """
                    ),
                    {
                        "disease_id": disease_id,
                        "impression": grading["impression"],
                        "display_order": grading["display_order"],
                        "is_active": grading["is_active"],
                        "guidelines": grading["guidelines"],
                    },
                )

        # Insert grading features mapped to the created disease_gradings
        for disease_name, impressions in SAMPLE_FEATURES.items():
            disease_id = disease_ids_by_name[disease_name]
            for impression_name, sample_data in impressions.items():
                grading_id = connection.execute(
                    sa.text(
                        """
                        SELECT id FROM disease_gradings
                        WHERE disease_id = :disease_id AND impression = :impression
                        """
                    ),
                    {"disease_id": disease_id, "impression": impression_name},
                ).scalar()

                if not grading_id or not sample_data["features"]:
                    continue

                for feature in sample_data["features"]:
                    connection.execute(
                        sa.text(
                            """
                            INSERT INTO gradings_features (disease_grading_id, sr_no, label)
                            VALUES (:grading_id, :sr_no, :label)
                            ON CONFLICT (disease_grading_id, sr_no)
                            DO UPDATE SET label = EXCLUDED.label
                            """
                        ),
                        {
                            "grading_id": grading_id,
                            "sr_no": feature["sr_no"],
                            "label": feature["label"],
                        },
                    )

        # Sync sequences so future inserts pick the next available IDs
        for table_name in (
            "hospitals",
            "areas",
            "cameras",
            "lab_units",
            "diseases",
            "disease_gradings",
            "gradings_features",
        ):
            connection.execute(sa.text(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table_name}', 'id'),
                    (SELECT COALESCE(MAX(id), 1) FROM {table_name})
                )
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
                            DiseaseGrading.disease_id.in_([1, 2, 3, 4])  # Core disease IDs
                        )
                    ).scalars().all()
                )
            )
        )
        
        # Remove disease gradings for core diseases
        db.execute(
            delete(DiseaseGrading).where(
                DiseaseGrading.disease_id.in_([1, 2, 3, 4])  # Core disease IDs
            )
        )
        
        # Remove core diseases
        db.execute(delete(Disease).where(Disease.id.in_([1, 2, 3, 4])))
        
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
        
