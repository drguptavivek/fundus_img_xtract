# Export Requirements Script

## Overview

`export_requirements.sh` auto-generates all per-container requirements files from `pyproject.toml` dependency groups.

## Usage

```bash
# From project root
./scripts/export_requirements.sh
```

## What It Does

1. Checks if web container is running (starts it if needed)
2. Runs `uv export` for each dependency group inside the container:
   - `--extra web` → `requirements-web.txt`
   - `--extra ocr` → `requirements-ocr.txt`
   - `--extra beat` → `requirements-beat.txt`
   - `--extra general` → `requirements-general.txt`
   - Core only → `requirements.txt`
3. Copies generated files from container to host
4. Shows summary of package counts

## Output Example

```
🔄 Exporting per-container requirements files...

📦 Generating requirements files...
✅ Generated all requirement files in container

📋 Copying files from container to host...

✅ Successfully exported requirements files:

  75 requirements.txt
  79 requirements-beat.txt
 110 requirements-general.txt
  97 requirements-ocr.txt
 418 requirements-web.txt
 779 total

📊 Package counts by container:
  Core only:     75 packages
  Web:          418 packages
  OCR:           97 packages
  Beat:          79 packages
  General:      110 packages

✅ Done! Now run:
   git add requirements*.txt
   git commit -m 'chore: regenerate requirements files'
```

## When to Run

Run this script whenever you:
- Update package versions in `pyproject.toml`
- Add new packages to dependency groups
- Remove packages from dependency groups
- Change dependency group structure

## Workflow

```bash
# 1. Edit pyproject.toml
nano pyproject.toml
# Add to [project.optional-dependencies.ocr]:
#   "new-package==1.2.3"

# 2. Sync uv.lock
docker compose exec web uv sync

# 3. Regenerate requirement files
./scripts/export_requirements.sh

# 4. Commit changes
git add pyproject.toml uv.lock requirements*.txt
git commit -m "feat: add new-package to OCR container"
git push

# 5. Rebuild containers
docker compose build --no-cache ocr-venv-builder
docker compose up -d celery-ocr-worker
```

## Dependency Groups

Defined in `pyproject.toml`:

```toml
[project]
# Core (all containers)
dependencies = [
    "celery[redis]==5.6.2",
    "redis>=5.0.4,<6.5",
    "sqlalchemy==2.0.46",
    "psycopg2-binary==2.9.11",
    "flask==3.1.2",
    "python-dotenv==1.2.1",
]

[project.optional-dependencies]
web = [ ... ]      # Web server specific
ocr = [ ... ]      # OCR worker specific
beat = [ ... ]     # Celery Beat specific
general = [ ... ]  # General worker specific
```

## Container Size Impact

**Important**: Auto-generated files include all transitive dependencies, BUT container sizes remain the same as hand-curated minimal files.

| Approach | Requirements File Size | Packages Installed | Container Size |
|----------|----------------------|-------------------|----------------|
| Hand-curated (12 lines) | Small | ~97 packages | X MB |
| Auto-generated (97 lines) | Large | ~97 packages | X MB (SAME) |

**Why**: Docker installs the same packages either way. The requirements file is NOT included in the final container.

## Troubleshooting

### Web container not running

```bash
docker compose up -d web
sleep 5
./scripts/export_requirements.sh
```

### Permission errors

```bash
chmod +x ./scripts/export_requirements.sh
```

### Old files not updated

The script overwrites existing files. Make sure to commit your changes first if you want to preserve them.
