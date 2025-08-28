1## GEMINI.md

### Project Overview

This project is a Python-based data processing pipeline designed to extract and analyze medical reports from zip files. The primary focus is on processing PDF reports containing fundus imagery for Diabetic Retinopathy and Glaucoma screenings.

The workflow begins by ingesting zip files, extracting their contents (PDFs and images), and then performing Optical Character Recognition (OCR) on the PDFs to extract key medical data points. The extracted information is then stored in a structured database. 

The project also includes a web application component built with **Flask**, which provides an interface for uploading files, monitoring processing status, and viewing the extracted results.

### Core Technologies

*   **Backend:** Python
*   **Web Framework:** Flask
*   **Database:** SQLAlchemy (ORM)
*   **PDF Processing:** PyMuPDF (fitz)
*   **OCR:** Pytesseract
*   **Dependency Management:** uv

### Building and Running

1.  **Installation:**
    *   Clone the repository.
    *   Install dependencies using `uv sync`.

2.  **Initialization:**
    *   To set up the necessary directories and create an empty database, run:
        ```bash
        python initialize.py
        ```

3.  **Execution:**
    *   The main processing workflow can be triggered by running the following scripts in order:
        1.  `python main.py`: Extracts PDFs and images from ZIPs in the `/files/uploaded` directory.
        2.  `python process_pdfs.py`: Performs OCR on the extracted PDFs and stores the results in the database.

4.  **Running the Web Application:**
    *   To start the web server, run:
        ```bash
        flask run
        ```
    *(Note: This is an inferred command based on the project structure and dependencies. The exact command may vary.)*

5.  **Resetting the Environment:**
    *   To reset the application to its initial state (clearing the database and moving processed files back to the upload directory), run:
        ```bash
        python reset.py
        ```

### Development Conventions

*   **Configuration:** The application uses a `.env` file for configuration. An example is provided in `.env.example`.
*   **Database:** Database models are defined in `models.py` using SQLAlchemy.
*   **Modular Design:** The project is organized into several modules with distinct responsibilities:
    *   `main.py`: Handles the initial zip file ingestion.
    *   `process_pdfs.py`: Manages the PDF processing and OCR workflow.
    *   `ocr_extraction.py`: Contains the core OCR logic and coordinate definitions.
    *   `app.py`, `worker.py`: Contain the web application and background job processing logic.
*   **Logging:** The application generates log files in the `logs/` directory to track the status of file processing.

### Flask Application

The Flask application provides a web interface for the project. It is organized using blueprints.

*   **`uploads` Blueprint:**
    *   `/upload_files` (GET): Displays the file upload form.
    *   `/upload` (POST): Handles file uploads, creates a job, and queues it for processing.

*   **`jobs` Blueprint:**
    *   `/jobs/<job_token>` (GET): Returns the status of a job as JSON.
    *   `/jobs/<job_token>/view` (GET): Displays a page that shows the status of a job.
    *   `/healthz` (GET): A health check endpoint.
    *   `/jobs` (GET): Displays a list of recent jobs.

*   **`uploaded_results` Blueprint:**
    *   `/uploaded_results` (GET): Displays a paginated list of uploaded zip files and their processing status.

*   **`screenings` Blueprint:**
    *   `/screenings` (GET): Displays a paginated list of patient encounters and their associated reports.

*   **`reports` Blueprint:**
    *   `/dr/<path:filename>` (GET): Serves a Diabetic Retinopathy report PDF.
    *   `/glaucoma/<path:filename>` (GET): Serves a Glaucoma report PDF.

*   **`media` Blueprint:**
    *   `/img/<path:filename>` (GET): Serves an image file.