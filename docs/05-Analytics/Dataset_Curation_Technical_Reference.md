# Dataset Curation - Technical Reference

## Overview

The Dataset Curation module (`analytics/route_dataset_curation.py`) provides a sophisticated filtering and selection system for creating curated datasets from graded fundus images. It enables researchers and data managers to select specific subsets of grading tasks based on multiple criteria including disease type, grades, AI model outputs, and consensus status.

## Architecture

### Database Models

#### CuratedDataset (`curated_datasets` table)
```python
class CuratedDataset(Base):
    id: int                      # Primary key
    uuid: str                    # Public identifier (UUID4)
    name: str                    # Dataset name
    purpose: str                 # Dataset purpose description
    filters_json: str            # JSON-encoded filter criteria
    disease_id: int              # Associated disease (FK)
    created_by_user_id: int      # Creator (FK to users)
    created_at: datetime         # Creation timestamp
    updated_at: datetime         # Last update timestamp
```

**Relationships:**
- `disease` → Disease (via `disease_id`)
- `created_by` → User (via `created_by_user_id`)
- `items` → List[CuratedDatasetItem] (cascade delete)

#### CuratedDatasetItem (`curated_dataset_items` table)
```python
class CuratedDatasetItem(Base):
    id: int                      # Primary key
    dataset_id: int              # Parent dataset (FK)
    task_id: int                 # Associated grading task (FK)
    include_in_export: bool      # Whether to include in export
    selection_method: str        # 'auto' or 'manual'
    selected_by_user_id: int     # Selector (FK to users)
    selected_at: datetime        # Selection timestamp
    created_at: datetime         # Record creation
    updated_at: datetime         # Last update
```

**Constraints:**
- Unique constraint on `(dataset_id, task_id)` - one item per task per dataset
- Check constraint: `selection_method IN ('auto', 'manual')`

### Route Handlers

#### 1. `/dataset-curation` (GET/POST)
**File:** `analytics/route_dataset_curation.py:154-276`

**Roles Required:** `admin`, `local_admin`, `data_manager`, `data_exporter`, `dataset_creator`, `analytics_viewer`

**GET Response:**
- Lists recent 20 datasets (ordered by creation date, descending)
- Displays filter options (diseases, lab units, grades, AI models)
- Shows dataset statistics (include/exclude counts)
- Displays active export jobs

**POST Request:**
Creates a new curated dataset with optional auto-selection.

**Form Parameters:**
```python
# Required
disease_id: int              # Disease to filter by
dataset_name: str            # Dataset name
dataset_purpose: str         # Purpose description

# Optional - Auto-selection
auto_select_count: int       # Number of tasks to auto-select (default: 0)
randomize_selection: str     # "yes"/"on"/"true"/"1" to enable random selection
random_seed: str            # Optional seed for reproducible random selection

# Filters (discrepancy-style)
lab_unit_id: int
resident_grade: List[str]
resident2_grade: List[str]
arbitrator_grade: List[str]
final_grade: List[str]
has_ai_grade: str           # "yes" or other
ai_model_id: List[int]
ai_grade: List[str]
ai_review_status: List[str]
has_review: str
has_consensus: str
```

**Flow:**
1. Validates user has access to lab units via `apply_scoping()`
2. Builds filters from request using `_build_filters_from_request()`
3. Merges with user's allowed lab units via `_filters_with_allowed()`
4. Creates `CuratedDataset` record
5. If `auto_select_count > 0`: fetches matching rows and creates items
6. Commits and redirects to dataset detail page

---

#### 2. `/dataset-curation/<dataset_uuid>` (GET/POST)
**File:** `analytics/route_dataset_curation.py:280-422`

**Roles Required:** Same as above

**Purpose:** Manual screening interface for individual task review and selection.

**Access Control:**
```python
# User must have access to stored lab units
stored_allowed = set(stored_filters.get("allowed_lab_units") or [])
if stored_allowed and not stored_allowed.intersection(set(allowed_lab_units)):
    abort(403)
```

**GET Response:**
- Shows next pending task for review
- Displays included/excluded task lists
- Shows AI summary for each task
- Displays matching task statistics

**POST Request (Decision Recording):**
```python
task_id: int           # Task being decided
decision: str          # "include" or "exclude"
```

**Flow:**
1. Looks up existing `CuratedDatasetItem` or creates new one
2. Updates `include_in_export` flag
3. Sets `selection_method = "manual"`
4. Records `selected_by_user_id`
5. Redirects to refresh view

---

#### 3. `/dataset-export/<dataset_uuid>` (POST)
**File:** `analytics/route_dataset_curation.py:426-486`

**Roles Required:** `admin`, `local_admin`, `data_manager`, `data_exporter`, `dataset_creator`

**Purpose:** Queues an export job for the dataset.

**Access Control:**
- User must have `dataset_creator` role OR be master admin
- User must have access to dataset's lab units

**Flow:**
1. Validates dataset exists and user has access
2. Fetches all items with `include_in_export=True`
3. Creates `Job` record with `upload_type="dataset_export"`
4. Calls `enqueue_dataset_export()` with:
   - Job token
   - Dataset ID
   - Task IDs to export
   - Metadata (name, purpose, filters)
5. Redirects to job status page

---

#### 4. `/dataset-export/<job_token>/<filename>` (GET)
**File:** `analytics/route_dataset_curation.py:490-517`

**Roles Required:** Same as export route

**Purpose:** Serves completed export artifacts.

**Security Validations:**
1. Job must exist and be of type `dataset_export`
2. User must be job creator OR have access to job's lab unit
3. Filename must pass `secure_filename()` check
4. Path must not contain traversal patterns (`..`, `/`, `\`)
5. Resolved path must be within `EXPORT_DIR`

**Response:** `send_file(export_path, as_attachment=True)`

## Helper Functions

### `_build_filters_from_request(req)`
Extracts discrepancy-style filters from Flask request.

**Returns:** Dictionary with filter criteria
```python
{
    "disease_id": int,
    "lab_unit_id": int,
    "resident_grade": List[str],
    "resident2_grade": List[str],
    "arbitrator_grade": List[str],
    "final_grade": List[str],
    "has_ai_grade": str,
    "has_review": str,
    "has_consensus": str,
    "ai_model_id": List[int],
    "ai_grade": List[str],
    "ai_review_status": List[str],
    # Random selection (NEW)
    "randomize_selection": bool,    # True for random, False for sequential
    "random_seed": int|None,         # Optional seed for reproducibility
}
```

**Random Selection Processing:**
- `randomize_selection`: Parsed from form values "yes", "on", "true", "1" → `True`
- `random_seed`: Converted to integer; strings are hashed using SHA-256 for consistent seed values

### `_filters_with_allowed(filters, allowed_lab_units)`
Merges user's allowed lab units into filter dictionary.

**Purpose:** Enforces ABAC by scoping filters to user's permitted lab units.

### `_get_next_pending_row(filters, decided_task_ids)`
Returns the next task row not yet decided for the dataset.

**Algorithm:**
1. Fetches all rows matching filters
2. Iterates through rows
3. Returns first row with `task_id` not in `decided_task_ids`

### `_fetch_options(db, user)`
Fetches filter options for the dataset creation form.

**Returns:** `(diseases, lab_units, grade_options, ai_models)`

**Important:** Lab units are scoped via `apply_scoping(lab_units_query, LabUnit, user, 'dataset_creation')`

### `_ai_summary(row: ExportTaskRow)`
Constructs human-readable AI information string.

**Format:** `{grade} ; p={prob} ; {model} ; review: {statuses} ; comment: {comments}`

**Data Sources:**
- Parses `grading_details_json` for AI role slot
- Falls back to regex parsing of `ai_review_comments` for probability

## Integration Points

### Review Module (`review/discrepancy_export.py`)
```python
from review.discrepancy_export import (
    ExportTaskRow,
    enqueue_dataset_export,
    _fetch_filtered_rows,
    _fetch_rows_by_task_ids,
)
```

**Used Functions:**
- `_fetch_filtered_rows(filters)` → Returns matching `ExportTaskRow` objects
- `_fetch_rows_by_task_ids(task_ids, disease_id)` → Returns rows by task IDs
- `enqueue_dataset_export(app, job_token, dataset_id, task_ids, metadata)` → Queues export job

**Random Selection Implementation:**
The `_fetch_filtered_rows()` function now supports random ordering via:
- `filters["randomize_selection"] = True` → Uses `ORDER BY RANDOM()` in SQL
- `filters["random_seed"] = <int>` → Uses `setseed()` before `RANDOM()` for reproducible results

```sql
-- Sequential (default)
ORDER BY gt.id DESC

-- Random without seed
ORDER BY RANDOM()

-- Random with seed (deterministic)
ORDER BY setseed(:seed), RANDOM()
```

### Hospital Scoping (`utils/hospital_scoping.py`)
```python
from utils.hospital_scoping import apply_scoping
```

**Applied to:** Lab unit queries for dataset creation and access control.

### Job Store (`job_store.py`)
```python
from job_store import db_create_job
```

**Purpose:** Creates job records for tracking export operations.

## Security Considerations

### Access Control
1. **Role-Based:** All routes require specific roles
2. **Attribute-Based:** Lab unit scoping applied to all queries
3. **Ownership:** Export downloads restricted to creators or authorized users

### Input Validation
1. All form parameters use Flask's type coercion
2. AI review status filtered against `AI_REVIEW_STATUS_LABELS`
3. Filenames validated with `werkzeug.utils.secure_filename()`
4. Path traversal protection on file downloads

### Data Isolation
```python
# Lab units merged into filters to enforce ABAC
merged["allowed_lab_units"] = list(allowed_lab_units)
```

## Export Process Flow

```
[User Clicks Export]
       ↓
[Create Job Record] → db_create_job()
       ↓
[Enqueue Background Task] → enqueue_dataset_export()
       ↓
[Background Worker Processes]
       ↓
[Generate ZIP File] → stored in EXPORT_DIR/job_token/
       ↓
[User Downloads] → /dataset-export/<job_token>/<filename>
```

## Configuration

### Environment Variables
```bash
EXPORT_RETENTION_HOURS=24    # How long export files are kept
EXPORT_DIR=/app/exports      # Export file storage location
```

## Dependencies

### Internal
- `models.py`: CuratedDataset, CuratedDatasetItem, Disease, LabUnit, AIModel
- `review/discrepancy_export.py`: Export task fetching and enqueuing
- `utils/hospital_scoping.py`: Lab unit access control
- `job_store.py`: Job creation utilities

### External
- Flask: Web framework
- SQLAlchemy: ORM
- Flask-Login: User authentication
- Werkzeug: Security utilities (`secure_filename`)

## Error Handling

### Common Scenarios
1. **No lab units available** → Flash error, redirect to dashboard
2. **Missing disease_id** → Flash "Disease selection required"
3. **Dataset not found** → HTTP 404
4. **Access denied** → Flash "You do not have access", redirect
5. **No tasks to export** → Flash "No tasks selected for export"

### Transaction Safety
- All database operations within `Session()` context manager
- Automatic rollback on exception
- Explicit `commit()` only after validations pass

## Performance Considerations

### Query Optimization
1. Lab unit queries use `joinedload(LabUnit.hospital)` to prevent N+1
2. Dataset statistics use aggregate queries with grouping
3. Export job queries filter by creation date (retention window)

### Pagination
- Dataset listing limited to 20 most recent
- Export rows fetched per-page during screening

## Future Enhancements

### Potential Improvements
1. **Async Export Processing:** Use Celery for background job processing
2. **Incremental Selection:** Add "select all visible" option
3. **Export Formats:** Support CSV, JSON, DICOM formats
4. **Versioning:** Track dataset revisions and history
5. **Collaboration:** Multi-user dataset curation with locks
6. **Advanced Filters:** Date ranges, image quality metrics

---

## File Reference

**Main File:** `/analytics/route_dataset_curation.py` (518 lines)

**Routes:**
- `dataset_curation()` → `/dataset-curation`
- `dataset_detail()` → `/dataset-curation/<uuid>`
- `dataset_export()` → `/dataset-export/<uuid>`
- `dataset_export_download()` → `/dataset-export/<token>/<filename>`

**Templates:**
- `review/dataset_curation.html` → Dataset creation and listing
- `review/dataset_detail.html` → Manual screening interface

---

**Last Updated:** January 15, 2026
**Version:** 1.0
**Author:** Technical Documentation Team
