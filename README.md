# Fundus Image Manager

A comprehensive system for an eye hospital to manage eye images. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD). Has specific workflows for Remedio FOP zip files that get downlaoded from the remedio dashboard

## Setup

```bash
git clone https://github.com/drguptavivek/fundus_img_xtract.git

# Install NPM packages and create directories
python3 setup_env_and_npm.py 
python setup_env_and_npm.py 
```

### PYTHON PACKAGES SETUP

```bash
# Create venv in .venv and install packages listed in uv.lock
uv init
uv add -r requirements.txt

# OR if you do not prefer / have uv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### DATABASE SETUP AND FIRST USER CREATION


```bash
# Activate virtual environment

source .venv/bin/activate

# Set up database
python -m scripts.setup_db

# Create initial user and assign roles
python -m scripts.create_user
python -m scripts.assign_roles admin --roles admin


```

## Running the Application

```bash
uv run app.py

# OR if you do not prefer / have uv
source .venv/bin/activate
source .venv/Scripts/activate
python app.py


```

## Documentation

### Project Overview
- [Project Summary](SUMMARY.md)
- [Project Details](DETAILS.md)
- [Agent Guidelines](AGENTS.md)

### Core Documentation
- [App Architecture](docs/app.md)
- [Database Models](docs/models.md)
- [API Documentation](docs/api.md)
- [Application Routes](docs/routes.md)

### Data Processing Workflows
- [ZIP Uploads](docs/zip_uploads.md)
    - [Main Processing Pipeline](docs/main.md)
    - [PDF Processing](docs/process_pdfs.md)
    - [OCR Extraction](docs/ocr_extraction.md)
- [Direct Uploads](docs/direct_uploads.md)
- [Audit Workflows](docs/audit.md)

### Grading System
- [Grading System Overview](docs/Grading.md)
    - [Dual Grading Workflow](docs/dual_grading.md)
    - [Dual Grading Flow Details](grading/dual_grading_flow.md)
    - [Task Creation Services](docs/task_creation_services.md)
    - [Grading Edge Cases](grading/edge_cases.md)

### Search & Utilities
- [Image Search](search/route_image_search.md)
- [Task Utilities](utils/taskUtils.md)
- [Flash Toasts Component](static/js/flash-toasts.md)

### Development & Conventions
- [Security](docs/Security.md)
- [Build Themes](docs/BUILD_THEMES.md)
- [Coding Conventions](CONVENTIONS/Templates.md)
- [Database Context Manager](CONVENTIONS/DB%20CONTEXT%20MANAGER.md)
- [DateTime Handling](CONVENTIONS/DateTime.md)
- [Logging System](CONVENTIONS/Logging.md)
- [User Management Scripts](scripts/USERS.md)
- [Script Migrations](scripts/migrations.md)

### Module-Specific Documentation
- [Analytics Routes](analytics/routes.md)
- [Analytics Utils](analytics/utils.md)
- [Tasks Routes](tasks/routes.md)
- [Services Task Creation](services/taskCreationServices.md)

### Documentation Index
- [Full Documentation Index](docs/README.md)

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