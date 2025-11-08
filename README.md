# Fundus Image Manager

A comprehensive system for an eye hospital to manage eye images. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD). 
It is extensible

## DISEASES
 - Users can add more diseases. 
 - For each diseases, gradings can be added. 
 - For each grade, features can be optionally defined which users may select. [multiple features can be selected per grade]]

## Hospital and Labs/Units
 - Hospitals and Laboratory/Units can be added
 - User can be mapped to specific Laboratpry / Units within hospitals
 - This scopes their access (except for grading that has a slot based access system) to images/ data for these Labs/Units

## Users and roles
 - Multiple users can be added
 - Each user can get allocated various roles - 


Has specific workflows for Remedio FOP zip files that get downlaoded from the remedio dashboard

## DOCKER Containerized Deployment

For a Docker-based stack (Flask app, PostgreSQL, Redis) review [Docker Compose Deployment](docs/deployment/docker-compose.md). It covers the two-file environment setup 
- `deploy.config.env` for non-sensitive settings
- `deploy.secrets.env` for credentials)

It persistent bind mounts for `./files`, `./logs`.
It also allows for reverse-proxy integration.


#### Docker Production Deployment
To run the production container stack with Gunicorn:

```bash
# Copy env templates and fill in secrets if not already done
cp deploy.config.env.example deploy.config.env
cp deploy.secrets.env.example deploy.secrets.env  # edit values!


nano  deploy.secrets.env
# POSTGRES_HOST_LOCAL=127.0.0.1 <-- remove this in production 

# Enure overdide file is not present
rm docker-compose.override.yml

# Ensure Local development config is removed
rm develop.config.env

# BUILD MAIN APP Container
docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env build 

# docker-compose down cache && docker volume rm fundus_img_xtract_redis_data
# docker-compose down db && docker volume rm fundus_img_xtract_postgres_data



docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d cache


docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db


# DB and CaACHE
docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache

# MIGRATIONS - using a temporary APP container
# docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   run --rm web uv run alembic upgrade head
# Now migrations are handled during App docker container start
# This includes autom
# docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env build 
# docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env up


# Launch services (uses Gunicorn via docker-compose.yml)
docker compose --env-file deploy.config.env   --env-file deploy.secrets.env up -d

# User Creation
docker compose --env-file deploy.config.env   --env-file deploy.secrets.env exec web /bin/bash

uv run python -m scripts.create_user admin
uv run python -m scripts.assign_roles admin --roles admin


# Check service status
docker compose ps
docker compose logs web
```

Build Time (docker compose build):  uses the `dockerfile`
 - python:3.12-slim AS base
 - Installs System Dependencies - tesseract, libmagic, pq, uv etc
 - Copy Dependency files - `pyprroject.toml`.
 - Copy Application Code in /app in container
 - Sets .venv location - ENV UV_PROJECT_ENVIRONMENT=/app/.venv
 - Python packages installed using `uv sync`. Packages are installed in /app/.venv inside the container.
 - Copies the `entrypoint.sh` script into the container image
 - Sets `entrypoint.sh` as the ENTRYPOINT for the container. No execution happens during build

** In case of code chanmge, rebuild is needed to copy fresh code top the container**
`docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env build `

Runtime (docker compose up):
 - Container starts and executes the ENTRYPOINT script
 - The script runs all migration and setup logic
    - Directory Setup → Creates /app/logs, /app/files
    - Environment Setup → Sets secure cookie defaults
    - Database Wait → Waits for PostgreSQL readiness
    - Migration Execution → Runs `uv run alembic upgrade head`. All pending migrations get executed. 
    - Core Data Check. → Determines if seeding needed -  Hospitals, Labs/Units, Diseases, gradings, features
    - Conditional Seeding → Only seeds if core data missing
 - Finally executes the CMD (gunicorn server)

The First time, application is started, following migratiosn are done
1. **Initial Migration** (`5a49784f68f1`): Creates all database tables
2. **Data Seeding Migration** (`691d42ba3fff`): Safely populates core reference data. Uses @scripts/setup_core_entities.py


When done, shut down cleanly with `docker compose down`.
- Database and REDIS data persists in volumes
- Uploaded files are bind mounted in ./files/ directory


#### Docker based Development

For containerized development with live-reload:

1. Ensure `docker-compose.override.yml` is present (checked in). It bind-mounts the project into the `web` container and runs `flask --reload`.
2. Start the dependencies and the reload-enabled web service:

```bash
# Create docker-compose.override.yml
cp docker-compose.override.yml.example docker-compose.override.yml 

# Copy env templates and fill in secrets if not already done
cp deploy.config.env.example deploy.config.env
cp deploy.secrets.env.example deploy.secrets.env  # edit values!

nano  deploy.secrets.env
# POSTGRES_HOST_LOCAL=127.0.0.1 <-- ENSURE THIS IS REMOVED this for development so that docker hostname can be used to resolve the db container 

# BUILD App
docker compose  --env-file deploy.config.env  --env-file deploy.secrets.env  build web


# DBa nd CaACHE
docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache

# MIGRATIONS
docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   run --rm web uv run alembic upgrade head


# WEB Container
docker compose  --env-file deploy.config.env   --env-file deploy.secrets.env   up web

# User
docker compose --env-file deploy.config.env   --env-file deploy.secrets.env exec web /bin/bash
uv run python -m scripts.create_user admin
uv run python -m scripts.assign_roles admin --roles admin
uv run scripts/initial_setup.py 
uv run scripts/add_test_users.py

 
```
3. Edit source code locally; the container sees changes immediately and the Flask reloader restarts automatically.
4. When switching back to production settings, stop the dev stack (`docker compose down`) so subsequent `docker compose up` runs use the Gunicorn configuration without the override.



## NON-DOCKER DEVELROPMNENT
Only DB and Redis run in docker. The app runs in terminal via `uv run app.py`


```bash

# Copy env templates and fill in secrets if not already done
cp deploy.config.env.example deploy.config.env
cp deploy.secrets.env.example deploy.secrets.env  # edit values!

nano  deploy.secrets.env
# POSTGRES_HOST_LOCAL=127.0.0.1 <-- ENSURE THIS IS ORESENT this for development so that 127.0.0.1 is used to resolve the db container 

# REDIS_HOST_LOCAL=127.0.0.1 <-- ENSURE THIS IS ORESENT this for development so that 127.0.0.1 is used to resolve the db container 

nano docker-compose.yml
#  Ensure REDIS PORT is exposed to host and bound to 127.0.0.1 and not an open relay
#     ports:
#      -  "127.0.0.1:${REDIS_PORT:-6379}:6379"

# PREVENT REDIS OPEN RELAY
# 

# DBa nd CaACHE
docker compose   --env-file deploy.config.env   --env-file deploy.secrets.env up -d db cache

# MIGRATIONS
uv run alembic upgrade head

# User
uv run scripts/initial_setup.py 
uv run scripts/add_test_users.py


uv run python -m scripts.create_user admin
uv run python -m scripts.assign_roles admin --roles admin




# APp
uv run app.py

```


## Package Management

This project uses **uv** as the primary package manager for faster dependency installation and better virtual environment management. All commands in this documentation assume you're using uv unless otherwise specified.

### Installing uv

#### macOS and Linux
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Windows (PowerShell)
```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### Using pip
```bash
pip install uv
```

### Package Management with uv

#### Installing Dependencies
```bash
# Install all dependencies from requirements.txt
uv sync


```

#### Managing Dependencies
```bash
# Remove a package
uv remove package_name

# Update a package to latest version
uv add package_name@latest

# Update all packages
uv lock --upgrade
uv sync


# List installed packages
uv pip list

# Check for outdated packages
uv pip list --outdated

uv pip freeze > requirements.txt
```

#### Virtual Environment Management
```bash
# Create a new virtual environment
uv venv

# Create with specific Python version
uv venv --python 3.11

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run commands without activating
uv run python script.py
uv run flask run
```

## Development Guidelines

When adding features to the application, please follow the conventions outlined in [Development Conventions](docs/10-DEVELOP/CONVENTIONS.md) for consistency with the existing codebase. This document includes essential patterns for database operations, CSRF protection, datetime handling, logging, security practices, and more.


## Setup

```bash
git clone https://github.com/drguptavivek/fundus_img_xtract.git


```

### PYTHON PACKAGES SETUP

This project uses **uv** as the primary package manager for faster dependency installation and better virtual environment management.

#### Recommended Method: Using uv

```bash
# Install uv if you haven't already (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt

# Activate the virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

#### Alternative Method: Traditional pip

```bash
# Only if you prefer not to use uv
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

#### Common uv Commands

```bash
# Run commands in the virtual environment
uv run python app.py
```

### DATABASE SETUP AND FIRST USER CREATION

```bash
# Set up database using Alembic migrations
uv run alembic upgrade head

# Create initial user and assign roles
uv run python -m scripts.create_user
uv run python -m scripts.assign_roles admin --roles admin
```

## Database Reset

### Reverting Database to Empty State

If you need to reset your database to an empty state while using Alembic migrations:

#### Recommended Method: Using Alembic Downgrade
```bash
# Downgrade to base state (removes all tables)
uv run alembic downgrade base

# Verify you're at base state
uv run alembic current

# Upgrade back to latest if needed
uv run alembic upgrade head
```

#### Alternative Methods

**Method 2: Clear Data and Reset Alembic**
```bash
# Clear all data using existing script
uv run python scripts/clear_db.py

# Reset Alembic version tracking
uv run alembic stamp base
```

**Method 3: Complete Fresh Start (Development Only)**
```bash
# Delete database file (SQLite)
rm image_manager.db

# Recreate from migrations
uv run alembic upgrade head

# Run initial data setup
uv run python scripts/initial_setup.py
```

#### Recommended Workflow for Clean Reset
```bash
# 1. Backup first (optional but recommended)
uv run python scripts/backup_db.py

# 2. Downgrade to base
uv run alembic downgrade base

# 3. Upgrade back to latest
uv run alembic upgrade head

# 4. Run initial data setup
uv run python scripts/initial_setup.py
```

**Important Notes:**
- All methods will permanently delete your data
- Always backup before performing a reset
- The first method (`alembic downgrade base`) is recommended as it properly maintains migration history

## Running the Application

### Development Mode

For development with auto-reloading and debugging features:

```bash
# Run the application with Flask development server
uv run app.py

# Check which process is using port 5001
lsof -i :5001

# Stop the application if running in background
kill -9 PID
```

### Production Mode with Gunicorn (Recommended for Production)

For production deployment, use Gunicorn which provides better performance, stability, and process management.

#### Option 1: Using systemd Service (Recommended)

For production deployment, using systemd is the recommended approach for process management:

```bash
# Navigate to the systemd directory
cd systemd

# Run the installation script (requires sudo)
sudo ./install_service.sh
```

This will install and enable the application as a systemd service with:
- Automatic start on boot
- Automatic restart on failure
- Proper logging
- Security hardening

Service management commands:
```bash
# Start the service
sudo systemctl start fundus-img-xtract

# Stop the service
sudo systemctl stop fundus-img-xtract

# Restart the service
sudo systemctl restart fundus-img-xtract

# Check service status
sudo systemctl status fundus-img-xtract

# View real-time logs
sudo journalctl -u fundus-img-xtract -f
```

#### Option 2: Using Startup Script

For manual or testing deployment:

```bash
# Using the provided startup script
./run_with_gunicorn.sh

# Or run Gunicorn directly
uv run gunicorn -c gunicorn_config.py wsgi:application
```

#### Gunicorn Configuration

The application includes a comprehensive Gunicorn configuration in `gunicorn_config.py`. Customize settings by editing `deploy.config.env` (non-secret values) or `deploy.secrets.env` (secrets). Example entries:

```bash
# deploy.config.env
FLASK_ENV=production
GUNICORN_BIND=0.0.0.0:5001
GUNICORN_WORKERS=4
GUNICORN_TIMEOUT=120
GUNICORN_LOG_LEVEL=info

# deploy.secrets.env
FLASK_SECRET_KEY=your-very-secret-key-here
```

For detailed information about running with Gunicorn, see [Gunicorn Documentation](docs/10-DEVELOP/GUNICORN.md).

### Alternative Method: Traditional virtual environment

```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run the application
python app.py
```

## Documentation

### Project Overview
- [Project Summary](SUMMARY.md)
- [Project Details](docs/DETAILS.md)
- [Agent Guidelines](AGENTS.md)

### Core Documentation (`docs/`)
- [App Architecture](docs/app.md) - Updated with current implementation details
- [Database Models](docs/00-Core/models.md) - Updated with dual grading system models
- [Database ERD](docs/00-Core/ERD.md) - Entity Relationship Diagram with Mermaid syntax
- [Master Data Management](docs/00-Core/master_data.md) - Core diseases, hospitals, labs, and grading systems
- [Scoping Mechanisms](docs/03-Tasks/Scoping.md) - User-LabUnit and Slot-LabUnit based access control
- [Application Routes](docs/routes.md) - Comprehensive documentation for all application routes
- [Email System](docs/10-DEVELOP/Email.md) - Comprehensive email functionality documentation
- [Security](docs/10-DEVELOP/Security.md) -  authentication, authorization, and security features
- [JavaScript Guidance](docs/10-DEVELOP/JavaScript_Guidance.md) - Authentication, CSRF protection, file organization, and template integration
- [Logging System](docs/10-DEVELOP/logging.md) - Complete logging infrastructure with dedicated loggers, debug mode, and configuration
- [Gunicorn Deployment](docs/10-DEVELOP/GUNICORN.md) - Running the application with Gunicorn in production
- [Playwright Testing](docs/10-DEVELOP/playwright.md) - End-to-end testing setup, configuration, and best practices
- [Build Themes](docs/10-DEVELOP/BUILD_THEMES.md)

### Data Processing Workflows (`docs/01-Adding_Images/`)
- [ZIP Uploads](docs/01-Adding_Images/zip_uploads.md)
    - [Main Processing Pipeline](docs/main.md)
    - [PDF Processing](docs/01-Adding_Images/process_pdfs.md)
    - [OCR Extraction](docs/01-Adding_Images/ocr_extraction.md)
- [Direct Uploads](docs/01-Adding_Images/direct_uploads.md)
- [Pre-Graded Uploads](docs/01-Adding_Images/pre_graded.md)
- [Audit Workflows](docs/01-Adding_Images/audit.md)

### Image Management & Processing (`docs/01-Adding_Images/`)
- [Direct Image Editing](docs/01-Adding_Images/direct_uploads.md) - Image editing, batch operations, and quality assessment

### Report Verification Workflows
- [Verification Workflows Overview](docs/02-Verify-Anonymize/verification-workflows-overview.md) - Comprehensive documentation for DR, Glaucoma, and No-DR report verification workflows
  - [DR PDF Verification Details](docs/02-Verify-Anonymize/dr-verification-details.md) - Technical implementation of DR PDF verification
  - [Glaucoma PDF Verification Details](docs/02-Verify-Anonymize/glaucoma-verification-details.md) - Technical implementation of Glaucoma PDF verification
  - [No DR Report Verification Details](docs/02-Verify-Anonymize/no-dr-verification-details.md) - Technical implementation of No-DR fallback verification
  - [Image Anonymization Workflow](docs/02-Verify-Anonymize/image-anonymization-workflow.md) - Technical implementation of direct image anonymization and verification
  - [Proposed No-Glaucoma Workflow Solution](docs/02-Verify-Anonymize/proposed-noglaucoma-workflow.md) - Implementation plan for missing Glaucoma verification workflow

### Task Creation
- [Scoping](docs/03-Tasks/Scoping.md) - ABAC - Attribute-Based Access Control & RBAC for Uplaoding and HGrading  and access to app features
- [Task Creation Services](docs/03-Tasks/taskCreationServices.md)
- [Task Utilities](docs/10-DEVELOP/Utilities/utils_taskUtils.md) - Functions for retrieving and managing task information with proper scoping


### Grading System (`docs/04-Grade/`)
- [Dual Grading Workflow](docs/04-Grade/dual_grading.md) - Updated with current implementation details
- [Dual Grading Implementation Details](docs/04-Grade/dual_grading_flow.md) - Technical implementation guide
- [Dual Grading Utilities](docs/04-Grade/dual_grading_utils.md) - Comprehensive function documentation for dual grading
- [Grading Edge Cases](docs/04-Grade/edge_cases.md) - Edge case analysis and resolution status
- [Grading Errors](docs/04-Grade/errors.md) - Error handling in grading workflows
- [Grading Flow Diagram](docs/04-Grade/flowdiagram.md) - Visual representation of grading workflows
- [Module Integration Guide](docs/04-Grade/module_integration_guide.md) - Integration patterns for grading module

### Utilities (`docs/10-DEVELOP/Utilities/`)
- [Utilities Overview](docs/10-DEVELOP/Utilities/00-utility_locations.md) - Complete listing of all utility functions and modules
- [Utilities by Category](docs/10-DEVELOP/Utilities/01-overview_of_all_utils.md) - Categorization of utilities by functionality

#### Logging Utilities
- [Logging Key Steps](docs/10-DEVELOP/Logging_key_steps.md) - Key steps for implementing logging in the dual grading system

#### Authentication Utilities
- [Auth Utilities](docs/10-DEVELOP/Utilities/auth_utils.md) - Functions for time handling and IP address retrieval

#### Analytics Utilities
- [Analytics Encounter Utilities](docs/10-DEVELOP/Utilities/analytics_encounterUtils.md) - Functions for encounter analytics
- [Analytics Utilities](docs/10-DEVELOP/Utilities/analytics_utils.md) - General analytics functions

#### API Utilities
- [API User Utilities](docs/10-DEVELOP/Utilities/api_userUtils.md) - API endpoint utilities for user management

#### Dual Grading Utilities
- [Dual Grading Fetch Detail Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingFetchDetailUtils.md) - Functions for fetching grades and tasks with related data
- [Dual Grading Eligibility Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingEligibility.md) - Functions for checking grading eligibility
- [Dual Grading Consensus Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingConsensusUtils.md) - Functions for handling consensus in dual grading
- [Dual Grading Next Tasks Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingGetNextTasks.md) - Functions for getting the next eligible tasks
- [Dual Grading KPIs Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingKPIs.md) - Functions for tracking dual grading KPIs
- [Dual Grading Revision Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingRevisionUtils.md) - Functions for checking revision eligibility
- [Dual Grading Stuck Task Cleanup Utilities](docs/10-DEVELOP/Utilities/utils_dualGradingStuckTaskCleanup.md) - Functions for detecting and cleaning up stuck tasks

#### Email Utilities
- [Email Utilities](docs/10-DEVELOP/Utilities/utils_emails.md) - Functions for sending emails synchronously and asynchronously

#### File Utilities
- [File Utilities](docs/10-DEVELOP/Utilities/utils_fileUtils.md) - Functions for file operations, path validation, and security checks

#### Upload Eligibility Utilities
- [Upload Eligibility Utilities](docs/10-DEVELOP/Utilities/utils_upload_eligibility.md) - Functions for determining user upload eligibility

#### Master Data Utilities
- [Master Utilities](docs/10-DEVELOP/Utilities/utils_masterUtils.md) - Functions for retrieving core entities like diseases, hospitals, etc.

#### Image Search Utilities
- [Image Search Utilities](docs/10-DEVELOP/Utilities/utils_imageSearchUtil.md) - Functions for searching images with various filters

#### Task Utilities
- [Task Utilities](docs/10-DEVELOP/Utilities/utils_taskUtils.md) - Functions for managing tasks and related information

#### Job Utilities
- [Job Utilities](docs/10-DEVELOP/Utilities/utils_jobUtils.md) - Functions for handling job data, particularly for ZIP uploads

#### Image Serving Utilities
- [Image Serving Utilities](docs/10-DEVELOP/Utilities/utils_utilsImgServe.md) - Functions for serving various types of images and reports by UUID

#### Datetime Utilities
- [Datetime Filters](docs/10-DEVELOP/Utilities/utils_datetime_filters.md) - Jinja filters for timezone-aware datetime rendering
- [Timezone Choices](docs/10-DEVELOP/Utilities/utils_timezone_choices.md) - Helpers for timezone selection with human-readable labels

#### Error Handling Utilities
- [Stack Trace Handler](docs/10-DEVELOP/Utilities/utils_stack_trace_handler.md) - Functions for capturing and logging stack traces

#### General Utilities
- [General Utilities](docs/10-DEVELOP/Utilities/utils_utils.md) - General utility functions for database sessions and access control
- [Additional Utilities](docs/10-DEVELOP/Utilities/utils_utils2.md) - Miscellaneous helper functions for file handling, data validation, and general operations


### Development & Conventions
- [Development Conventions](docs/10-DEVELOP/CONVENTIONS.md) - Essential patterns for database, CSRF, datetime, logging, and more

  - [Database Context Manager](docs/10-DEVELOP/DB CONTEXT MANAGER.md)
  - [DateTime Handling](docs/10-DEVELOP/DateTime.md)

### Frontend Components (`static/`)
- [Flash Toasts Component](static/js/flash-toasts.md)

### Module-Specific Documentation
- [Analytics Utils](docs/10-DEVELOP/Utilities/analytics_utils.md) - Functions for encounter analytics and data processing
- [Services Task Creation](docs/03-Tasks/taskCreationServices.md) - Task creation services and related functionality

### Scripts & Migrations (`scripts/`)
- [User Management Scripts](scripts/USERS.md) - User creation and management
- [Alembic Database Migrations](docs/alembic-migrations.md) - Database schema migrations using Alembic
- [Script Migrations](scripts/migrations.md) - Database migration scripts

## Application Workflow Flowchart

```mermaid
flowchart TD
    subgraph Ingestion & Initial Processing
        A[ZIP Upload] --> B[Extract Files - Images & PDFs];
        B --> C[Validate & MD5 Hash];
        C --> D1[Assign UUIDs to Images];
        C --> D2[Assign UUIDs to PDFs];

        E[Direct Image Upload] --> F[Assign UUID & Metadata];
    end

    subgraph Processing & Anonymization
        D1 --> G[Image Anonymization];
        F --> G;

        D2 --> H[Process PDFs - OCR & Data Extraction];
        H --> I[Store OCR Data in DB & Assign UUIDs to Reports];
    end

    subgraph Image Management & Editing
        G --> J1[Direct Image Editing];
        J1 --> J2[Batch Operations];
        J2 --> J3[Quality Assessment];
        J3 --> J4[Metadata Management];
    end

    subgraph Report Verification
        I --> K1[DR Report Verification];
        I --> K2[Glaucoma Report Verification];
        K1 --> K3[Data Validation & Laterality Assignment];
        K2 --> K4[Data Cleaning & Clinical Validation];
        J4 --> K3;
        J4 --> K4;
    end

    subgraph Task Creation & Assignment
        K3 --> L[Create Grading Tasks per Disease];
        K4 --> L;
        L --> M[Assign Tasks Based on User Roles & Lab Units];
        M --> N[Task Queue Management];
    end

    subgraph Dual Grading System
        N --> O[Resident Grading];
        O --> P[Resident2 Grading];
        P --> Q{Consensus Required?};
        Q -->|Yes| R[Arbitrator Review];
        Q -->|No| S[Final Grade Established];
        R --> S;
    end

    subgraph Quality Control & AI Integration
        S --> T[Quality Assurance Checks];
        T --> U[AI Model Comparison];
        U --> V[Dataset Ready for Training/Validation];
    end

    style A fill:#f9f,stroke:#333,stroke-width:2px;
    style E fill:#f9f,stroke:#333,stroke-width:2px;
    style V fill:#bbf,stroke:#333,stroke-width:2px;
    style Q fill:#ff9,stroke:#333,stroke-width:2px;
```

## API Documentation

The application provides comprehensive RESTful API endpoints with detailed documentation including:
- Endpoint URLs and HTTP methods
- Required authentication and authorization
- Request parameters
- Response formats
- Error codes

The API follows OpenAPI 3.0 standards with machine-readable specifications available for:
- Swagger UI for interactive API documentation
- Code generation tools to create client SDKs
- API testing tools
- Documentation generators

### ⚠️ Documentation Status Notice
Many documentation files appear to be stale and don't reflect the current state of the application. The app has evolved significantly with:
- New blueprints (notifications, tasks, dashboard, api, docs)
- Dual grading system replacing single grading
- Updated logging system with dedicated loggers
- Enhanced security features (Security.md has been updated)
- New database models and relationships

Please review individual documentation files for accuracy before relying on them.

## GIT Workflow

```bash
git init
git add README.md
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/drguptavivek/fundus_img_xtract.git
git push -u origin main
git branch --set-upstream-to=origin/main main

git add . && git commit -a -m "The commit message"
git push -u origin main
```
