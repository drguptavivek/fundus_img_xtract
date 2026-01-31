# Docker Package Updates & Dependency Management

## Key Steps: Package Update Workflow (TL;DR)

Update packages in **5 simple steps**:

```bash
# 1️⃣  Edit the source of truth (NOT requirements-*.txt files)
nano pyproject.toml
# Change versions: gunicorn==23.0.0 → gunicorn==24.1.1

# 2️⃣  Regenerate lock file (DO NOT manually delete uv.lock)
uv sync
# ✓ uv reads pyproject.toml
# ✓ uv updates uv.lock automatically
# ✓ No manual deletion needed

# 3️⃣  Auto-generate per-container requirements (using dependency groups)
# Using the helper script:
./scripts/export_requirements.sh

# Or manually:
docker compose exec web bash -c "
  uv export --extra web --format requirements-txt --no-hashes > /tmp/requirements-web.txt &&
  uv export --extra ocr --format requirements-txt --no-hashes > /tmp/requirements-ocr.txt &&
  uv export --extra beat --format requirements-txt --no-hashes > /tmp/requirements-beat.txt &&
  uv export --extra general --format requirements-txt --no-hashes > /tmp/requirements-general.txt &&
  uv export --format requirements-txt --no-hashes > /tmp/requirements.txt
"

# Copy files from container to host
docker compose exec web cat /tmp/requirements-web.txt > requirements-web.txt
docker compose exec web cat /tmp/requirements-ocr.txt > requirements-ocr.txt
docker compose exec web cat /tmp/requirements-beat.txt > requirements-beat.txt
docker compose exec web cat /tmp/requirements-general.txt > requirements-general.txt
docker compose exec web cat /tmp/requirements.txt > requirements.txt

# 4️⃣  Commit changes
git add pyproject.toml uv.lock requirements*.txt
git commit -m "chore: update packages"

# 5️⃣  Rebuild containers and test
docker compose build --no-cache *-venv-builder
docker compose up -d
docker compose exec web uv run pytest tests/ -v
docker compose logs web | head -20

# 6️⃣  Push to remote
git push
```

### ❓ FAQ: Do I need to delete uv.lock?

**NO. Never manually delete uv.lock.**

- `uv sync` automatically updates it
- It's a **lock file** (like `package-lock.json` in Node.js or `Gemfile.lock` in Ruby)
- Always let `uv` manage it, not humans

---

## Overview

This system uses a **multi-venv architecture** with isolated dependency sets for different container roles. Package management uses:
- **Source of Truth**: `pyproject.toml` (main dependency definitions)
- **Lock File**: `uv.lock` (all resolved transitive dependencies with exact versions)
- **Per-Container**: `requirements-*.txt` files (derived dependency subsets)

## Architecture: Multi-Venv Setup

Each Docker container has its own virtual environment (venv) with a specific dependency set:

```
┌──────────────────────────────────────────────────────────────┐
│  Docker Compose Services                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐      │
│  │ web-venv    │  │ ocr-venv     │  │ beat-venv       │      │
│  │             │  │              │  │                 │      │
│  │ Web server  │  │ OCR worker   │  │ Celery Beat     │      │
│  │ (gunicorn)  │  │ (tesseract)  │  │ Scheduler       │      │
│  └─────────────┘  └──────────────┘  └─────────────────┘      │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐                           │
│  │ general-venv│  │ default-venv │                           │
│  │             │  │ (for venv-   │                           │
│  │ General     │  │  builder)    │                           │
│  │ worker      │  │              │                           │
│  │ (Celery)    │  │              │                           │
│  └─────────────┘  └──────────────┘                           │
│                                                              │
│  Dependency Specifications:                                  │
│  └─ requirements-web.txt         (web container)             │
│  └─ requirements-ocr.txt         (ocr-worker container)      │
│  └─ requirements-beat.txt        (celery-beat container)     │
│  └─ requirements-general.txt     (celery-general container)  │
│  └─ requirements.txt             (fallback/general venv)     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Dependency Hierarchy

```
pyproject.toml (Main Source)
        ↓
    uv sync
        ↓
   uv.lock (Frozen versions)
        ↓
   ┌────┴────┬────────┬──────────┬──────────┐
   ↓         ↓        ↓          ↓          ↓
requirements.txt
(all deps)        requirements-web.txt   requirements-ocr.txt
                  (web subset)           (OCR subset)
                      ↓
                  web-venv             ocr-venv
                  (gunicorn)           (tesseract)
```

## File Reference: What Each Dependency File Contains

### `pyproject.toml` (Source of Truth)
- **Location**: Root directory
- **Purpose**: Main dependency declarations with version constraints
- **Managed by**: `uv` (Python dependency manager)
- **Contains**:
  - Flask framework (3.1.2)
  - Database: SQLAlchemy (2.0.46), psycopg2-binary (2.9.11)
  - Caching: Redis (5.0.4+), flask-caching (2.3.1+)
  - Image processing: Pillow (12.1.0), OpenCV, Tesseract
  - Data analysis: pandas (3.0.0), numpy (2.4.1), matplotlib (3.10.8)
  - PDF processing: PyMuPDF (1.26.7)
  - Celery (5.6.2) for async tasks
  - Testing: pytest (9.0.2), playwright
  - Security: argon2-cffi, cryptography, PyNaCl
  - Admin tools: pip-audit, pip-api

**UPDATE PROCESS**:
```bash
# Edit version numbers in pyproject.toml
nano pyproject.toml

# Regenerate lock file with new resolved dependencies
uv sync

# This updates uv.lock with all transitive dependencies
```

### `uv.lock` (Frozen Lock File)
- **Location**: Root directory
- **Purpose**: Immutable record of all resolved dependencies (including transitive)
- **Format**: TOML with `[[package]]` sections
- **Auto-generated**: by `uv sync` command
- **Contains**: Every package and sub-dependency at exact pinned versions
- **Size**: ~400+ packages with full dependency tree

**DO NOT EDIT MANUALLY**. Always regenerate via `uv sync`.

### `requirements.txt` (All Dependencies)
- **Location**: Root directory
- **Purpose**: Fallback requirement file, contains ALL dependencies from pyproject.toml
- **Usage**: Default venv when container doesn't have specialized requirements file
- **Auto-generated**: Extract from pyproject.toml (see export instructions below)
- **Contains**: 63+ packages (all Flask, data science, OCR, Celery, testing libraries)

### `requirements-web.txt` (Web Server Subset)
- **Location**: Root directory
- **Purpose**: Web-specific dependencies for Flask/Gunicorn server
- **Usage**: Installed in `web-venv-builder`, mounted to `web` container
- **Size**: ~40 packages
- **Includes**:
  - Flask framework & plugins
  - Database connections (SQLAlchemy, psycopg2)
  - Caching (Flask-Caching, Redis client)
  - Image processing (Pillow, OpenCV)
  - Data analysis (pandas, numpy, matplotlib)
  - Excel support (openpyxl)
  - Testing (pytest)
  - Admin tools (pip-api, pip-audit)

### `requirements-ocr.txt` (OCR Worker Subset)
- **Location**: Root directory
- **Purpose**: Minimal dependencies for OCR worker container
- **Usage**: Installed in `ocr-venv-builder`, mounted to `celery-ocr-worker`
- **Size**: ~13 packages
- **Includes**:
  - Celery + Redis
  - Database: SQLAlchemy, psycopg2
  - Image processing: Pillow, OpenCV (headless)
  - PyMuPDF (PDF text extraction)
  - Tesseract OCR

### `requirements-beat.txt` (Celery Beat Scheduler Subset)
- **Location**: Root directory
- **Purpose**: Minimal dependencies for scheduled task scheduler
- **Usage**: Installed in `beat-venv-builder`, mounted to `celery-beat`
- **Size**: ~8 packages
- **Includes**:
  - Celery + Redis
  - Database: SQLAlchemy, psycopg2
  - Configuration: python-dotenv, pyyaml
  - Timezone: pytz

### `requirements-general.txt` (General Worker Subset)
- **Location**: Root directory
- **Purpose**: Dependencies for general background worker (exports, thumbnails, S3 sync)
- **Usage**: Installed in `general-venv-builder`, mounted to `celery-general-worker`
- **Size**: ~15 packages
- **Includes**:
  - Celery + Redis
  - Database: SQLAlchemy, psycopg2, Flask-Caching
  - Image processing: Pillow, numpy, pandas, OpenPyXL
  - Security: cryptography, PyNaCl (S3 signing)

## Understanding uv.lock (The Lock File)

### What is uv.lock?

`uv.lock` is a **frozen record of all resolved dependencies** — exactly like:
- `package-lock.json` (Node.js)
- `Gemfile.lock` (Ruby)
- `poetry.lock` (Python Poetry)

It contains ~400+ packages with exact pinned versions, including all transitive dependencies.

**Example**:
```
[[package]]
name = "flask"
version = "3.1.2"

[[package]]
name = "werkzeug"
version = "3.1.5"  # Required by flask, automatically resolved

[[package]]
name = "click"
version = "8.3.1"  # Required by flask, automatically resolved
```

### Why It Exists

- **Reproducibility**: Same `uv.lock` + `pyproject.toml` = exact same environment every time
- **Transitive deps**: Automatically includes all sub-dependencies (you don't edit these manually)
- **Conflict resolution**: `uv` solves version conflicts automatically
- **Docker consistency**: All containers get identical dependency versions

### Should You Delete It?

**NO. Never delete uv.lock manually.**

| Action | Result |
|--------|--------|
| ✅ `uv sync` | Automatically updates uv.lock with new resolved versions |
| ✅ `git pull` | Gets latest uv.lock from remote |
| ❌ `rm uv.lock` | Wastes time, next `uv sync` regenerates it anyway |
| ❌ Manual edits | Breaks reproducibility, causes version conflicts |

### When uv.lock Updates

**Automatically** (no manual action needed):

```bash
# Edit pyproject.toml
nano pyproject.toml
# Change: gunicorn==23.0.0 → gunicorn==24.1.1

# Run uv sync
uv sync
# ✓ Reads updated pyproject.toml
# ✓ Queries PyPI for new versions and their transitive deps
# ✓ Resolves all conflicts
# ✓ Writes updated uv.lock with ~400+ exact versions
```

That's it. No manual deletion needed.

### Conflict During Update?

If `uv sync` fails with dependency conflicts:

```bash
# ❌ DON'T do this:
rm uv.lock
uv sync

# ✅ DO THIS: Let uv show the conflict
uv sync  # Shows what packages conflict
# Then edit pyproject.toml to fix the constraint:
#   Example: change flask-limiter==4.0.0 to flask-limiter==4.1.1
nano pyproject.toml
uv sync  # Try again
```

---

## Upgrade Workflow

### Step 1: Identify What Needs Updating

Use the built-in package update scanner:

```bash
# From host, check available package updates
docker compose exec web uv run python -c "
from utils.package_update_scanner import scan_package_updates
result = scan_package_updates()
print(f'Packages with updates: {result[\"updates_available_count\"]}')
for pkg in result['packages'][:10]:
    if pkg['has_update']:
        print(f\"  {pkg['name']}: {pkg['current_version']} → {pkg['latest_version']}\")
"
```

Or check the admin dashboard for a badge showing available updates.

### Step 2: Update Dependencies in pyproject.toml

**Option A: Manual Update (Recommended for controlled rollouts)**

```bash
# Edit the version numbers directly
nano pyproject.toml

# Example changes:
# - gunicorn==23.0.0  →  gunicorn==24.1.1
# - flask-cors==6.0.1  →  flask-cors==6.0.2
# - numpy==2.3.2  →  numpy==2.4.1
```

**Option B: Automated Update (For testing/dev)**

```bash
# Use pip-audit to check for security updates only
docker compose exec web uv run pip-audit --desc

# Then selectively update in pyproject.toml
```

### Step 3: Regenerate Lock File

```bash
# Run uv sync to resolve all transitive dependencies
uv sync

# This updates uv.lock with exact resolved versions for all ~400+ packages
# ✅ Check the diff:
git diff uv.lock | head -50
```

### Step 4: Auto-Generate Per-Container Requirement Files

**Your Setup**: Using **dependency groups with auto-generated requirements files**.

```
requirements.txt (75 lines - core deps with transitive)
├─ requirements-web.txt (418 lines - core + web + all transitive)
│  └─ Flask, web server, data analysis, testing, admin tools
├─ requirements-ocr.txt (97 lines - core + ocr + all transitive)
│  └─ Celery, OCR libs, image processing
├─ requirements-beat.txt (79 lines - core + beat + all transitive)
│  └─ Celery scheduler, timezone, config
└─ requirements-general.txt (110 lines - core + general + all transitive)
   └─ Celery worker, image processing, S3, data export
```

Each file is **auto-generated from dependency groups** and includes all transitive dependencies for exact reproducibility.

#### Auto-Generate Using Helper Script (Recommended)

```bash
# One command to regenerate all requirement files
./scripts/export_requirements.sh

# Output:
# ✅ Successfully exported requirements files:
#   Core only:     75 packages
#   Web:          418 packages
#   OCR:           97 packages
#   Beat:          79 packages
#   General:      110 packages
```

#### Manual Export (If Needed)

```bash
docker compose exec web bash -c "
  uv export --extra web --format requirements-txt --no-hashes > /tmp/requirements-web.txt &&
  uv export --extra ocr --format requirements-txt --no-hashes > /tmp/requirements-ocr.txt &&
  uv export --extra beat --format requirements-txt --no-hashes > /tmp/requirements-beat.txt &&
  uv export --extra general --format requirements-txt --no-hashes > /tmp/requirements-general.txt &&
  uv export --format requirements-txt --no-hashes > /tmp/requirements.txt
"

# Copy from container to host
docker compose exec web cat /tmp/requirements-web.txt > requirements-web.txt
docker compose exec web cat /tmp/requirements-ocr.txt > requirements-ocr.txt
docker compose exec web cat /tmp/requirements-beat.txt > requirements-beat.txt
docker compose exec web cat /tmp/requirements-general.txt > requirements-general.txt
docker compose exec web cat /tmp/requirements.txt > requirements.txt
```

**Benefits**:
- Automatic generation (no manual editing)
- Exact version pinning (reproducible builds)
- Container sizes are identical to hand-curated approach
- Consistent with uv's design philosophy

---

### Why This Is Manual

```dockerfile
# What Docker does during build:
FROM web-base AS web-venv-builder
COPY requirements-web.txt ./              # ← Reads FILE from repo
CMD ["sh", "-c", "uv pip install -r requirements-web.txt"]  # ← Installs from file

# Docker CANNOT:
# - Run 'uv export' during build
# - Access pyproject.toml directly
# - Generate files automatically
```

### Step 5: Test Each Container's Venv

```bash
DC="docker compose"

# Rebuild all venv builders (they will install the new requirements)
$DC build --no-cache web-venv-builder ocr-venv-builder beat-venv-builder general-venv-builder

# Test web server startup
$DC up web -d
sleep 10
$DC logs web | grep -i "error\|warning\|404" || echo "✅ Web started OK"

# Test OCR worker
$DC up celery-ocr-worker -d
sleep 5
$DC logs celery-ocr-worker | head -20

# Test Beat scheduler
$DC up celery-beat -d
sleep 5
$DC logs celery-beat | head -20

# Test general worker
$DC up celery-general-worker -d
sleep 5
$DC logs celery-general-worker | head -20
```

### Step 6: Run Integration Tests

```bash
# Create test database (if not already running)
docker compose up test-db -d

# Run pytest suite
docker compose exec -u $(id -u):$(id -g) web uv run pytest tests/ -v

# Check for any dependency-related test failures
docker compose logs test-db
```

### Step 7: Commit Changes

```bash
# Stage updated dependency files
git add pyproject.toml uv.lock requirements*.txt

# Verify changes before committing
git diff --cached | head -100

# Commit with clear message
git commit -m "chore: update package dependencies

- Updated gunicorn 23.0.0 → 24.1.1
- Updated numpy 2.3.2 → 2.4.1
- Updated pandas 2.3.2 → 3.0.0
- Updated 15+ other packages

Regenerated uv.lock and all requirements-*.txt files.
All containers tested and passing."

# Push to remote
git push
```

## Dependency Groups (Future Enhancement)

To separate dependencies properly in `pyproject.toml`, add optional groups:

```toml
[project.optional-dependencies]
# Web server specific
web = [
    "gunicorn>=24.0",
    "matplotlib>=3.10",
    "openpyxl>=3.1",
]

# OCR worker specific
ocr = [
    "opencv-python-headless>=4.13",
    "pytesseract>=0.3",
    "pymupdf>=1.26",
]

# Celery beat scheduler
beat = [
    "pytz>=2025.2",
    "pyyaml>=6.0",
]

# General worker
general = [
    "pillow>=12.0",
    "numpy>=2.4",
    "pandas>=3.0",
    "cryptography>=46.0",
    "pynacl>=1.6",
]
```

Then export becomes cleaner:
```bash
uv export --only-group ocr > requirements-ocr.txt
uv export --only-group web > requirements-web.txt
```

## Security Scanning

### Automated Security Checks

```bash
# Scan for known security vulnerabilities in dependencies
docker compose exec web uv run pip-audit --fix

# Check for outdated security-critical packages
docker compose exec web uv run pip-audit --desc | grep -i "security\|critical"
```

### Update Security-Critical Packages First

Priority order for updates:
1. **CRITICAL** (vulnerability patches): cryptography, PyNaCl, werkzeug, Flask, urllib3
2. **HIGH** (security): certifi, requests, PyYAML, SQLAlchemy
3. **MEDIUM**: Database drivers, image libraries
4. **LOW**: Testing, development, analytics

### Automated Package Update Scanner

The system includes `utils/package_update_scanner.py` which:
- Checks PyPI for available updates daily (via Celery Beat)
- Stores scan results in database
- Shows badge in admin dashboard
- Caches PyPI responses for 1 hour to avoid rate limits

Triggered by:
- Scheduled task (daily via Celery Beat)
- Admin dashboard "Scan Now" button (manual)

Results include:
- Package name and current version
- Latest available version on PyPI
- Whether latest is a prerelease
- Publication date
- PyPI project URL

## Docker Build Process: How Packages Get Installed

### Why `uv export` Must Be Done Manually (Not Automatic in Docker)

```
YOU (Host Machine)              Docker Build                Container Runtime
═══════════════════════════════════════════════════════════════════════════

1. Edit pyproject.toml
2. Run: uv sync
   ↓ (updates uv.lock)

3. Run: uv export
   ↓ (generates requirements-*.txt) ← MANUAL, must be done on host

4. git add & commit all files
   ↓ (files now in repo)

5. git push
      ↓
      Docker pulls repo
      ↓
      docker compose build web-venv-builder
      ↓
      Dockerfile: COPY requirements-web.txt ./  ← Reads FILE from repo
      ↓
      Dockerfile: CMD uv pip install -r requirements-web.txt
      ↓
      Creates venv in volume ✅
```

**Critical Point**: Docker CANNOT run `uv export` because:
- The `COPY` command only reads files that already exist in the repo
- Docker build context is isolated from your machine's Python environment
- `uv export` is a Python tool that must run on your machine, not in Docker

**If you skip Step 3 (uv export)**:
```bash
# Docker tries to build
docker compose build web-venv-builder

# Error: requirements-web.txt not found
# Because you never created it with 'uv export'
```

---

### Dockerfile Multi-Stage Build

```dockerfile
# Stage 1: venv-builder (for Dockerfile production builds)
FROM base AS venv-builder
RUN apt-get install build-essential libpq-dev
COPY pyproject.toml uv.lock ./
CMD ["uv", "sync", "--frozen", "--no-dev"]
# Result: /app/.venv with all dependencies
# (This stage uses uv.lock directly, not requirements.txt)

# Stage 2: web-base (actual web service)
FROM python:3.13.9-slim AS web-base
COPY . .
# Mounts web_venv volume with prebuilt venv from venv-builder

# Stage 3: web-venv-builder (for docker-compose local development)
FROM web-base AS web-venv-builder
COPY requirements-web.txt ./           ← Reads requirements file from repo
CMD ["sh", "-c", "uv venv && uv pip install --no-cache -r requirements-web.txt"]
# Result: /app/.venv with web-specific dependencies
```

**Two different approaches**:
- **venv-builder stage**: Uses `uv sync` with `pyproject.toml` + `uv.lock` (for production)
- **web-venv-builder stage**: Uses `uv pip install` with `requirements-web.txt` (for local compose)

Both need the source files to be in the repo for Docker to `COPY` them.

---

### Docker Compose: Venv Builder Services

Each venv builder is a **service** that:
1. Builds once to completion (`restart: "no"`)
2. Installs from its specific `requirements-*.txt` file
3. Outputs to a named **volume** (`web_venv:/app/.venv`)

The actual service containers then **mount** that volume:

```yaml
services:
  web-venv-builder:
    build:
      target: web-venv-builder
    volumes:
      - web_venv:/app/.venv      # Output venv to this volume
    restart: "no"
    # This runs once and exits
    # Creates a venv by installing requirements-web.txt

  web:                          # Actual web server
    build:
      target: web-base
    depends_on:
      web-venv-builder:
        condition: service_completed_successfully
    volumes:
      - web_venv:/app/.venv     # Reuse prebuilt venv
    restart: on-failure:5
    # Waits for builder to finish
    # Then starts, reusing the cached venv from volume
```

**Startup Order**:
1. `web-venv-builder` runs: `COPY requirements-web.txt ./` → `uv pip install -r requirements-web.txt`
2. Creates `web_venv` volume with installed packages
3. `web` container waits for builder to complete
4. `web` container starts, mounting the prebuilt venv
5. No reinstallation needed every restart (volume is cached)

## Troubleshooting

### Issue: "venv not found" or "dependencies not installed"

```bash
# Rebuild just the venv builders
docker compose build --no-cache web-venv-builder
docker compose build --no-cache ocr-venv-builder
docker compose build --no-cache beat-venv-builder
docker compose build --no-cache general-venv-builder

# Restart services
docker compose down
docker compose up -d
```

### Issue: "Permission denied" when editing requirements files

```bash
# The Docker containers create root-owned files
# Fix ownership:
sudo chown -R $(id -u):$(id -g) requirements*.txt uv.lock

# Or run Docker commands with your user ID:
docker compose exec -u $(id -u):$(id -g) web uv sync
```

### Issue: Dependency conflicts after update

```bash
# Check which packages are conflicting
docker compose exec web uv run pip check

# If uv.lock is corrupted, regenerate:
rm uv.lock
uv sync

# If conflicts persist, check version constraints in pyproject.toml:
cat pyproject.toml | grep -A 2 "conflicting_package"
```

### Issue: OCR container still using old Tesseract version

```bash
# OCR libs are system packages, not Python
# Check what's installed in image:
docker compose exec celery-ocr-worker tesseract --version

# To update system packages, edit Dockerfile:
# OCR-base stage: add newer package to apt-get install list
# Then rebuild:
docker compose build --no-cache ocr-base

# This rebuilds all OCR containers using the new base
```

## File Management: What to Edit, What NOT to Edit

### Files You SHOULD Edit

| File | When | How | Why |
|------|------|-----|-----|
| `pyproject.toml` | Want to update a package | Edit version number directly | This is the source of truth |
| `uv.lock` | Never | Let `uv sync` handle it | Automatically regenerated |
| `requirements.txt` | Never | Use `uv export` | Auto-generated from uv.lock |
| `requirements-*.txt` | Never | Use `uv export` | Auto-generated subsets |

### Workflow: What to Edit in What Order

```
1. EDIT ONLY THIS:
   ✏️  pyproject.toml

2. RUN (DON'T EDIT):
   $ uv sync
   → uv.lock is auto-updated

3. RUN (DON'T EDIT):
   $ uv export --format requirements-txt > requirements.txt
   $ cp requirements.txt requirements-*.txt
   → All requirement files are auto-generated

4. COMMIT ALL:
   git add pyproject.toml uv.lock requirements*.txt
   git commit -m "..."
```

---

## Summary Checklist: Updating Packages

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `nano pyproject.toml` | ✏️ Edit version numbers ONLY |
| 2 | `uv sync` | Auto-update uv.lock (don't delete, don't edit) |
| 3 | `uv export --format requirements-txt > requirements.txt` | Auto-generate requirements.txt |
| 4 | `cp requirements.txt requirements-{web,ocr,beat,general}.txt` | Auto-generate per-container files |
| 5 | `git add pyproject.toml uv.lock requirements*.txt` | Stage all updated files |
| 6 | `git diff --cached \| head -50` | Review changes before commit |
| 7 | `git commit -m "chore: update packages..."` | Commit |
| 8 | `docker compose build --no-cache *-venv-builder` | Rebuild venv volumes |
| 9 | `docker compose up -d && sleep 10` | Start services |
| 10 | `docker compose logs web \| head -30` | Check for startup errors |
| 11 | `docker compose exec web uv run pytest tests/` | Run tests |
| 12 | `git push` | Push to remote |

## Additional Resources

- **Python Packaging**: [packaging.python.org](https://packaging.python.org/)
- **uv Documentation**: [astral.sh/uv](https://astral.sh/uv)
- **pip-audit**: Automated vulnerability scanning
- **PyPI JSON API**: Used by `package_update_scanner.py`
- **Docker Volumes**: [docs.docker.com/storage/volumes](https://docs.docker.com/storage/volumes)