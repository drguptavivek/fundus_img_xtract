FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Add PostgreSQL repository for PostgreSQL 18
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        logrotate \
        cron \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt/ $(. /etc/os-release && echo $VERSION_CODENAME)-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        postgresql-client-18 \
        tesseract-ocr \
        libtesseract-dev \
        poppler-utils \
        ghostscript \
        libgl1 \
        libglib2.0-0 \
        libmagic1 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifests first for better caching
COPY pyproject.toml uv.lock ./

# Install uv and sync dependencies
RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

# Copy application code
COPY . .

# Ensure runtime directories exist
RUN mkdir -p /app/logs /app/files /var/log/fundus-img-xtract /var/run/fundus-img-xtract && \
    chmod 755 /app/logs /app/files /var/log/fundus-img-xtract /var/run/fundus-img-xtract

# Set up logrotate configuration and cron job
RUN cp /app/docker/logrotate.conf /etc/logrotate.d/fundus-img-xtract && \
    cp /app/docker/logrotate.cron /etc/cron.d/fundus-img-xtract && \
    chmod 0644 /etc/logrotate.d/fundus-img-xtract && \
    chmod 0644 /etc/cron.d/fundus-img-xtract && \
    touch /var/log/cron.log

EXPOSE 5001

ENTRYPOINT ["/bin/bash", "docker/entrypoint.sh"]
CMD ["uv", "run", "gunicorn", "-c", "gunicorn_config.py", "wsgi:application"]
