# Rapid Docker commands for setting up the app 

```bash
rm docker-compose.override.yml 
rm develop.secrets.env

cp deploy.secrets.env.example deploy.secrets.env
nano deploy.secrets.env

docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env down -v
docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache

docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env logs db cache

docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env build web

docker compose --env-file deploy.config.env   --env-file deploy.secrets.env up  web -d


docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   stop web

docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   start web

docker compose --env-file deploy.config.env   --env-file deploy.secrets.env logs web  --tail=20 -f

docker compose --env-file deploy.config.env   --env-file deploy.secrets.env exec web  uv run alembic upgrade head

# Alembic Commnsa
uv run alembic  history
uv run alembic heads
uv run alembic current
 uv run alembic upgrade head
 

# User Creation
docker compose --env-file deploy.config.env   --env-file deploy.secrets.env exec web /bin/bash


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
docker compose --env-file deploy.config.env   --env-file deploy.secrets.env  -f docker-compose.yml -f docker-compose.stats.yml up -d --build stats-logger


sudo chown -R $USER:$USER /home/eyeimg/fundus_img_xtract
```

## DEVELOPMENT


```bash
cp develop.config.env.example develop.config.env
cp docker-compose.override.yml.example docker-compose.override.yml 

docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   build  web

docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache


docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   up web -d
docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   logs web -f



``
