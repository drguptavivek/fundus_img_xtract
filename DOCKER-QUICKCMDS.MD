# Rapid Docker commands for setting up the app 

```bash

docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env down -v
docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache

docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env logs db cache

docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env build 


docker compose --env-file deploy.config.env   --env-file deploy.secrets.env up  web -d

docker compose --env-file deploy.config.env   --env-file deploy.secrets.env logs web -f

# User Creation
docker compose --env-file deploy.config.env   --env-file deploy.secrets.env exec web /bin/bash
uv run python -m scripts.create_user admin
uv run python -m scripts.assign_roles admin --roles admin ophthalmologist optometrist
exit

# Check service status
docker compose ps
docker compose logs web

sudo chown -R $USER:$USER /home/eyeimg/fundus_img_xtract
```

## DEVELOPMENT


```bash
cp docker-compose.override.yml.example docker-compose.override.yml 

docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   build  web

docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache


docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   up web -d
docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   logs web -f

``