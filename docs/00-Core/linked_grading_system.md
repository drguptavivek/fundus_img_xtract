# Linked Grading System

The Linked Grading system allows for the grouping of diseases that should be graded together on the same image. A primary disease (e.g., Diabetic Retinopathy) can have one or more linked diseases (e.g., Diabetic Macular Edema) associated with it.

## Data Model

### LinkedDiseaseGrading
The core of the system is the `LinkedDiseaseGrading` model, which establishes a one-to-one relationship from a linked disease to a primary disease.

- **primary_disease_id**: The ID of the parent disease (e.g., DR).
- **linked_disease_id**: The ID of the disease that is triggered when the primary is assigned (e.g., DME).
- **display_order**: Controls the sequence in which linked diseases appear in the UI.
- **is_active**: Toggle for enabling/disabling the link without deleting the record.

### Constraints
- **Unique Link**: A disease can only be a "linked disease" for one primary disease at a time (`uq_linked_disease_unique`).
- **Self-Link Prevention**: A disease cannot be linked to itself (`ck_linked_disease_not_self`).
- **Global Uniqueness**: Task uniqueness is still enforced at the image/disease level, ensuring consistent data across the system.

## Core Logic

### Identification
- **Primary Disease**: A disease that has other diseases linked to it.
- **Linked Disease**: A disease that is explicitly associated with a primary disease.

### Utilities (`utils/linkedGradingUtils.py`)
- `get_linked_disease_ids(db, primary_id)`: Retrieves all active linked disease IDs for a given primary.
- `get_primary_disease_id(db, disease_id)`: Finds the primary ID for any given disease ID (returns itself if it's already primary or unlinked).
- `expand_primary_disease_ids(db, ids)`: Flattens a list of primary IDs to include all their linked counterparts.
