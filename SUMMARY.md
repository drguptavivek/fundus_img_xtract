# Fundus Image Manager

## Abbreviations

- DR: Diabetic Retinopathy
- AI: Artificial Intelligence
- API: Application Programming Interface
- AMD: Age-related Macular Degeneration
- FOP: Fundus on Phone

## Project Overview

This project is a system for an eye hospital to manage retinal fundus images and generate datasets of retinal images that can be used for AI training and validation of models targeted at Glaucoma, DR, and AMD.

### Project Objectives

- Manage ZIP files from the Remedio FOP camera (containing patient information, images, and PDF reports of AI-generated screening results).
- Manage standalone JPG/JPEG retinal images uploaded by various clinics and labs.
- Ingest, clean, and anonymize data and images, with an emphasis on preserving original files while creating a framework for extended information.
- Perform automated data cleaning based on rules for dates, values, etc.
- Allow for manual verification and editing of data by Data Managers and Optometrists, including assessing image quality and validating extracted PDF data.
- Implement a system for independent, masked grading of images by consultants and fellows specializing in Glaucoma, DR, and AMD.
- Establish an arbitration process to determine a final grade for each image for each target disease.
- Create a process for sampled re-grading to assess intra-rater reliability.
- Develop a process to send images to an external API for grading and save the results.
- Assess inter-rater and intra-rater agreement, as well as agreement between the Remedio AI and the final grade.

### Progress So Far

#### Standalone Scripts & Core Logic

- **`main.py`**: This script is the primary data processing pipeline for extracting and analyzing medical reports from ZIP files. It handles the ingestion of multiple ZIP files, extracts their contents (PDFs and images), and performs initial validation.
  - It checks for disallowed file types, path traversal, and content-type mismatches to prevent malicious uploads.
  - It calculates an MD5 hash of each ZIP file to detect and skip the processing of duplicate uploads.
  - It assigns a unique UUID to every extracted image and original PDF, creating an `EncounterFile` record for each in the database.
  - [Documentation](docs/main.md)

- **`process_pdfs.py` & `ocr_extraction.py`**: These scripts perform Optical Character Recognition (OCR) on the extracted PDFs to pull key medical data points. The extracted information is then stored in the database.
  - A unique UUID is also automatically assigned to the single-page, split-off reports for Diabetic Retinopathy and Glaucoma when their records are created in the database.
  - [Documentation for process_pdfs](docs/process_pdfs.md) and [ocr_extraction](docs/ocr_extraction.md)

#### Flask Application

- **`app.py`**: This is the application factory and entry-point for the Flask app. It initializes all configuration, the environment, logging, the database schema, a thread pool for background tasks, and registers all application blueprints. It also provides security features and protected routes.
  - [Documentation](docs/app.md)

- **`models.py`**: Defines the database schema using SQLAlchemy ORM, managing all data from ingestion to analysis and grading.
  - [Documentation](docs/models.md)

##### Login, Users, and Roles
The application features a comprehensive user and role management system across three blueprints: `/auth`, `/account`, and `/admin`. The `/auth` blueprint handles core security, login/logout, and defines roles like "admin", "fileUploader", "ophthalmologist", and "data_manager". The `/account` blueprint provides self-service profile and password management for users. The `/admin` blueprint gives administrators full control over user creation, role assignment, and profile editing. Route access is protected using a `@roles_required()` decorator.

##### File Uploading & Processing
The `/uploads` blueprint manages the entire file ingestion workflow, allowing authorized users to upload ZIP files. The system validates files, prevents overwrites by creating unique filenames, and records metadata about the upload. It then creates a `Job` in the database and queues it for background processing. The `/jobs` blueprint allows administrators to monitor the status of these background tasks, showing which files have completed, failed, or are still processing. Malicious upload attempts are logged and can be reviewed by an admin at the `/admin/malicious-uploads` endpoint.

##### Serving Images and PDFs
The `/media` and `/reports` blueprints handle securely serving files. Routes allow for fetching images and original PDFs by filename or by their stable UUID. The reports blueprint is dedicated to serving the split-off, single-page PDF reports for DR and Glaucoma, which can also be accessed by their filename or UUID.

##### Automated Data Audits
The application includes endpoints for data quality assurance. `audit.missing_capture_date` lists all patient encounters that are missing a valid capture date, allowing admins to correct them. `glaucoma.glaucoma_clean_workflow` is a tool for admins to process raw OCR text into a clean, standardized, and numeric format suitable for analysis.

##### Viewing and Searching Patient Encounters
The `/screenings` blueprint is the main interface for browsing patient data. It provides a searchable, paginated list of all encounters. From this list, users can click to see a detailed view of a single encounter, which includes a gallery of all associated images and links to reports. **Note: Patient details are NOT masked on these screens, and access should be restricted to authorized personnel.**

##### Manual Data Verification (Glaucoma)
From the "Glaucoma > Verify" menu, users can access the glaucoma data verification workflow. The `glaucoma.list` endpoint shows a list of reports, which can be filtered by verification status. The `glaucoma.edit` page is the core of this workflow, where users can correct OCR data, tag the laterality (left/right eye) of each image, and finally mark the entire encounter as "verified" once all data is confirmed and all images are tagged.

- **Data Storage**:
  1.  **Laterality**: Saved in the `eye_side` column of the `EncounterFile` table.
  2.  **Verification Status**: Stored in the `PatientEncounters` table with the verifier's username and a timestamp.
  3.  **Cleaned Data**: Stored in the `GlaucomaResultsCleaned` table.
  4.  **Original Data**: The raw OCR text is preserved in the `GlaucomaReport` and `DiabeticRetinopathyReport` tables for traceability.

##### Manual Data Verification (Diabetic Retinopathy)
*To Be Developed.*

##### Image Grading (Glaucoma & DR)
The `/grading` blueprint provides the interface for clinical grading of images.

- **Dashboard (`/grading/`)**: The grading dashboard provides statistics on grading activity, such as total gradings and a breakdown by clinical impression. It features a "Start Grading" button that randomly selects one of the 50 most recent images that the current user has not yet graded. Users can also look up an image by UUID or review their own grading history.

- **Confidentiality**: The grading process is designed to be confidential.
    1.  **Patient Masking**: The grading screen withholds all patient-identifying information from the grader.
    2.  **Grader Independence**: A grader can only see their own prior assessment for an image, not the grades of others, ensuring unbiased evaluation.

- **Grading Interface (`/grading/glaucoma/image/<uuid>`)**: This screen displays the image in an advanced viewer with controls for zoom, brightness, contrast, and color filters. The grader selects a clinical impression from a list of buttons. If "Not gradable" is chosen, a list of reasons appears ("Disc not focussed", "Retina not focussed", "Disc not complete", "Artefacts", "Other").

- **Saving Grades**: When a grade is submitted, the system uses an "upsert" logic, updating the user's existing grade for that image or creating a new one if it's their first time. **This means only the most recent grade from a user for a specific image is stored, and therefore, intra-rater agreement cannot currently be assessed.**

### Core Technologies

*   **Backend:** Python
*   **Web Framework:** Flask, Jinja2
*   **Database:** SQLAlchemy (ORM)
*   **Data Analysis:** Pandas, Numpy, Matplotlib
*   **Styling:** Bootstrap 5.3, SASS
*   **JS:** Client-side vanilla JavaScript.
*   **OCR:** Pytesseract
*   **Dependency Management:** uv

### Development Conventions

*   **Configuration:** Uses a `.env` file.
*   **Database:** Models are defined in `models.py`.
*   **Modular Design:** The application is organized into Blueprints with distinct responsibilities.
*   **Logging:** Generates log files in the `logs/` directory.
