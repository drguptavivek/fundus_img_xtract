# Fundus Image Manager


##  Technical Details

- **Backend:** Python, Flask
- **Database:** SQLAlchemy (ORM)
- **Frontend:** Jinja2 Templates, Vanilla JavaScript, Bootstrap 5.3 via SASS
- **Key Libraries:** Pytesseract (OCR), Pandas, Numpys
- **Dependency Management:** uv
- **Environment:**  .env and .env.example


##  Common Commands
### Development
- `.venv\bin\activate` or `.venv\Scripts\activate` - Activate the virtual environment
- `python3 app.py` - Run the application 
- `uv pip install` - Install dependencies with uv
- `npn run build:css` - Build Theme 


## CODING PROTOCOL ##
**Coding Instructions**
- First understand the request and ask clarifying questions
- Explain your approach step-by-step before writing any code.
- No unrelated edits - focus on just the task you're on
- Follow PEP 8 style guidelines
- Apply PEP 484 type annotations
- Follow Python's Zen (import this)
- Proper memory management
- always close db sessions
- Choose efficent query loading
- Use proper dependency injection
- Implement proper request validation
- Implement efficient response handling
- Implement proper error handling and exceptions
- Build Logic First, then build front-end template. 
- Use Secure Coding practices
- Ensure CSRF protection in all forms  @templates/_forms.html   
- Enusre SQL Injection 
- Add allowed roles for each route
- No sweeping changes
- Commit small, frequent changes for readable diffs
- Use explicit error handling, no unwraps in production code
- Use Success and error Loggers from create_app  in @app.py 
- Use Flash toasts for user feedback
- Use avaibale styles only as much as possible
- Keep code modular using blueprints
- Include docstrings 
- Organize templates in sub-folders
- Ensure no data is lost.
- Give migration scipts in @scrips/folder. 
- Udpate @scripts/setup_db.py when models change as needed
- Update @scripts/migrations.md with instructions


## 1. Project Overview

This project is a comprehensive system for an eye hospital to manage retinal fundus images. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD). The system is designed to handle the entire lifecycle of image data, from initial upload to final clinical grading.

### 1.1. Key Objectives

- **Data Ingestion**: Manage ZIP archives from mobile fundus cameras and standalone `.jpg` or `.jpeg` images from various clinics.
- **Processing & Anonymization**: Ingest, clean, and anonymize image data while preserving original files for traceability.
- **Automated & Manual Verification**: Perform automated data cleaning and provide interfaces for manual data verification and editing by authorized personnel.
- **Masked Clinical Grading**: Implement a system for independent, masked grading of images by specialists to prevent bias.
- **Workflow & Analysis**: Establish workflows for grading arbitration, assessing inter-rater and intra-rater reliability, and integrating with external AI grading APIs.

## 2. System Architecture & Workflows

### 2.1. Core Logic & Standalone Scripts

- **`main.py`**: The primary data processing pipeline that handles ZIP file extraction, validation against malicious files, MD5 hashing to prevent duplicate uploads, and the assignment of a unique UUID to every extracted image and original PDF.
  - [Documentation](docs/main.md)
- **`process_pdfs.py` & `ocr_extraction.py`**: These scripts perform Optical Character Recognition (OCR) on extracted PDFs to pull key medical data, which is then stored in the database. A unique UUID is also automatically assigned to the resulting single-page report records.
  - [Documentation for process_pdfs](docs/process_pdfs.md) and [ocr_extraction](docs/ocr_extraction.md)

### 2.2. Flask Web Application

The application is built using Flask and is organized into modular blueprints, each handling a distinct set of features.

- **`app.py`**: The application factory. It initializes configuration, logging, the database schema, and registers all blueprints.
  - [Documentation](docs/app.md)
- **`models.py`**: Defines the complete database schema using SQLAlchemy ORM.
  - [Documentation](docs/models.md)

#### 2.2.1. Key Application Workflows

- **User Management (`/auth`, `/account`, `/admin`)**: A comprehensive system for user authentication, self-service profile management, and powerful administrative control over user creation, role assignment, and permissions.

- **File Uploading & Processing (`/uploads`, `/jobs`)**: A robust workflow for uploading ZIP files. The system validates files, prevents overwrites, and queues a background job for processing. The `/jobs` blueprint allows admins to monitor the real-time status of these tasks and review any errors or malicious upload attempts.

- **File Serving (`/media`, `/reports`)**: Securely serves images and PDF reports. Files can be fetched by their filename or, for stable access, by their unique UUID.

- **Data Auditing & Cleaning (`/audit`, `/glaucoma`)**: Provides tools for data quality assurance. This includes a report for encounters missing a capture date (`audit.missing_capture_date`) and a workflow for cleaning and standardizing raw OCR data into a numeric format suitable for analysis (`glaucoma.glaucoma_clean_workflow`).

- **Patient Encounter Review (`/screenings`)**: The main interface for browsing patient data. It offers a searchable, paginated list of all encounters. The detail view displays all images and reports for an encounter. **Note: Patient-identifying information is visible on these screens, and access must be strictly controlled.**

- **Manual Data Verification (`/glaucoma`)**: A workflow for clinical staff to verify the accuracy of extracted OCR data. Users can correct data, tag the laterality (left/right eye) of each image, and mark the encounter as "verified" only after all images have been tagged.

- **Clinical Image Grading (`/grading`)**: This blueprint provides the interface for masked clinical grading of images for DR and Glaucoma.
    - **Dashboard**: The grading dashboard offers statistics on grading activity and a "Start Grading" button that directs the user to a random, recent, ungraded image to ensure an efficient workflow.
    - **Confidentiality**: The grading process is fully masked. Graders cannot see patient-identifying information, nor can they see the grades submitted by other users, ensuring unbiased, independent assessments.
    - **Grading Interface**: The grading screen features an advanced image viewer with controls for zoom, brightness, and color filters. The user submits their assessment by selecting from a predefined list of clinical impressions.
    - **Saving Grades**: The system uses an "upsert" logic, saving only the most recent grade for each user per image. **Therefore, intra-rater agreement cannot be assessed with the current implementation.**
