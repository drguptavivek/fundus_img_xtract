# Rapid Docker commands for setting up the app 

Notes:
- Docker Compose auto-loads `.env` in the repo root. No `--env-file` flags needed.
- Runtime containers use `SKIP_UV_SYNC=true` and rely on the venv builders.

Adding a new Python package:
1) Add it to `pyproject.toml`.
2) Update the appropriate venv requirements file:
   - `requirements-web.txt` for web
   - `requirements-ocr.txt` for OCR worker
   - `requirements-general.txt` for general worker
   - `requirements-beat.txt` for beat
3) Rebuild and rerun the matching venv builder:
   - `docker compose build <service>-venv-builder`
   - `docker compose up <service>-venv-builder -d`

```bash
rm docker-compose.override.yml 
rm develop.secrets.env

cp deploy.secrets.env.example deploy.secrets.env
nano deploy.secrets.env


ln -sf deploy.secrets.env .env



docker compose down -v
docker compose up -d db cache

docker compose logs db cache

docker compose build web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder web celery-ocr-worker celery-general-worker celery-beat

docker compose up web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder -d
docker compose up web celery-ocr-worker celery-general-worker celery-beat -d


docker compose   stop web

docker compose   start web

docker compose logs web  --tail=20 -f

docker compose exec web  uv run alembic upgrade head

# Database backup (timestamped)
mkdir -p backups
docker compose exec -T db bash -lc 'pg_dump -U "$POSTGRES_APP_USER" -d "$POSTGRES_APP_DB"' > backups/backup_$(date +%Y%m%d_%H%M%S).sql

# Alembic Commnsa
uv run alembic  history
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
 

# User Creation
docker compose exec web /bin/bash


uv run python -m scripts.create_user admin
uv run python -m scripts.assign_roles admin --roles admin ophthalmologist optometrist
exit

# Check service status
docker compose ps
docker compose logs web

sudo chown -R $USER:$USER /home/eyeimg/fundus_img_xtract


# 1) Stop/remove any stats-logger containers
docker rm -f $(docker ps -a --filter name=fundus-img-xtract-stats --format '{{.ID}}') 2>/dev/null || true
# 2) Remove all stats-logger images
docker rmi -f $(docker images --format '{{.ID}} {{.Repository}}' | awk '$2 ~ /stats-logger/{print $1}') 2>/dev/null || true

# 3) Rebuild and start fresh
docker compose  -f docker-compose.yml -f docker-compose.stats.yml up -d --build stats-logger


sudo chown -R $USER:$USER /home/eyeimg/fundus_img_xtract
```

## DEVELOPMENT


```bash
cp develop.config.env.example develop.config.env
cp docker-compose.override.yml.example docker-compose.override.yml 

docker compose   build  web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder web celery-ocr-worker celery-general-worker celery-beat

docker compose up -d db cache


docker compose   up web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder -d
docker compose   up web celery-ocr-worker celery-general-worker celery-beat -d
docker compose   logs web -f



``
