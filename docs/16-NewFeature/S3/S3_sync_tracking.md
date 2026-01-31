# S3 Sync Status Tracking

## Overview

The S3 sync tracking system provides visibility into file synchronization between local storage and S3. It tracks upload status, supports retry logic, and enables monitoring through a dashboard.

## Data Model

### S3SyncStatus

```python
class S3SyncStatus(Base):
    """
    Tracks synchronization status of files to S3 storage.
    """
    __tablename__ = 's3_sync_status'

    # Polymorphic file reference
    file_type: str      # 'encounter_file', 'encounter_file_pdf', 'direct_upload', 'encounter_set_image'
    file_id: int        # ID of the file record

    # S3 configuration
    s3_config_id: int   # FK → s3_configs.id

    # Sync state
    status: str         # 'pending', 'in_progress', 'success', 'failed'
    variant: str        # 'original', 'thumbnail', 'edited', 'edited_thumbnail'

    # Retry tracking
    attempt_count: int
    last_attempt_at: datetime
    last_error: str

    # Completion
    synced_at: datetime

    # Audit
    created_at: datetime
    updated_at: datetime
```

### Status States

```
┌──────────┐
│ PENDING  │ ◀─── Created when file is added
└────┬─────┘
     │
     ▼
┌──────────────┐
│ IN_PROGRESS  │ ◀─── Upload started (attempt_count++)
└──────┬───────┘
       │
       ├─────────────────┐
       ▼                 ▼
┌──────────┐      ┌──────────┐
│ SUCCESS  │      │  FAILED  │
└──────────┘      └────┬─────┘
                       │
                       ▼ (retry)
                 ┌──────────────┐
                 │ IN_PROGRESS  │
                 └──────────────┘
```

## File Type Mapping

| `file_type` | Model | Table |
|-------------|-------|-------|
| `encounter_file` | `EncounterFile` | encounter_files |
| `encounter_file_pdf` | `EncounterFilePDF` | encounter_file_pdfs |
| `direct_upload` | `DirectImageUpload` | direct_image_uploads |
| `encounter_set_image` | `EncounterSetImage` | encounter_set_images |

## Variants

| Variant | Description | Example Use |
|---------|-------------|-------------|
| `original` | Original uploaded file | All file types |
| `thumbnail` | Thumbnail for UI | All file types |
| `edited` | PII-masked version | EncounterFile, EncounterSetImage |
| `edited_thumbnail` | Thumbnail of edited version | EncounterFile, EncounterSetImage |

## API Usage

### Creating Sync Status

```python
from utils.s3_sync_status import create_sync_status

sync = create_sync_status(
    file_type="encounter_file",
    file_id=123,
    s3_config_id=5,
    variant="original",
    status="pending"
)
# Returns: S3SyncStatus instance
```

### Updating Sync Status

```python
from utils.s3_sync_status import (
    mark_sync_in_progress,
    mark_sync_success,
    mark_sync_failed
)

# Start upload
mark_sync_in_progress(sync.id)

# Upload succeeded
mark_sync_success(sync.id)

# Upload failed
mark_sync_failed(sync.id, "Connection timeout")
```

### Querying Sync Status

```python
from utils.s3_sync_status import get_sync_status, get_failed_syncs

# Get all sync records for a file
statuses = get_sync_status("encounter_file", 123)

# Get failed syncs for an S3 config
failed = get_failed_syncs(s3_config_id=5, limit=100)
```

### Hospital-Level Counts

```python
from utils.s3_sync_status import get_sync_counts_by_hospital

counts = get_sync_counts_by_hospital(hospital_id=5)
# Returns: {pending: 12, in_progress: 3, success: 1450, failed: 2, has_s3: True}
```

## Sync Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. File Created (Upload or Processing)                         │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ encounter_file = EncounterFile(...)                  │     │
│     │ db.add(encounter_file)                               │     │
│     │ db.flush()  # Get file.id                            │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. Create Sync Status Record                                  │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ sync = S3SyncStatus(                                │     │
│     │   file_type='encounter_file',                       │     │
│     │   file_id=encounter_file.id,                        │     │
│     │   s3_config_id=s3_config.id if s3 else None,        │     │
│     │   variant='original',                               │     │
│     │   status='pending',                                 │     │
│     │   attempt_count=0                                   │     │
│     │ )                                                   │     │
│     │ db.add(sync)                                        │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. Celery Background Job Picks Up Task                        │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ @celery.task                                        │     │
│     │ def sync_file_to_s3(sync_id):                      │     │
│     │     sync = S3SyncStatus.get(sync_id)               │     │
│     │     mark_sync_in_progress(sync_id)                  │     │
│     │                                                      │     │
│     │     try:                                            │     │
│     │         # Upload to S3                              │     │
│     │         s3_client.put_object(...)                   │     │
│     │         mark_sync_success(sync_id)                  │     │
│     │     except Exception as e:                          │     │
│     │         mark_sync_failed(sync_id, str(e))           │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. Retry Logic (for Failed Syncs)                            │
│     ┌─────────────────────────────────────────────────────┐     │
│     │ if sync.status == 'failed' and sync.attempt_count < 3:│   │
│     │     # Re-queue for retry                            │     │
│     │     sync_to_s3.delay(sync_id, countdown=60)         │     │
│     └─────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

## Dashboard Integration

### Hospital Sync Status Widget

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 S3 Sync Status - City Eye Hospital                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────┬─────────┬─────────┬─────────┬─────────┐          │
│  │ ⏳ PEND │ 🔄 IN   │ ✅ SUCC │ ❌ FAIL │  TOTAL  │          │
│  │   12    │    3    │  1450   │    2    │  1467   │          │
│  └─────────┴─────────┴─────────┴─────────┴─────────┘          │
│                                                                 │
│  [View Details] [Retry Failed] [Export Report]                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Failed Syncs Detail Table

```
┌─────────────────────────────────────────────────────────────────┐
│  ❌ Failed Syncs (2)                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌────────────┬──────────┬───────────────┬──────────┬────────┐ │
│  │ File Type  │ Variant  │ File          │ Attempts │ Error  │ │
│  │────────────│──────────│───────────────│──────────│────────│ │
│  │ direct_upld│ thumbnail│ abc-123...jpg │    3     │ CN...  │ │
│  │ encounter  │ edited   │ def-456...jpg │    2     │ TL...  │ │
│  └────────────┴──────────┴───────────────┴──────────┴────────┘ │
│                                                                 │
│  [Retry Selected] [Retry All]                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Recent Activity Timeline

```
┌─────────────────────────────────────────────────────────────────┐
│  📋 Recent Sync Activity (last 50)                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✅ encounter_file • original • 18:45:23                       │
│  ✅ encounter_file • thumbnail • 18:45:22                      │
│  ✅ direct_upload • original • 18:45:20                        │
│  ⚠️ encounter_set_image • edited • 18:44:15                    │
│  ✅ encounter_file_pdf • original • 18:44:10                   │
│  ...                                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Retry API

### Manual Retry (Single)

**Route:** `POST /admin/api/s3-sync-retry/<sync_id>`

**Response:**
```json
{
  "success": true,
  "message": "Sync retry queued"
}
```

**Action:** Re-queues the Celery task for this sync

### Batch Retry (All Failed)

**Route:** `POST /admin/api/s3-sync-retry-all/<s3_config_id>`

**Response:**
```json
{
  "success": true,
  "queued_count": 5
}
```

## Retry Strategy

### Exponential Backoff

```
Attempt 1: Immediate (0s delay)
Attempt 2: 60 seconds
Attempt 3: 300 seconds (5 minutes)
Attempt 4+: Skipped (max 3 attempts)
```

### Max Attempts

Default maximum: **3 attempts**

After 3 failed attempts:
- Status remains `failed`
- Manual retry required via dashboard
- Error persists for investigation

## Monitoring Queries

### Get Stalled Syncs

```sql
-- Syncs stuck in in_progress > 1 hour
SELECT *
FROM s3_sync_status
WHERE status = 'in_progress'
  AND last_attempt_at < NOW() - INTERVAL '1 hour'
ORDER BY last_attempt_at ASC;
```

### Get High-Failure Files

```sql
-- Files with multiple failed variants
SELECT file_type, file_id, COUNT(*) as failed_count
FROM s3_sync_status
WHERE status = 'failed'
GROUP BY file_type, file_id
HAVING COUNT(*) >= 2;
```

### Get Sync Statistics by Day

```sql
SELECT
    DATE(synced_at) as date,
    COUNT(*) as sync_count
FROM s3_sync_status
WHERE status = 'success'
  AND synced_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(synced_at)
ORDER BY date DESC;
```

## Celery Integration

### Task Definition

```python
# celery_tasks/tasks/s3_sync_tasks.py
from celery import shared_task
from utils.s3_sync_status import (
    mark_sync_in_progress,
    mark_sync_success,
    mark_sync_failed,
    get_file_by_sync
)

@shared_task(bind=True, max_retries=3)
def sync_file_to_s3(self, sync_id):
    """
    Sync a single file to S3.
    """
    from db_transaction_manager import transaction_scope

    with transaction_scope() as db:
        sync_status = db.query(S3SyncStatus).get(sync_id)
        if not sync_status:
            return

        mark_sync_in_progress(sync_id)

        try:
            file_record = get_file_by_sync(sync_status, db)
            if not file_record:
                mark_sync_failed(sync_id, "File record not found")
                return

            # Upload based on file type and variant
            upload_result = upload_file_variant(
                file_record,
                sync_status.variant,
                sync_status.s3_config_id
            )

            if upload_result.success:
                mark_sync_success(sync_id)
            else:
                mark_sync_failed(sync_id, upload_result.error)

        except Exception as e:
            mark_sync_failed(sync_id, str(e))
            raise self.retry(exc=e, countdown=60)
```

## Related Documentation

- [S3 Storage System](../../00-Core/S3_storage_system.md) - Architecture overview
- [S3 Administration](../../10-ADMIN/S3_administration.md) - Dashboard and management
- [Security](../../09-Security/S3_security.md) - Access control
