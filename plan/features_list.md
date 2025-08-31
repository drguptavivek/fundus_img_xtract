# Features List

This document outlines the key features of the Fundus Image Manager application.

## 1. Core System & Data Processing

- **Data Ingestion**: Handles various sources, including:
  - ZIP archives from mobile fundus cameras (e.g., Remedio FOP).
  - Standalone `.jpg` or `.jpeg` images from clinics.
- **Automated Processing Pipeline**:
  - Extracts contents from ZIP files (images, PDFs).
  - Performs Optical Character Recognition (OCR) on PDFs to extract structured medical data.
  - Splits multi-page PDFs into single-page reports for DR and Glaucoma.
- **Data Integrity & Traceability**:
  - **Deduplication**: Generates MD5 hashes of uploaded ZIP files to prevent processing duplicates.
  - **Unique Identification**: Assigns a unique UUID to every file (images, original PDFs, processed report PDFs) to ensure stable referencing.
  - **Preservation**: Original uploaded files are preserved for traceability.
- **Security**:
  - Validates uploads for malicious files (disallowed extensions, path traversal, content-type mismatches).
  - Logs and flags malicious upload attempts for admin review.

## 2. User & Access Management

- **Authentication**: Standard user login and logout system.
- **Role-Based Access Control (RBAC)**:
  - Predefined roles: `admin`, `fileUploader`, `ophthalmologist`, `data_manager`.
  - Route protection ensures only authorized users can access specific features.
- **User Account Management**:
  - Users can self-manage their profile information.
  - Users can change their own password.
- **Admin Controls**:
  - Full control over user lifecycle: create, edit, and assign/revoke roles.
  - Ability to reset any user's password.
  - View a log of malicious upload attempts.

## 3. Data Management & Workflows

- **File Upload & Job Processing**:
  - Web interface for authorized users to upload ZIP files.
  - Handles filename collisions to prevent overwriting existing files.
  - Queues uploads for reliable background processing.
  - **Job Monitoring**: Admins can monitor the real-time status of processing jobs and review details and errors for each file.
- **Patient Encounter Review (`/screenings`)**:
  - A searchable, paginated list of all patient encounters.
  - Detailed view for each encounter, showing all associated images and reports.
  - **Note**: Patient-identifying information is visible on these screens and access is restricted.
- **Manual Data Verification (Glaucoma)**:
  - A dedicated workflow to review and verify data extracted via OCR.
  - Users can filter encounters by verification status (verified/unverified).
  - **Verification Interface**:
    - Edit and correct extracted data (e.g., VCDR values).
    - Tag the laterality of each image (`right` eye, `left` eye, `cannot_tell`).
    - Mark the entire encounter as "verified" (action is blocked until all images are tagged).
- **Data Auditing & Cleaning**:
  - **Automated Cleaning**: A workflow to standardize raw, text-based OCR results into a clean, numeric format for analysis.
  - **Audit Reports**: Identifies and lists encounters with missing critical data (e.g., capture date) for correction.
- **Analytics Dashboard (Glaucoma)**:
  - Displays aggregate statistics on cleaned glaucoma data.
  - Visualizes the distribution of VCDR values for right and left eyes using histograms.
  - **Note**: Patient data is masked on this screen.

## 4. Clinical Grading

- **Confidentiality & Masking**:
  - **Patient Anonymity**: The grading interface is fully masked, withholding all patient-identifying information from the grader.
  - **Grader Independence**: Graders can only see their own assessments, preventing bias from other graders' opinions.
- **Grading Dashboard**:
  - Central hub for grading activity.
  - Displays system-wide KPIs (total gradings, unique images graded, breakdown by impression).
  - "Start Grading" button intelligently directs the user to a random, recent, ungraded image.
  - Allows users to look up an image by UUID and review their own grading history.
- **Glaucoma & DR Grading Interface**:
  - **Advanced Image Viewer**: Features controls for zoom, fullscreen, brightness, contrast, and color channel filters (R, G, B, Y, H) with keyboard navigation.
  - **Efficient Form**: Uses large, clickable buttons for selecting clinical impressions.
  - **"Not Gradable" Reasons**: Provides a standardized list of reasons (e.g., "Disc not focussed", "Artefacts") that can be quickly added to remarks.
  - **Workflow Buttons**: "Save & Next" and "Save & Close" to streamline the grading of multiple images.
- **Saving Grades**:
  - The system uses an "upsert" logic, saving only the most recent grade for each user per image.
  - A user's previous grade for an image is overwritten if they re-grade it.
  - **Limitation**: Because only one grade is stored per user/image, intra-rater reliability cannot currently be assessed.

## 5. File Serving

- **Secure Access**: Serves images and PDF reports securely.
- **Flexible Retrieval**: Files can be accessed either by their original filename or by their stable, unique UUID.

## 6. To-Be-Developed / Future Features
- **Direct Image Upload**: A process to upload images directly for glaucoam images, dr images, amd images, cornea images. 
- **DR Data Verification**: A manual verification workflow for Diabetic Retinopathy reports.
- **Grading Arbitration**: A process to establish a final, consensus grade for an image when multiple graders disagree.
- **Intra-Rater Reliability**: A system to allow for and assess sampled re-grading by the same specialist. This requires a data model change to store multiple grading instances per user/image.
- **Inter-Rater Agreement Analysis**: Tools to compare and analyze the consistency of grades between different specialists.
- **External AI Integration**: A process to send images to an external AI grading API and store the results.

