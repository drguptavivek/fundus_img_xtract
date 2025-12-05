# ======================================================================
# BASE — Debian 13 trixie 
# ======================================================================
FROM python:3.13.3-slim-trixie AS base

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
        build-essential \
        libpq-dev \
        tesseract-ocr \
        libtesseract-dev \
        poppler-utils \
        ghostscript \
        libgl1 \
        libglib2.0-0 \
        libmagic1; \
    \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc --fail \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \
        https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-18; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# ======================================================================
# UV + dependency installation
# ======================================================================
COPY pyproject.toml uv.lock ./

RUN pip install --no-cache-dir uv && \
    uv sync --frozen --no-dev

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
