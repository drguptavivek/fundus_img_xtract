# Fundus Image Manager

A comprehensive system for an eye hospital to manage eye images. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD). Has specific workflows for Remedio FOP zip files that get downlaoded from the remedio dashboard

## Development Guidelines

When adding features to the application, please follow the conventions outlined in [Development Conventions](CONVENTIONS.md) for consistency with the existing codebase. This document includes essential patterns for database operations, CSRF protection, datetime handling, logging, security practices, and more.

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
- [Project Details](docs/DETAILS.md)
- [Agent Guidelines](AGENTS.md)

### Core Documentation (`docs/`)
- [App Architecture](docs/app.md) - Updated with current implementation details
- [Database Models](docs/00-Core/models.md) - Updated with dual grading system models
- [Database ERD](docs/00-Core/ERD.md) - Entity Relationship Diagram with Mermaid syntax
- [Master Data Management](docs/00-Core/master_data.md) - Core diseases, hospitals, labs, and grading systems
- [Scoping Mechanisms](docs/03-Tasks/Scoping.md) - User-LabUnit and Slot-LabUnit based access control
- [API Documentation](docs/Utilities/api.md)
- [Application Routes](docs/routes.md) - Comprehensive documentation for all application routes
- [Email System](docs/10-DEVELOP/Email.md) - Comprehensive email functionality documentation
- [Common Utilities](docs/Utilities/CommonUtils.md) - Core utility functions and reusable components
- [Security](docs/10-DEVELOP/Security.md) - Comprehensive authentication, authorization, and security features
- [JavaScript Guidance](docs/10-DEVELOP/JavaScript_Guidance.md) - Authentication, CSRF protection, file organization, and template integration
- [Logging System](docs/10-DEVELOP/logging.md) - Complete logging infrastructure with dedicated loggers, debug mode, and configuration
- [Playwright Testing](docs/10-DEVELOP/playwright.md) - End-to-end testing setup, configuration, and best practices
- [Build Themes](docs/10-DEVELOP/BUILD_THEMES.md)

### Data Processing Workflows (`docs/01-Adding_Images/`)
- [ZIP Uploads](docs/01-Adding_Images/zip_uploads.md)
    - [Main Processing Pipeline](docs/main.md)
    - [PDF Processing](docs/01-Adding_Images/process_pdfs.md)
    - [OCR Extraction](docs/01-Adding_Images/ocr_extraction.md)
- [Direct Uploads](docs/01-Adding_Images/direct_uploads.md)
- [Audit Workflows](docs/01-Adding_Images/audit.md)

### Image Management & Processing (`docs/01-Adding_Images/`)
- [Direct Image Editing](docs/01-Adding_Images/direct_uploads.md) - Image editing, batch operations, and quality assessment

### Report Verification Workflows
- Report verification documentation is being reorganized

### Task Creation
- [Scoping](docs/03-Tasks/Scoping.md)
- [Task Creation Services](docs/03-Tasks/taskCreationServices.md)
- [Task Utilities](docs/Utilities/taskUtils.md) - Functions for retrieving and managing task information with proper scoping


### Grading System (`docs/04-Grade/`)
- [Dual Grading Workflow](docs/04-Grade/dual_grading.md) - Updated with current implementation details
- [Dual Grading Implementation Details](docs/04-Grade/dual_grading_flow.md) - Technical implementation guide
- [Dual Grading Utilities](docs/04-Grade/dual_grading_utils.md) - Comprehensive function documentation for dual grading
- [Grading Edge Cases](docs/04-Grade/edge_cases.md) - Edge case analysis and resolution status
- [Grading Errors](docs/04-Grade/errors.md) - Error handling in grading workflows
- [Grading Flow Diagram](docs/04-Grade/flowdiagram.md) - Visual representation of grading workflows
- [Module Integration Guide](docs/04-Grade/module_integration_guide.md) - Integration patterns for grading module

### Utilities (`docs/Utilities/`)
- [API Documentation](docs/Utilities/api.md)
- [Common Utilities](docs/Utilities/CommonUtils.md)
- [Image Search Utilities](docs/Utilities/imageSearchUtils.md)
- [Task Utilities](docs/Utilities/taskUtils.md)
- [Utilities README](docs/Utilities/utils2.md)


### Development & Conventions
- [Development Conventions](docs/10-DEVELOP/CONVENTIONS.md) - Essential patterns for database, CSRF, datetime, logging, and more
  - [Logging Conventions](docs/10-DEVELOP/Logging12.md) - Implementation patterns and conventions
  - [Database Context Manager](docs/10-DEVELOP/DB%20CONTEXT%20MANAGER.md)
  - [DateTime Handling](docs/10-DEVELOP/DateTime.md)

### Frontend Components (`static/`)
- [Flash Toasts Component](static/js/flash-toasts.md)

### Module-Specific Documentation
- [Analytics Utils](analytics/utils.md)
- [Services Task Creation](services/taskCreationServices.md)

### Scripts & Migrations (`scripts/`)
- [User Management Scripts](scripts/USERS.md) - User creation and management
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
        O --> P[Faculty Grading];
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
