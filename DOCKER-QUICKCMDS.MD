# Docker commands for setting up the app 

Notes:
- Docker Compose auto-loads `.env` in the repo root. No `--env-file` flags needed.
- Runtime containers use `SKIP_UV_SYNC=true` and rely on the venv builders.

Adding a new Python package:
1) Add it to `pyproject.toml`.

2) Genherate the appropriate venv requirements file:
    ` ./scripts/export_requirements.sh `
   This uses uv inside web container.

3) Rebuild and rerun the matching venv builder:
   - `docker compose build <service>-venv-builder`
   - `docker compose up <service>-venv-builder -d`

```bash

##  If you are in production
# rm docker-compose.override.yml 
# rm develop.secrets.env

# If Fresh Install
cp deploy.secrets.env.example deploy.secrets.env
nano deploy.secrets.env

ln -sf deploy.secrets.env .env


## BACKUP
python3 scripts/backup_db.py

# Bring down any existing conatiners
docker compose down

# FIRST STEP PostGres and Redis
docker compose up -d db cache 
docker compose logs db cache -f --tail=200

# SECOND STEP VENV Builders FIRST

docker volume rm   fundus_img_xtract_web_venv fundus_img_xtract_ocr_venv fundus_img_xtract_beat_venv fundus_img_xtract_general_venv

## If packages changed 
   ### generate Reuirements.txts for each container
   ./scripts/export_requirements.sh


   ### Create venv buiders
   docker compose build --no-cache web-venv-builder  
   docker compose build --no-cache ocr-venv-builder beat-venv-builder general-venv-builder  


## If No packages changed 
   ### Create venv buiders
   docker compose build  web-venv-builder ocr-venv-builder beat-venv-builder general-venv-builder  

## Bring up VNEV Builders
docker compose up web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder -d
docker compose logs  web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder --tail=100

# THIRD STEP Main Containers SERVICES SECOND
docker compose up web celery-ocr-worker celery-general-worker celery-beat -d
docker compose logs web-venv-builder web celery-ocr-worker celery-general-worker celery-beat --tail=100 -f



docker compose build --no-cache beat-venv-builder 
docker compose restart celery-beat
### Celery conatiners restart
docker compose restart celery-ocr-worker celery-general-worker celery-beat

## ROUTINE HOSUEKPING 
docker compose down
docker compose up
docker compose up -d

# Logs
docker compose logs --tail=100 -f
docker compose logs web  --tail=100 -f
docker compose logs web db --tail=100 -f
docker compose logs web celery-ocr-worker celery-general-worker celery-beat --tail=100 -f


#sizes
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Size}}" | grep -E "NAME|fundus"

docker system df -v | grep -E "(fundus.*venv|Local Volumes)" 

# Stop Start
docker compose   stop web
docker compose   start web

docker compose up web celery-ocr-worker celery-general-worker celery-beat -d

docker compose stop    web celery-ocr-worker celery-general-worker celery-beat
docker compose start   web celery-ocr-worker celery-general-worker celery-beat
docker compose restart web celery-ocr-worker celery-general-worker celery-beat
docker compose logs --tail = 200 -f  web celery-ocr-worker celery-general-worker celery-beat

# Database backup (timestamped)
mkdir -p backups
docker compose exec -T db bash -lc 'pg_dump -U "$POSTGRES_APP_USER" -d "$POSTGRES_APP_DB"' > backups/backup_$(date +%Y%m%d_%H%M%S).sql

# Alembic Commands
docker compose exec web  uv run alembic history
docker compose exec web  uv run alembic heads
docker compose exec web  uv run alembic current
docker compose exec web  uv run alembic upgrade head
 

# User Creation
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

# 3. Remove build cache (safe, rebuilds wiregenerate)
docker builder prune -f

# Unused vilume prune
docker volume ls --filter dangling=true 
docker system df -v | grep -A 20 "Local Volumes" | sort -k3 -h    
docker volume prune -f

# 4. Check space saved   
docker system df
docker system df 
docker image prune -a -f
docker builder prune -f  
docker system prune -a -f
```


## STATS LOGGER


```
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
# Add overrides as needed for Coookie HTTPS, Secure etc
nano develop.config.env
cp docker-compose.override.yml.example docker-compose.override.yml 

docker compose   build  web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder web celery-ocr-worker celery-general-worker celery-beat

docker compose up -d db cache


docker compose   up web-venv-builder ocr-venv-builder general-venv-builder beat-venv-builder -d
docker compose   up web celery-ocr-worker celery-general-worker celery-beat -d
docker compose   logs web -f



``
