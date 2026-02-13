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

Linked chains are resolved recursively so A → B → C returns `[B, C]` for primary A.

## Arbitrator Linked Grading

### Arbitrator Context
Arbitrators review tasks when resident and resident2 grades don't match (consensus needed). With linked diseases, arbitrators need context from related disease grades to make informed decisions.

### Carousel for Context
- Arbitrator sees primary + linked diseases in carousel
- Each disease has independent consensus requirement
- Editability based on task state:
  - Primary in 'arbitration' → Editable (need arbitrator decision)
  - Linked in 'arbitration' → Editable (need arbitrator decision)
  - Any disease in 'final' → Read-only (already matched)

### Task States and Visibility
Four scenarios for arbitrator:
1. **Primary matched, linked not**: Primary read-only (done), linked editable (needs arbitration)
2. **Linked matched, primary not**: Primary editable (needs arbitration), linked read-only (done)
3. **Both matched**: Task not shown on dashboard (fully consensused, nothing to arbitrate)
4. **Both unmatched**: Both editable (arbitrator decides both)

### Independent Consensus
- Each disease tracks grades and consensus separately
- Arbitrator decision on DR doesn't affect DME consensus logic
- Both can be submitted together but resolved independently

## Task Creation Policy

- Linked tasks are created when a primary task is created (task creation service).
- The grading UI does not create linked tasks on-demand.
- Legacy primaries created before a link existed remain unlinked unless backfilled.

## Allocation Guardrails

Primary tasks are excluded from standard resident/resident2 queues when linked tasks exist and are in mismatch states:
- Primary `resident_done` + linked `pending`
- Primary `resident2_done`/`final` + linked `resident_done`

This prevents growing inconsistencies in the main grading queue.

## Linked Follow-up Flow

- Follow-up entrypoints appear per primary disease as `Pending <LinkedDiseaseName>`.
- Follow-up grading opens the **linked disease task directly** (no primary redirect).
- In follow-up mode, the **target linked task is editable** if the user is eligible.
- The primary task is not auto-loaded as a separate editable panel.
- Resident2 is preferred when the user has eligibility; otherwise resident.

## Dashboard and KPI Behavior

- Linked-only diseases are not shown as standalone grading cards.
- Pending counts for primary diseases exclude certain linked mismatch states to avoid inconsistent queues.
- Linked follow-up counts are derived from primary/link mismatch states and shown under the primary disease card.
