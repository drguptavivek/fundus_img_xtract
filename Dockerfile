FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    UV_PROJECT_ENVIRONMENT=/app/.venv

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
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
RUN mkdir -p /app/logs /app/files && \
    chmod 755 /app/logs /app/files

EXPOSE 5001

ENTRYPOINT ["/bin/bash", "docker/entrypoint.sh"]
CMD ["uv", "run", "gunicorn", "-c", "gunicorn_config.py", "wsgi:application"]
