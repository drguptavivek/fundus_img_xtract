# Docker commands for setting up the app

Notes:
- Docker Compose auto-loads `.env` in the repo root. No `--env-file` flags needed.
- Runtime containers use `SKIP_UV_SYNC=true` and rely on the venv builders.

## Base images

- The base images define the OS + Python runtime + shared system packages.
- They are the foundation for runtime services and venv builders.
- `common-base` is the shared stage with OS deps + uv.
- `web-base`, `beat-base`, `general-base`, and `ocr-base` inherit from `common-base`.
- `base` adds OCR libs on top of `common-base` and is used for the full runtime.

## Requirements exporter

- `requirements-exporter` manages Python requirements for each container from the common `pyproject.toml`.
- It runs `uv export` against dependency groups:
  - `uv export --extra web ...` → `requirements-web.txt`
  - `uv export --extra ocr ...` → `requirements-ocr.txt`
  - `uv export --extra beat ...` → `requirements-beat.txt`
  - `uv export --extra general ...` → `requirements-general.txt`
  - `uv export ...` → `requirements.txt` (core)
- The container provides Python + uv, mounts the repo, and writes files to the host.

## Venv builders

- Venv builders inherit from respective base images.
- Inheritance chain:
  - `web-venv-builder` → `web-base` → `common-base`
  - `ocr-venv-builder` → `ocr-base` → `common-base`
  - `beat-venv-builder` → `beat-base` → `common-base`
  - `general-venv-builder` → `general-base` → `common-base`
  - `venv-builder` (generic `uv sync`) → `common-base`

## Adding a new Python package

1) Add it to `pyproject.toml`.

2) Generate requirements files:
   - `docker compose build requirements-exporter`
   - `./scripts/export_requirements.sh`

3) Rebuild and rerun the matching venv builder:
   - `docker compose build <service>-venv-builder`
   - `docker compose up <service>-venv-builder -d`

```bash
## If you are in production
# rm docker-compose.override.yml
# rm develop.secrets.env

# If Fresh Install
cp deploy.secrets.env.example deploy.secrets.env
nano deploy.secrets.env

ln -sf deploy.secrets.env .env

# BACKUP
python3 scripts/backup_db.py

# Bring down any existing containers
docker compose down

# FIRST STEP: Postgres and Redis
docker compose up -d db cache
docker compose logs db cache -f --tail=200

# SECOND STEP: Venv builders

docker volume rm fundus_img_xtract_web_venv fundus_img_xtract_ocr_venv fundus_img_xtract_beat_venv fundus_img_xtract_general_venv

## If packages changed
### Generate requirements.txt for each container via requirements-exporter
./scripts/export_requirements.sh

### Create venv builders
# 1. Rebuild images (only needed if Dockerfile or requirements files changed)
docker compose build web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder

# 2. Update the venv volumes (this installs/updates packages)
docker compose up web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder -d

## If no packages changed
### Build venv builders (rebuilds images only)
docker compose build web-venv-builder ocr-venv-builder beat-venv-builder general-venv-builder

## Bring up venv builders (installs Python packages)
# Runs the venv builder containers. They create/refresh /app/.venv by running:
# - uv venv (only if missing)
# - uv pip install -r requirements-*.txt
docker compose up web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder -d
docker compose logs web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder --tail=100

# THIRD STEP: Main containers (app code uses the venvs)
docker compose up web celery-ocr-worker celery-general-worker celery-beat -d
docker compose logs web-venv-builder web celery-ocr-worker celery-general-worker celery-beat --tail=100 -f

### Rebuild a specific venv builder
# 1. Build
docker compose build web-venv-builder
# 2. Run to update the venv volume
docker compose up web-venv-builder -d

# Replace web-venv-builder with ocr-venv-builder, general-venv-builder, or beat-venv-builder as needed.

docker compose restart celery-beat

### Celery containers restart
docker compose restart celery-ocr-worker celery-general-worker celery-beat

## ROUTINE HOUSEKEEPING
docker compose down
docker compose up
docker compose up -d

# Logs
docker compose logs --tail=100 -f
docker compose logs web --tail=100 -f
docker compose logs web db --tail=100 -f
docker compose logs web celery-ocr-worker celery-general-worker celery-beat --tail=100 -f

# Sizes
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Size}}" | grep -E "NAME|fundus"

docker system df -v | grep -E "(fundus.*venv|Local Volumes)"

# Stop / Start
docker compose stop web
docker compose start web

docker compose up web celery-ocr-worker celery-general-worker celery-beat -d

docker compose stop web celery-ocr-worker celery-general-worker celery-beat
docker compose start web celery-ocr-worker celery-general-worker celery-beat
docker compose restart web celery-ocr-worker celery-general-worker celery-beat
docker compose logs --tail=200 -f web celery-ocr-worker celery-general-worker celery-beat

# Database backup (timestamped)
python3 scripts/backup_db.py

# Alembic commands
docker compose exec web uv run alembic history
docker compose exec web uv run alembic heads
docker compose exec web uv run alembic current
docker compose exec web uv run alembic upgrade head

# User creation
docker compose exec web /bin/bash
uv run python -m scripts.create_user admin
uv run python -m scripts.assign_roles admin --roles admin ophthalmologist optometrist
exit

# Check service status
docker compose ps
docker compose logs web

# Permissions
sudo chown -R $USER:$USER /home/eyeimg/fundus_img_xtract

# Clean up first to save space
docker system df
docker system df -v

# 2. Remove dangling images only (safest)
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | sort -k3 -h
docker image prune -f

# 3. Remove build cache (safe, rebuilds will regenerate)
docker builder prune -f
docker builder prune --filter "until=168h"

# Unused volume prune
docker volume ls --filter dangling=true
docker system df -v | grep -A 20 "Local Volumes" | sort -k3 -h
docker volume prune -f

# 4. Check space saved
docker system df
```

## Stats logger

```bash
# 1) Stop/remove any stats-logger containers
docker rm -f $(docker ps -a --filter name=fundus-img-xtract-stats --format '{{.ID}}') 2>/dev/null || true
# 2) Remove all stats-logger images
docker rmi -f $(docker images --format '{{.ID}} {{.Repository}}' | awk '$2 ~ /stats-logger/{print $1}') 2>/dev/null || true

# 3) Rebuild and start fresh
docker compose -f docker-compose.yml -f docker-compose.stats.yml up -d --build stats-logger
```
