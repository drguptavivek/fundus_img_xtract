# Celery Background Task System Implementation Plan

## Overview

Implement a **general-purpose Celery-based background task queue system** to replace the current blocking PostgreSQL advisory lock queue. Phase 1 focuses on **PII detection + PDF OCR migration** with infrastructure designed for future task types (thumbnails, metadata backfill, etc.).

## Business Goals

1. **Decouple OCR/PII processing** from blocking metadata backfill (currently 15-30s per image)
2. **Enable independent scaling** - workers scale separately from web process
3. **Preserve audit trails** - maintain `PiiDetectionJob`, `ImagePiiVerification` models
4. **General-purpose foundation** - infrastructure ready for future task types

---

## System Constraints

**Hardware**: 4 cores, 8GB RAM

**Resource Allocation Strategy**:

| Service | CPU | Memory (reservation/limit) | Workers/Processes |
|---------|-----|---------------------------|-------------------|
| web (Gunicorn) | 1 core | 1g / 2g | **2 workers** (was 9!) |
| db (PostgreSQL) | 1 core | 512m / 1.5g | connection pool |
| cache (Redis) | <0.5 core | 256m / 512m | single-threaded |
| celery-ocr-worker | 1 core | 512m / 1g | 1 process (concurrency:1) |
| celery-general-worker | 0.5 core | 256m / 512m | 1 process (concurrency:2) |

**Total**: ~3.5 cores, ~3GB reservation, ~6.5GB limit (within 8GB)

---

## Library Dependencies (OCR Workload)

| Library | PII Detection | PDF OCR | Purpose |
|---------|---------------|---------|---------|
| `pytesseract` | ✅ | ✅ | OCR text extraction |
| `numpy` | ✅ | ✅ | Image array operations |
| `Pillow` | - | ✅ | Image manipulation |
| `opencv-python-headless` | ✅ | - | Image preprocessing (threshold, Canny, CLAHE) |
| `pymupdf` | - | ✅ | PDF splitting/rendering |

**All dependencies already in `pyproject.toml`** - only need to add `celery[redis]>=5.4.0`.

---

## Import Isolation Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  wsgi.py (Web Container)                                    │
│  ├── load_environment()                                     │
│  ├── create_app() from app.py                               │
│  │   ├── Flask()                                            │
│  │   ├── Register blueprints (auth, admin, api, etc.)       │
│  │   ├── SQLAlchemy init                                    │
│  │   └── EXECUTOR = ThreadPoolExecutor                      │
│  └── application.run()                                      │
│  Imports: models.py (all 70+ models)                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  celery_worker.py (Worker Containers)                       │
│  ├── load_environment()                                     │
│  ├── make_celery_app() from celery_app.py                   │
│  │   ├── Celery(broker=redis)                               │
│  │   ├── autodiscover_tasks(['tasks'])                      │
│  │   └── NO Flask, NO blueprints                            │
│  └── celery_app.start()                                     │
│  Imports: models_tasks.py (ONLY PII/OCR models)             │
│                                                             │
│  Task modules import:                                       │
│  ├── models_tasks.py (PiiDetectionJob, ImagePiiVerification)│
│  ├── utils/ocr_pii.py (CV2, pytesseract)                    │
│  ├── utils/pii_masking.py                                   │
│  ├── utils/log_sanitize.py                                  │
│  └── db_transaction_manager.py                              │
│                                                             │
│  Task modules NEVER import:                                 │
│  ✗ app.py                                                   │
│  ✗ from flask import current_app, request, flash            │
│  ✗ Blueprint modules                                        │
│  ✗ CSRF, session management                                 │
│  ✗ models.py (full 70+ models)                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Worker Architecture (2 Services)

```
┌─────────────────────────────────────────────────────────────────┐
│              celery-ocr-worker (single container)               │
│  ┌─────────────────────┐        ┌─────────────────────┐        │
│  │  pii_detection      │        │   pdf_processing    │        │
│  │      queue          │        │       queue         │        │
│  │  (concurrency: 1)   │        │   (concurrency: 1)  │        │
│  └─────────────────────┘        └─────────────────────┘        │
│                                                                 │
│  Shared: pytesseract, numpy, opencv, pymupdf, Pillow           │
│  1 process, sequential OCR (CPU-intensive)                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│            celery-general-worker (separate container)           │
│  ┌─────────────────────┐        ┌─────────────────────┐        │
│  │      default        │        │      metadata       │        │
│  │      queue          │        │       queue         │        │
│  │  (concurrency: 1)   │        │   (concurrency: 1)  │        │
│  └─────────────────────┘        └─────────────────────┘        │
│                                                                 │
│  Future: thumbnails, scheduled tasks, other async work         │
└─────────────────────────────────────────────────────────────────┘
```

**Why combine PII + PDF?**
- Same core dependencies (pytesseract, numpy)
- Both CPU-intensive OCR tasks
- Simpler infrastructure (2 workers vs 3)
- Separate queues provide isolation

---

## Implementation Plan

### Phase 1: Celery Infrastructure (Foundation)

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Modify | Add `celery[redis]>=5.4.0` |
| `celery_app.py` | Create | Celery factory with Redis broker, queue routing |
| `celery_worker.py` | Create | Worker entry point (NO Flask imports) |
| `models_tasks.py` | Create | Task-only models (not full models.py) |
| `tasks/__init__.py` | Create | Task package init |
| `tasks/base.py` | Create | Base task class with DB session, logging |
| `tasks/pii_detection.py` | Create | PII detection task |
| `tasks/pdf_processing.py` | Create | PDF OCR task |
| `utils/celery_helpers.py` | Create | Enqueue helpers, monitoring |
| `docker-compose.yml` | Modify | Add 2 worker services, adjust Gunicorn workers |
| `deploy.config.env` | Modify | Add Celery config, set GUNICORN_WORKERS=2 |
| `app_init/logging_config.py` | Modify | Add Celery loggers |

#### celery_worker.py (New Entry Point)

```python
"""Celery worker entry point - NO FLASK IMPORTS"""

import os
import logging
from celery import Celery

from utils.env_loader import load_environment

# Load environment (same as wsgi.py)
load_environment()

# Expand env vars (same as wsgi.py)
for key, value in list(os.environ.items()):
    if isinstance(value, str) and "${" in value:
        try:
            os.environ[key] = os.path.expandvars(value)
        except Exception as exc:
            logging.warning(f"Unable to expand {key}")

# Create Celery app (NOT Flask)
from celery_app import make_celery_app
celery_app = make_celery_app()

if __name__ == "__main__":
    celery_app.start()
```

#### models_tasks.py (Task-Only Models)

```python
"""Minimal models for Celery tasks - NOT full models.py"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from db_transaction_manager import Base

class PiiDetectionJob(Base):
    """PII detection jobs table"""
    __tablename__ = 'pii_detection_jobs'
    id = Column(Integer, primary_key=True)
    image_uuid = Column(String(36), nullable=False, index=True)
    image_variant = Column(String(20), nullable=False)
    image_path = Column(Text, nullable=False)
    status = Column(String(20), default='queued', index=True)  # queued, running, completed, failed
    source = Column(String(20), default='auto')  # auto, manual
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ImagePiiVerification(Base):
    """PII verification results"""
    __tablename__ = 'image_pii_verifications'
    id = Column(Integer, primary_key=True)
    image_uuid = Column(String(36), nullable=False, index=True)
    image_variant = Column(String(20), nullable=False)
    has_pii = Column(Boolean, nullable=False, default=False)
    verified_by = Column(String(100), nullable=True)  # user_id or 'system'
    verified_at = Column(DateTime, default=datetime.utcnow)
    detections = Column(Text, nullable=True)  # JSON string
```

#### Celery Configuration (celery_app.py)

```python
from celery import Celery
from utils.redis_client import build_redis_url

def make_celery_app():
    app = Celery('fundus_img_xtract')
    app.conf.update(
        broker_url=build_redis_url(),
        result_backend=build_redis_url(),
        task_routes={
            'tasks.pii_detection.*': {'queue': 'pii_detection'},
            'tasks.pdf_processing.*': {'queue': 'pdf_processing'},
        },
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_track_started=True,
        task_time_limit=3600,
        task_soft_time_limit=3300,
        task_retry_max=3,
        task_retry_backoff=True,
    )
    app.autodiscover_tasks(['tasks'])
    return app
```

---

### Phase 2: Task Implementations

#### Base Task (tasks/base.py)

```python
from functools import wraps
import time
import logging
from utils.log_sanitize import sanitize_log_value
from models_tasks import Session

logger = logging.getLogger(__name__)

def with_db_session(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        db = Session()
        try:
            result = func(db=db, *args, **kwargs)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return wrapper

class BaseTask:
    def __init__(self):
        self.logger = logger

    def _log_sanitized(self, level, msg, *args):
        sanitized_msg = sanitize_log_value(msg)
        sanitized_args = [sanitize_log_value(str(arg)) for arg in args]
        getattr(self.logger, level)(sanitized_msg, *sanitized_args)
```

#### PII Detection Task (tasks/pii_detection.py)

```python
from tasks.base import BaseTask, with_db_session
from models_tasks import PiiDetectionJob, ImagePiiVerification
from utils.pii_verification import run_pii_detection_for_path
from auth.utils import utcnow

class PiiDetectionTask(BaseTask):
    name = 'tasks.pii_detection.detect_image_pii'

    @with_db_session
    def run(self, db, job_id: int, image_uuid: str, image_variant: str, image_path: str, source: str = 'auto'):
        self._log_sanitized('info', 'Starting PII detection for job %s, image %s', job_id, image_uuid)

        # Update status to running
        job = db.query(PiiDetectionJob).filter_by(id=job_id).first()
        if not job:
            self._log_sanitized('error', 'Job %s not found', job_id)
            return {'status': 'error', 'message': 'Job not found'}

        job.status = 'running'
        job.started_at = utcnow()
        db.commit()

        try:
            # Run PII detection (existing function)
            result = run_pii_detection_for_path(db, image_uuid, image_variant, image_path)

            # Update job status
            job.status = 'completed'
            job.completed_at = utcnow()
            db.commit()

            self._log_sanitized('info', 'PII detection completed for job %s', job_id)
            return {'status': 'completed', 'result': result}

        except Exception as e:
            job.status = 'failed'
            job.error_message = str(e)[:500]  # Truncate error messages
            job.completed_at = utcnow()
            db.commit()
            self._log_sanitized('error', 'PII detection failed for job %s: %s', job_id, str(e))
            raise
```

---

### Phase 3: Enqueue Helpers (utils/celery_helpers.py)

```python
from celery_app import make_celery_app
from models_tasks import PiiDetectionJob, Session
from auth.utils import utcnow

celery_app = make_celery_app()

def enqueue_pii_detection(image_uuid, image_variant, image_path, source='auto'):
    """Enqueue PII detection job - returns immediately (non-blocking)"""
    db = Session()
    try:
        # Check existing manual verification
        existing = db.query(ImagePiiVerification).filter_by(
            image_uuid=image_uuid,
            image_variant=image_variant
        ).first()
        if existing:
            return None  # Skip if already verified

        # Check existing queued/running job
        existing_job = db.query(PiiDetectionJob).filter_by(
            image_uuid=image_uuid,
            image_variant=image_variant
        ).filter(
            PiiDetectionJob.status.in_(['queued', 'running'])
        ).first()
        if existing_job:
            return existing_job.id  # Return existing job

        # Create new job
        job = PiiDetectionJob(
            image_uuid=image_uuid,
            image_variant=image_variant,
            image_path=image_path,
            source=source,
            status='queued',
            created_at=utcnow()
        )
        db.add(job)
        db.flush()  # Get job_id

        # Enqueue Celery task
        celery_app.send_task(
            'tasks.pii_detection.detect_image_pii',
            args=[job.id, image_uuid, image_variant, image_path, source]
        )

        db.commit()
        return job.id

    finally:
        db.close()

# Monitoring functions
def get_queue_depth(queue_name: str) -> int:
    """Get pending task count for queue"""
    with celery_app.connection_or_acquire() as conn:
        return conn.default_channel.queue_declare(
            queue=queue_name, passive=True
        ).message_count

def get_active_tasks(queue_name: str) -> list:
    """Get currently running tasks"""
    inspect = celery_app.control.inspect()
    active = inspect.active()
    return active.get(queue_name, [])

def cancel_task(task_id: str) -> bool:
    """Cancel a pending task"""
    celery_app.control.revoke(task_id, terminate=True)
    return True
```

---

### Phase 4: Docker Configuration

#### docker-compose.yml

```yaml
services:
  web:
    # ... existing config ...
    environment:
      GUNICORN_WORKERS: 2  # OVERRIDE default (cpu_count*2+1=9)

  # ... existing db, cache ...

  # OCR Worker (PII + PDF) - combined since they share dependencies
  celery-ocr-worker:
    build: .
    image: fundus-img-xtract:web
    container_name: fundus-img-xtract-ocr-worker
    mem_reservation: 512m
    mem_limit: 1g
    cpus: '1.0'  # Pin to 1 CPU core
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    env_file:
      - deploy.config.env
      - deploy.secrets.env
    environment:
      CELERY_BROKER_URL: redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
      CELERY_RESULT_BACKEND: redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
    command: >
      uv run celery -A celery_worker worker
      --loglevel=info
      -Q pii_detection,pdf_processing
      -c 1
      -n ocr-worker@%h
      --max-tasks-per-child=50
      --prefetch-multiplier=1
      --logfile=/app/logs/celery_ocr_worker.log
    volumes:
      - ./files:/app/files
      - ./logs:/app/logs
      - web_venv:/app/.venv
    restart: on-failure:5
    healthcheck:
      test: ["CMD-SHELL", "celery -A celery_worker inspect ping || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3

  # General Worker (future tasks, catch-all)
  celery-general-worker:
    build: .
    image: fundus-img-xtract:web
    container_name: fundus-img-xtract-general-worker
    mem_reservation: 256m
    mem_limit: 512m
    cpus: '0.5'  # Pin to 0.5 CPU core
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_healthy
    env_file:
      - deploy.config.env
      - deploy.secrets.env
    environment:
      CELERY_BROKER_URL: redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
      CELERY_RESULT_BACKEND: redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
    command: >
      uv run celery -A celery_worker worker
      --loglevel=info
      -Q default,metadata
      -c 1
      --concurrency=2
      -n general-worker@%h
      --logfile=/app/logs/celery_general_worker.log
    volumes:
      - ./files:/app/files
      - ./logs:/app/logs
      - web_venv:/app/.venv
    restart: on-failure:5
```

#### docker-compose.override.yml (Development)

```yaml
services:
  celery-ocr-worker:
    volumes:
      - .:/app  # Hot-reload for code changes
      - ./files:/app/files
      - ./logs:/app/logs
      - web_venv:/app/.venv
    environment:
      CELERY_LOG_LEVEL: debug

  celery-general-worker:
    volumes:
      - .:/app
      - ./files:/app/files
      - ./logs:/app/logs
      - web_venv:/app/.venv
```

#### deploy.config.env

```bash
# ... existing config ...

# Gunicorn Workers (CRITICAL: Override default cpu_count*2+1)
GUNICORN_WORKERS=2

# Celery Configuration
CELERY_BROKER_URL=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}
CELERY_TASK_TRACK_STARTED=true
CELERY_TASK_TIME_LIMIT=3600
CELERY_TASK_SOFT_TIME_LIMIT=3300
```

---

### Phase 5: Replace Blocking Calls

**File: `utils/image_metadata_backfill.py` (Line ~535)**
```python
# BEFORE:
from utils.pii_detection_queue import enqueue_pii_detection_job, run_pii_detection_queue
enqueue_pii_detection_job(db, image_uuid=..., image_variant=..., image_path=...)
run_pii_detection_queue(max_jobs=1)  # BLOCKS!

# AFTER:
from utils.celery_helpers import enqueue_pii_detection
enqueue_pii_detection(image_uuid=..., image_variant=..., image_path=...)
# Returns immediately, processing in background
```

**Other callers to update:**
- `direct_uploads/save_image.py` - After edited image save
- `api/ocr.py` - OCR API endpoint
- `admin/image_metadata.py` - Manual PII queue runner
- `process_pdfs.py` - PDF OCR processing (convert to Celery task)

---

### Phase 6: Testing Strategy

#### Test Structure

```
tests/
├── celery/
│   ├── __init__.py
│   ├── conftest.py           # Celery-specific fixtures
│   ├── test_pii_detection.py
│   ├── test_pdf_processing.py
│   └── test_celery_helpers.py
```

#### tests/celery/conftest.py

```python
import pytest
import os
from celery.contrib.testing import worker
from celery_app import make_celery_app
from models_tasks import Session

@pytest.fixture
def celery_app():
    """Test Celery app with in-memory broker"""
    # Override broker for tests
    os.environ['CELERY_BROKER_URL'] = 'memory://'
    os.environ['CELERY_RESULT_BACKEND'] = 'cache+memory://'
    return make_celery_app()

@pytest.fixture
def celery_worker(celery_app):
    """Run Celery worker for integration tests"""
    with worker.start_worker(celery_app, concurrency=1) as w:
        yield w

@pytest.fixture
def test_db_session():
    """Use test-db for Celery tests"""
    from utils.env_loader import load_environment
    load_environment()
    # Override DB to test-db
    os.environ['DATABASE_URL'] = 'postgresql://test_user:test_password_change_in_production@test-db:5438/fundus_test'
    session = Session()
    yield session
    session.close()
    # Cleanup test data
    session.query(PiiDetectionJob).delete()
    session.query(ImagePiiVerification).delete()
    session.commit()
```

#### Unit Tests (Mock DB)

```python
# tests/celery/test_pii_detection.py
import pytest
from unittest.mock import Mock, patch
from tasks.pii_detection import PiiDetectionTask

def test_pii_detection_task_logic():
    """Test task logic without real DB"""
    task = PiiDetectionTask()

    # Mock DB session
    mock_db = Mock()
    mock_job = Mock()
    mock_job.status = 'queued'
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_job

    # Mock OCR function
    with patch('tasks.pii_detection.run_pii_detection_for_path') as mock_ocr:
        mock_ocr.return_value = {'is_pii': False, 'valid_detections': 0}

        result = task.run(
            db=mock_db,
            job_id=1,
            image_uuid='test-uuid',
            image_variant='orig',
            image_path='/tmp/test.jpg'
        )

        # Assertions
        mock_ocr.assert_called_once()
        assert mock_job.status == 'completed'
        mock_db.commit.assert_called_once()
```

#### Integration Tests (Real Celery + Test DB)

```python
# tests/celery/test_pii_detection_integration.py
import pytest
from celery_app import celery_app
from celery.result import AsyncResult
from utils.celery_helpers import enqueue_pii_detection
from models_tasks import PiiDetectionJob

def test_enqueue_and_process(celery_worker, test_db_session):
    """Full integration: enqueue -> worker processes -> DB updated"""

    # Enqueue task
    job_id = enqueue_pii_detection(
        image_uuid='test-uuid',
        image_variant='orig',
        image_path='/tmp/test.jpg'
    )

    assert job_id is not None

    # Wait for task to complete
    result = AsyncResult(job_id, app=celery_app)
    result.get(timeout=10)

    # Verify DB state
    job = test_db_session.query(PiiDetectionJob).filter_by(id=job_id).first()
    assert job.status in ('completed', 'failed')
```

#### Running Tests

```bash
# Unit tests only (fast, no worker)
DC exec -u $(id -u):$(id -g) web uv run pytest tests/celery/ -v -m "not integration"

# Integration tests (starts worker, uses test-db)
DC up -d test-db
DC exec -u $(id -u):$(id -g) web uv run pytest tests/celery/ -v
```

---

## Critical Files Summary

### Must Create (New Files)

| File | Priority | Purpose |
|------|----------|---------|
| `celery_app.py` | P0 | Celery factory, core configuration |
| `celery_worker.py` | P0 | Worker entry point (NO Flask) |
| `models_tasks.py` | P0 | Task-only models |
| `tasks/__init__.py` | P0 | Task package |
| `tasks/base.py` | P0 | Base task class |
| `tasks/pii_detection.py` | P1 | PII detection task |
| `tasks/pdf_processing.py` | P1 | PDF OCR task |
| `utils/celery_helpers.py` | P1 | Enqueue helpers, monitoring |
| `tests/celery/conftest.py` | P1 | Celery test fixtures |
| `tests/celery/test_pii_detection.py` | P1 | Unit + integration tests |

### Must Modify

| File | Changes |
|------|---------|
| `pyproject.toml` | Add `celery[redis]>=5.4.0` |
| `docker-compose.yml` | Add 2 worker services, CPU limits |
| `deploy.config.env` | Add Celery vars, `GUNICORN_WORKERS=2` |
| `app_init/logging_config.py` | Add Celery loggers |
| `utils/image_metadata_backfill.py` | Replace blocking call |
| `direct_uploads/save_image.py` | Update enqueue call |
| `api/ocr.py` | Update enqueue call |

---

## Verification Checklist

- [ ] Workers start successfully: `docker compose up -d celery-ocr-worker celery-general-worker`
- [ ] Workers connect to Redis (check logs)
- [ ] `enqueue_pii_detection()` creates `PiiDetectionJob` with status='queued'
- [ ] Celery task processes job, status transitions to 'completed' or 'failed'
- [ ] `ImagePiiVerification` records created successfully
- [ ] Metadata backfill no longer blocks (completes without waiting for OCR)
- [ ] Logs sanitized with `sanitize_log_value()` throughout
- [ ] Unit tests pass: `uv run pytest tests/celery/ -v -m "not integration"`
- [ ] Integration tests pass: `uv run pytest tests/celery/ -v`
- [ ] CPU usage within limits (top/htop shows ~3.5 cores used)
- [ ] Memory within limits (docker stats shows ~6GB max)

---

## Commands Reference

```bash
# Start workers
DC="docker compose --env-file deploy.config.env --env-file deploy.secrets.env"
$DC up -d celery-ocr-worker celery-general-worker

# View worker logs
$DC logs -f celery-ocr-worker

# Check worker status
$DC exec celery-ocr-worker uv run celery -A celery_worker inspect active

# Check resource usage
docker stats

# Restart workers
$DC restart celery-ocr-worker celery-general-worker

# Run tests
$DC exec -u $(id -u):$(id -g) web uv run pytest tests/celery/ -v
```

---

## Future Expansion (Not in Phase 1)

The infrastructure is designed for easy addition of new task types:

1. **Thumbnail Generation**: Create `tasks/thumbnail_generation.py`, add `thumbnails` queue
2. **Metadata Extraction**: Create `tasks/metadata_backfill.py`, use `metadata` queue
3. **Scheduled Tasks**: Replace APScheduler with Celery Beat (maintenance worker)

Each new task type requires:
- New task module inheriting from `BaseTask`
- Enqueue helper in `celery_helpers.py`
- Optional queue/worker in `docker-compose.yml`
- Add relevant models to `models_tasks.py` (NOT full models.py)
