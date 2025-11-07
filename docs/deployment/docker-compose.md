# Docker Compose Deployment

This stack runs the Fundus Image Manager, PostgreSQL, and Redis in containers. The application container listens on port 5001 and is intended to sit behind an existing reverse proxy that terminates TLS.

## 1. Prepare environment variables

1. Copy `deploy.config.env.example` to `deploy.config.env` (non-sensitive runtime config).
2. Copy `deploy.secrets.env.example` to `deploy.secrets.env` and fill in strong credentials.
3. Keep `deploy.secrets.env` restricted (permissions 600) and out of version control.



## 2. Build and launch

```bash


docker compose --env-file deploy.secrets.env build
docker compose up -d

```
#### DATABASE


``bash
docker compose exec web uv run alembic upgrade head
```

The application is available on `http://localhost:5001` by default. The Postgres service exposes `${POSTGRES_PORT}` on the host so tools such as pgAdmin can connect using the credentials defined in `deploy.secrets.env`.

## 3. Reverse proxy integration

Configure your existing proxy to forward HTTPS traffic to `http://<docker-host>:5001`. Ensure the proxy forwards `X-Forwarded-Proto=https` so Flask recognises secure requests.

## 4. Persistent data

- Application uploads/logs: bind-mounts (`./files`, `./logs`).
- PostgreSQL data: named volume `postgres_data`.
- Redis data: named volume `redis_data`.

## 5. Maintenance

- View logs: `docker compose logs -f web`.
- Rotate secrets: update `deploy.secrets.env`, then `docker compose up -d` to recreate containers.
- Database access: connect pgAdmin to `host=<docker-host> port=${POSTGRES_PORT}` using the credentials from `deploy.secrets.env`.

## 6. Cleanup

```bash
docker compose down
docker volume rm fundus-img-xtract_postgres_data fundus-img-xtract_redis_data
```

Remove bind-mounted directories only if you no longer need the data.
