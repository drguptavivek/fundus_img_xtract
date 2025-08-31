# Fundus Image Manager

## Abbreviations

- DR: Diabetic Retinopathy
- AI: Artificial Intelligence
- API: Application Programming Interface
- AMD: Age-related Macular Degeneration
- FOP: Fundus on Phone

## Project Overview

To develop a system for an eye hospital to manage retinal fundis images and generate datasets of reinal images that can be used for AI trainig and valdiation of AI models targeted at Glaucoma, DR and AMD.


### Project Objectives
 
- Manage ZIP files from Remedio FOP camera (containg patient information, images and possibly PDF reports of Remedio Medios AI generated diabetic retinopathy screening results).
- Manage standalone .JPG/.jpeg/ retinal images uploaded by Community Clinics, Retina Lab, Glaucoma lab etc. 
- The data and images should be ingested, cleaned, and anonymized. There is an emphasis on preserving original data [images, zip files, PDFs] while also having a framework for saving extended information about each image.
- Automated data cleaning based on rules of dates, values etc
- Manual verification and editong of data and images by Data Managers and Optometrists. They should indicate for each image. These steps include assessing the basic quality attributes of images and checking the data extarcted from PDF files.
- Independent masked coding of images by consultants, and fellows. The consultants and fellows can be  specialists in Glaucoma (for glaucoam grading), and in Retina (for DR and AMD grading). 
- Have an arbitration process to have a final grade for each image for each target disease
- Have a process of sampled regrading to assess intra-rater agreement/ reliability for each disease 
- Have a proceess to send images to an external API for grading of specific disease and save its result
- For each disease,  assess inter-rater agreement, intra-rater agreement , agreement between remedio AI and final grade etc



### Progress So far
- ```app.py```: Application factory and entry-point for the Flask app. Initializes configuration, environment, logging, DB schema, thread pool, and registers all blueprints. Provides the homepage route (`/`). Has features for security, and protection of routes. [Details](app.md)
- ```models.py```: This schema manages retinal fundus images from ingestion to analysis. It tracks patient encounters, extracted image and PDF files, OCR'd diagnostic data, and manual gradings by medical professionals. [Details](models.md). The 
- ```main.py``` : Data processing pipeline designed to extract and analyze medical reports from Remedio FOP camera zip files which contain a named directory about the encounter with sub-directories for images and PDF report on Diabetic Retinopathy and Glaucoma screening results. The workflow begins by ingesting multiple zip files, extracting their contents (PDFs and images). This step is working well and feature may be marked as complete.
- ```process_pdfs.py``` and ```ocr_extraction.py```: Performing Optical Character Recognition (OCR) on the PDFs to extract key medical data points. The extracted information is then stored in a structured database. This step is working well and feature may be marked as complete.
- 

Then data cleaning needs to be performed such as dates, numeric values etc.



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
