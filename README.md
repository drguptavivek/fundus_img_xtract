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
- [Project Details](DETAILS.md)
- [Agent Guidelines](AGENTS.md)

### Core Documentation
- [App Architecture](docs/app.md) - Updated with current implementation details
- [Database Models](docs/models.md) - Updated with dual grading system models
- [Database ERD](docs/ERD.md) - Entity Relationship Diagram with Mermaid syntax
- [Master Data Management](docs/master_data.md) - Core diseases, hospitals, labs, and grading systems
- [Scoping Mechanisms](docs/Scoping.md) - User-LabUnit and Slot-LabUnit based access control
- [API Documentation](docs/api.md)
- [Application Routes](docs/routes.md) - Comprehensive documentation for all application routes
- [Email System](docs/Email.md) - Comprehensive email functionality documentation

### Data Processing Workflows
- [ZIP Uploads](docs/zip_uploads.md)
    - [Main Processing Pipeline](docs/main.md)
    - [PDF Processing](docs/process_pdfs.md)
    - [OCR Extraction](docs/ocr_extraction.md)
- [Direct Uploads](docs/direct_uploads.md)
- [Audit Workflows](docs/audit.md)

### Image Management & Processing
- [Direct Image Editing](docs/direct_image_editing.md) - Image editing, batch operations, and quality assessment
- [Anonymization](docs/anonymization.md) - Patient data anonymization and audit trails

### Report Verification Workflows
- [DR Report Verification](docs/dr_report_verification.md) - Diabetic Retinopathy report verification system
- [Glaucoma Report Verification](docs/glaucoma_report_verification.md) - Glaucoma report verification system

### Task Creation
- - [Automatic Task Creation Services](docs/task_creation_services.md)

### Grading System
- [Dual Grading Workflow](docs/dual_grading.md) - Updated with current implementation details
- [Dual Grading Implementation Details](grading/dual_grading_flow.md) - Technical implementation guide
- [Dual Grading Utilities](grading/dual_grading_utils.md) - Comprehensive function documentation for dual grading
- [Grading Edge Cases](grading/edge_cases.md) - Edge case analysis and resolution status
- [Grading Errors](grading/errors.md) - Error handling in grading workflows
- [Grading Flow Diagram](grading/flowdiagram.md) - Visual representation of grading workflows
- [Module Integration Guide](grading/module_integration_guide.md) - Integration patterns for grading module

### Search & Utilities
- [Common Utilities](docs/CommonUtils.md) - Core utility functions and reusable components used throughout the application
- [Task Utilities](utils/taskUtils.md) - Functions for retrieving and managing task information with proper scoping
- [Flash Toasts Component](static/js/flash-toasts.md)
- [Upload Eligibility](utils/upload_eligibility.py) - User upload permission checking
- [Dual Grading Eligibility](utils/dualGradingEligibility.py) - Grading permission validation
- [Master Data Utilities](utils/masterUtils.py) - Core entities retrieval functions

### Development & Conventions
- [Development Conventions](CONVENTIONS.md) - Essential patterns for database, CSRF, datetime, logging, and more
  - [Logging Conventions](CONVENTIONS/Logging.md) - Implementation patterns and conventions
- [Security](docs/Security.md) - Comprehensive authentication, authorization, and security features
- [JavaScript Guidance](docs/JavaScript_Guidance.md) - Authentication, CSRF protection, file organization, and template integration
- [Logging System](docs/logging.md) - Complete logging infrastructure with dedicated loggers, debug mode, and configuration
- [Playwright Testing](docs/playwright.md) - End-to-end testing setup, configuration, and best practices
- [Build Themes](docs/BUILD_THEMES.md)
- [Database Context Manager](CONVENTIONS/DB%20CONTEXT%20MANAGER.md)
- [DateTime Handling](CONVENTIONS/DateTime.md)
- [User Management Scripts](scripts/USERS.md)
- [Script Migrations](scripts/migrations.md)

### Module-Specific Documentation
- [Analytics Utils](analytics/utils.md)
- [Services Task Creation](services/taskCreationServices.md)
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