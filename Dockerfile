# ======================================================================
# BASE — Debian 13 trixie (runtime)
# ======================================================================
FROM python:3.13.9-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# ======================================================================
# OS PACKAGES + Postgres repo + OCR libs
# ======================================================================
# ======================================================================
# FIX APT MIRRORS → FORCE HTTPS (critical!)
# ======================================================================
RUN set -eux; \
    rm -f /etc/apt/sources.list.d/debian.sources;\
    \
    printf "deb https://deb.debian.org/debian trixie main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n" \
    > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        logrotate \
        cron \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        libmagic1 \
        libpq5; \
    \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
        https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-18; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# ======================================================================
# UV (dependencies are installed into the shared /app/.venv volume)
# ======================================================================
RUN pip install --no-cache-dir uv

# ======================================================================
# Application code
# ======================================================================
COPY . .

RUN mkdir -p \
        /app/logs \
        /app/files \
        /var/log/fundus-img-xtract \
        /var/run/fundus-img-xtract \
    && chmod 755 \
        /app/logs \
        /app/files \
        /var/log/fundus-img-xtract \
        /var/run/fundus-img-xtract

# ======================================================================
# Logrotate + Cron setup
# ======================================================================
RUN cp /app/docker/logrotate.conf /etc/logrotate.d/fundus-img-xtract && \
    cp /app/docker/logrotate.cron /etc/cron.d/fundus-img-xtract && \
    chmod 0644 /etc/logrotate.d/fundus-img-xtract && \
    chmod 0644 /etc/cron.d/fundus-img-xtract && \
    touch /var/log/cron.log

EXPOSE 5001

ENTRYPOINT ["/bin/bash", "docker/entrypoint.sh"]
CMD ["uv", "run", "gunicorn", "-c", "gunicorn_config.py", "wsgi:application"]

# ======================================================================
# WEB BASE — runtime without OCR libs
# ======================================================================
FROM python:3.13.9-slim AS web-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN set -eux; \
    rm -f /etc/apt/sources.list.d/debian.sources;\
    \
    printf "deb https://deb.debian.org/debian trixie main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n" \
    > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        logrotate \
        cron \
        libmagic1 \
        libpq5; \
    \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
        https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-18; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY . .

RUN mkdir -p \
        /app/logs \
        /app/files \
        /var/log/fundus-img-xtract \
        /var/run/fundus-img-xtract \
    && chmod 755 \
        /app/logs \
        /app/files \
        /var/log/fundus-img-xtract \
        /var/run/fundus-img-xtract

RUN cp /app/docker/logrotate.conf /etc/logrotate.d/fundus-img-xtract && \
    cp /app/docker/logrotate.cron /etc/cron.d/fundus-img-xtract && \
    chmod 0644 /etc/logrotate.d/fundus-img-xtract && \
    chmod 0644 /etc/cron.d/fundus-img-xtract && \
    touch /var/log/cron.log

EXPOSE 5001

ENTRYPOINT ["/bin/bash", "docker/entrypoint.sh"]
CMD ["uv", "run", "gunicorn", "-c", "gunicorn_config.py", "wsgi:application"]

# ======================================================================
# VENV BUILDER — includes build tools for uv sync into shared volume
# ======================================================================
FROM base AS venv-builder

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

ENTRYPOINT []
CMD ["uv", "sync", "--frozen", "--no-dev"]

# ======================================================================
# OCR BASE — minimal runtime for OCR worker
# ======================================================================
FROM python:3.13.9-slim AS ocr-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN set -eux; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    printf "deb https://deb.debian.org/debian trixie main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n" \
    > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        tesseract-ocr \
        libgl1 \
        libglib2.0-0 \
        libpq5; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY . .

ENTRYPOINT ["/bin/bash", "docker/entrypoint_ocr.sh"]
CMD ["uv", "run", "celery", "-A", "celery_worker", "worker", "--loglevel=info"]

# ======================================================================
# OCR VENV BUILDER — installs OCR deps into ocr venv volume
# ======================================================================
FROM ocr-base AS ocr-venv-builder

COPY requirements-ocr.txt ./

ENTRYPOINT []
CMD ["sh", "-c", "uv venv && uv pip install --no-cache -r requirements-ocr.txt"]

# ======================================================================
# WEB VENV BUILDER — installs web deps into web venv volume
# ======================================================================
FROM web-base AS web-venv-builder

COPY requirements-web.txt ./

ENTRYPOINT []
CMD ["sh", "-c", "uv venv && uv pip install --no-cache -r requirements-web.txt"]

# ======================================================================
# BEAT BASE — minimal runtime for celery beat
# ======================================================================
FROM python:3.13.9-slim AS beat-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN set -eux; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    printf "deb https://deb.debian.org/debian trixie main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n" \
    > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libpq5; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY . .

ENTRYPOINT ["/bin/bash", "docker/entrypoint_beat.sh"]
CMD ["uv", "run", "celery", "-A", "celery_beat_app", "beat", "--loglevel=info"]

# ======================================================================
# BEAT VENV BUILDER — installs minimal deps into beat venv volume
# ======================================================================
FROM beat-base AS beat-venv-builder

COPY requirements-beat.txt ./

ENTRYPOINT []
CMD ["sh", "-c", "uv venv && uv pip install --no-cache -r requirements-beat.txt"]

# ======================================================================
# GENERAL BASE — minimal runtime for celery general worker
# ======================================================================
FROM python:3.13.9-slim AS general-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN set -eux; \
    rm -f /etc/apt/sources.list.d/debian.sources; \
    printf "deb https://deb.debian.org/debian trixie main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware\n\
deb https://deb.debian.org/debian-security trixie-security main contrib non-free non-free-firmware\n" \
    > /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libpq5; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY . .

ENTRYPOINT ["/bin/bash", "docker/entrypoint_general.sh"]
CMD ["uv", "run", "celery", "-A", "celery_worker", "worker", "--loglevel=info"]

# ======================================================================
# GENERAL VENV BUILDER — installs minimal deps into general venv volume
# ======================================================================
FROM general-base AS general-venv-builder

COPY requirements-general.txt ./

ENTRYPOINT []
CMD ["sh", "-c", "uv venv && uv pip install --no-cache -r requirements-general.txt"]
