#!/bin/bash

# Startup script for running the Fundus Image Manager with Gunicorn
# This script sets up the environment and starts the Gunicorn server

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if .env file exists
if [ ! -f .env ]; then
    print_warn ".env file not found. Using default environment variables."
    if [ -f .env.example ]; then
        print_info "Copying .env.example to .env"
        cp .env.example .env
        print_info "Please review and update the .env file with your specific configuration"
    fi
fi

# Create logs directory if it doesn't exist
mkdir -p logs

# Load environment variables from .env file
# This ensures all configuration is available to Gunicorn and the Flask application
if [ -f .env ]; then
    print_info "Loading environment variables from .env file"
    
    # Export all non-comment, non-empty lines from .env
    while IFS= read -r line; do
        # Skip empty lines and comments
        if [[ ! -z "$line" && ! "$line" =~ ^[[:space:]]*# ]]; then
            # Export the variable
            export "$line"
        fi
    done < .env
    
    print_info "Environment variables loaded successfully"
else
    print_warn "No .env file found. Using default values."
fi

# Set default values if not in environment
export FLASK_ENV=${FLASK_ENV:-production}
export GUNICORN_BIND=${GUNICORN_BIND:-127.0.0.1:5001}
export GUNICORN_WORKERS=${GUNICORN_WORKERS:-$(python3 -c "import multiprocessing; print(multiprocessing.cpu_count() * 2 + 1)")}
export GUNICORN_LOG_LEVEL=${GUNICORN_LOG_LEVEL:-info}
export GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120}

# Display configuration
print_info "Starting Fundus Image Manager with Gunicorn"
print_info "Environment: $FLASK_ENV"
print_info "Bind address: $GUNICORN_BIND"
print_info "Workers: $GUNICORN_WORKERS"
print_info "Log level: $GUNICORN_LOG_LEVEL"
print_info "Timeout: $GUNICORN_TIMEOUT seconds"

# Check if virtual environment exists
if [ -d ".venv" ]; then
    print_info "Virtual environment found at ./.venv"
    export VIRTUAL_ENV="$(pwd)/.venv"
    export PATH="$VIRTUAL_ENV/bin:$PATH"
elif [ ! -z "$VIRTUAL_ENV" ]; then
    print_warn "No virtual environment detected. Using system Python."
else
    print_info "Using virtual environment: $VIRTUAL_ENV"
fi

# Install dependencies if needed
if [ "$FLASK_ENV" = "development" ] && [ "$INSTALL_DEPS" = "true" ]; then
    print_info "Installing dependencies with uv..."
    uv pip install
fi

# Start Gunicorn
print_info "Starting Gunicorn server..."
exec uv run gunicorn -c gunicorn_config.py wsgi:application