# Docker Compose Deployment

This stack runs the Fundus Image Manager, PostgreSQL, and Redis in containers. The application container listens on port 5001 and is intended to sit behind an existing reverse proxy that terminates TLS.
For Docker-based development, `develop.config.env` can be used as an override and is loaded via `docker-compose.override.yml` when present.

## 1. Prepare environment variables

1. Copy `deploy.config.env.example` to `deploy.config.env` (non-sensitive runtime config).
2. Copy `deploy.secrets.env.example` to `deploy.secrets.env` and fill in strong credentials.
3. Keep `deploy.secrets.env` restricted (permissions 600) and out of version control.
4. (Development only) Copy `develop.config.env.example` to `develop.config.env` for dev overrides.




## Integration of Redis Configuration Components

The system implements a flexible Redis configuration system that integrates three key components: [`deploy.secrets.env`](deploy.secrets.env:1), [`docker-compose.yml`](docker-compose.yml:1), and [`utils/redis_connection.py`](utils/redis_connection.py:1). Here's how they work together:

### 1. Environment Variables Configuration (`deploy.secrets.env`)

The [`deploy.secrets.env`](deploy.secrets.env:17-21) file  contains all Redis configuration variables:
```bash
# Redis
REDIS_PASSWORD="Aemae6ca-moeFei3e-Ahk3Gua3-eew6pieC"
REDIS_HOST=redis
REDIS_HOST_LOCAL=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
```

This follows the same pattern as PostgreSQL, providing:
- **REDIS_HOST**: For Docker environments (set to "redis" to match the service name)
- **REDIS_HOST_LOCAL**: For local development (set to "127.0.0.1")
- **REDIS_PASSWORD**: Authentication credentials
- **REDIS_PORT** and **REDIS_DB**: Connection parameters

### 2. Docker Configuration (`docker-compose.yml`)

The [`docker-compose.yml`](docker-compose.yml:17-21)  passes these environment variables to the application container:
```yaml
environment:
  REDIS_HOST: ${REDIS_HOST}
  REDIS_PORT: ${REDIS_PORT}
  REDIS_DB: ${REDIS_DB}
  REDIS_PASSWORD: ${REDIS_PASSWORD}
```

This replaces the previous hardcoded `REDIS_URL` and allows the application to construct the Redis URL dynamically.

### 3. Centralized Connection Logic (`utils/redis_connection.py`)

The [`utils/redis_connection.py`](utils/redis_connection.py:15) module provides the [`build_redis_url()`](utils/redis_connection.py:15) function that:

1. **Implements Priority-Based Host Selection**:
   - First checks `REDIS_HOST_OVERRIDE` (for temporary overrides)
   - Then checks `REDIS_HOST_LOCAL` (for local development)
   - Then uses `REDIS_HOST` (for Docker environments)
   - Falls back to "127.0.0.1" if none are set

2. **Constructs the Redis URL**:
   ```python
   redis_url = f"redis://{password_part}{redis_host}:{redis_port}/{redis_db}"
   ```

3. **Handles Password Authentication**:
   - URL-encodes the password for safety
   - Only includes password if it exists

### 4. Integration with Rate Limiter

The [`utils/rate_limiter.py`](utils/rate_limiter.py:1) now imports and uses the centralized function:
```python
from utils.redis_connection import build_redis_url

app.config['RATELIMIT_REDIS_URL'] = build_redis_url()
```

### How It Works in Different Environments:

**Docker Environment**:
- `REDIS_HOST=redis` (matches the Redis service name in docker-compose)
- `build_redis_url()` returns: `redis://:password@redis:6379/0`

**Local Development**:
- `REDIS_HOST_LOCAL=127.0.0.1` (overrides the Docker host)
- `build_redis_url()` returns: `redis://:password@127.0.0.1:6379/0`

**Temporary Override**:
- Set `REDIS_HOST_OVERRIDE=custom-host` for testing
- `build_redis_url()` returns: `redis://:password@custom-host:6379/0`

This implementation provides the same flexible environment switching for Redis that PostgreSQL already had, allowing seamless transitions between Docker-based development and local development without changing code.




## DATABASE

The system implements a flexible PostgreSQL configuration system that integrates three key components: [`deploy.secrets.env`](deploy.secrets.env.example:1), [`docker-compose.yml`](docker-compose.yml:1), and [`models.py`](models.py:1). Here's how they work together:

### 1. Environment Variables Configuration (`deploy.secrets.env`)

The [`deploy.secrets.env.example`](deploy.secrets.env.example:7-12) file contains all PostgreSQL configuration variables:
```bash
# PostgreSQL
POSTGRES_APP_DB=fundus_app
POSTGRES_APP_USER=fundus_user
POSTGRES_APP_PASSWORD=change-this-password
POSTGRES_HOST=db
POSTGRES_PORT=5432
```

This provides:
- **POSTGRES_APP_DB**: Database name for the application
- **POSTGRES_APP_USER**: Database user for the application
- **POSTGRES_APP_PASSWORD**: Authentication credentials
- **POSTGRES_HOST**: For Docker environments (set to "db" to match the service name)
- **POSTGRES_PORT**: Connection port (default 5432)

### 2. Docker Configuration (`docker-compose.yml`)

The [`docker-compose.yml`](docker-compose.yml:28-49) configures the PostgreSQL service and passes environment variables:

### Database Service Configuration:
```yaml
db:
  image: postgres:18-alpine
  container_name: fundus-img-xtract-db
  env_file:
    - deploy.config.env
    - deploy.secrets.env
  environment:
    POSTGRES_DB: ${POSTGRES_APP_DB}
    POSTGRES_USER: ${POSTGRES_APP_USER}
    POSTGRES_PASSWORD: ${POSTGRES_APP_PASSWORD}
    POSTGRES_PORT: ${POSTGRES_PORT:-5432}
  ports:
    - "${POSTGRES_PORT:-5432}:5432"
  volumes:
    - postgres_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_APP_USER} -d ${POSTGRES_APP_DB}"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 10s
  restart: unless-stopped
```

### Application Service Configuration:
```yaml
web:
  environment:
    DATABASE_URL: postgresql://${POSTGRES_APP_USER}:${POSTGRES_APP_PASSWORD}@db:5432/${POSTGRES_APP_DB}
```

This configuration:
- Creates a PostgreSQL container using the official Alpine image
- Passes credentials and database name from environment variables
- Exposes the port to the host for external access
- Includes health checks to ensure database readiness
- Persists data using a named volume
- Constructs the DATABASE_URL for the application container

### 3. Database Connection Logic (`models.py`)

The [`models.py`](models.py:19-50) file provides the [`_build_database_url()`](models.py:19) function that constructs the database URL:

### Priority-Based Host Selection:
1. **Explicit DATABASE_URL**: If set, uses it directly
2. **Host Override**: Checks `POSTGRES_HOST_OVERRIDE` or `POSTGRES_HOST_LOCAL` for local development
3. **Docker Host**: Uses `POSTGRES_HOST` (for Docker environments)
4. **Fallback**: Defaults to "127.0.0.1" if none are set

### URL Construction:
```python
def _build_database_url(base_dir: Path) -> str:
    """Construct a database URL from available environment variables."""
    
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url
    
    postgres_db = (os.getenv("POSTGRES_APP_DB") or "").strip()
    postgres_user = (os.getenv("POSTGRES_APP_USER") or "").strip()
    host_override = os.getenv("POSTGRES_HOST_OVERRIDE") or os.getenv("POSTGRES_HOST_LOCAL")
    postgres_host_raw = host_override if host_override and host_override.strip() else os.getenv("POSTGRES_HOST")
    postgres_host = (postgres_host_raw or "127.0.0.1").strip()
    postgres_password = os.getenv("POSTGRES_APP_PASSWORD")
    raw_port = os.getenv("POSTGRES_PORT")
    postgres_port = raw_port.strip() if raw_port else "5432"
    
    if postgres_db and postgres_user:
        user_part = quote(postgres_user, safe="")
        password_part = ""
        if postgres_password and postgres_password.strip():
            password_part = f":{quote(postgres_password.strip(), safe='')}"
        
        host_part = postgres_host or "127.0.0.1"
        port_part = f":{postgres_port}" if postgres_port else ""
        return f"postgresql://{user_part}{password_part}@{host_part}{port_part}/{postgres_db}"
    
    _LOGGER.warning("DATABASE_URL not configured")
```


## How It Works in Different Environments:

### Docker Environment:
- `POSTGRES_HOST=db` (matches the PostgreSQL service name in docker-compose)
- `_build_database_url()` returns: `postgresql://fundus_user:password@db:5432/fundus_app`

### Local Development:
- `POSTGRES_HOST_LOCAL=127.0.0.1` (overrides the Docker host)
- `_build_database_url()` returns: `postgresql://fundus_user:password@127.0.0.1:5432/fundus_app`

### Temporary Override:
- Set `POSTGRES_HOST_OVERRIDE=custom-host` for testing
- `_build_database_url()` returns: `postgresql://fundus_user:password@custom-host:5432/fundus_app`


## Network
The docker compose file will connect all containers to a Docker network titled `fundus_img_xtract_default`

## Application Availability

The application is available on `http://localhost:5001` by default. 


## 3. Reverse proxy integration

Configure your existing proxy to forward HTTPS traffic to `http://<docker-host>:5001`. Ensure the proxy forwards `X-Forwarded-Proto=https` so Flask recognises secure requests.

## COOKIEs

Ensure that HTTP_SECURE is set to true once SSL has been set up. 
 - SESSION_COOKIE_SECURE=true

On localhost / 127.0.0.1 development, set 
 - SESSION_COOKIE_SECURE=false


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
