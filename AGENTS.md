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

#### Models 

- ```models.py```: The database manages medical imaging data, specifically retinal fundus images, from ingestion to analysis and grading.[Documentation](docs/models.md)

#### Standlone scripts

- ```main.py``` : Data processing pipeline designed to extract and analyze medical reports from Remedio FOP camera zip files which contain a named directory about the encounter with sub-directories for images and PDF report on Diabetic Retinopathy and Glaucoma screening results. The workflow begins by ingesting multiple zip files, extracting their contents (PDFs and images).This is done as a background job by the flask app. [Documentation](docs/main.md). 
- ```process_pdfs.py``` and ```ocr_extraction.py```: Performing Optical Character Recognition (OCR) on the PDFs to extract key medical data points. The extracted information is then stored in a structured database.  [Documentation process_pdfs](docs/process_pdfs.md) and [Documentation ocr_extraction](docs/ocr_extraction.md) 

#### Flask Application

``app.py```: Application factory and entry-point for the Flask app. Initializes configuration, environment, logging, DB schema, thread pool, and registers all blueprints. Provides the homepage route (`/`). Has features for security, and protetcion of routes. [Documentation](docs/app.md)

##### Login, Users, and Roles
   This application implements a comprehensive user and role management system distributed across three key blueprints. 
   
   The /auth blueprint handles core security, managing user login and logout while also defining the system's roles, which include "admin," "fileUploader,"  "ophthalmologist," and "data_manager." It uses decorators to protect routes, ensuring only authorized users can access specific  functionalities.

  The /account blueprint provides self-service capabilities, allowing authenticated users to update their personal profile information and change their own password. 
  
  For administrative functions, the /admin blueprint is restricted to users with the "admin" role. This  blueprint offers complete control over user management, including creating new users, assigning or revoking roles, editing profiles, and  resetting any user's password. This clear separation of concerns provides both user convenience and strong administrative oversight. 
  
  Role management is handled within the /admin blueprint, which includes an endpoint for creating new roles. This endpoint is exclusively  available to administrators, who can define new roles by providing a name that meets specific validation criteria. To protect routes and restrict access to users with specific roles, the application uses a custom decorator called @roles_required(). You  can apply this decorator to any Flask route, passing one or more role names as arguments. For example, using @roles_required('admin') on a  route ensures that only users with the "admin" role can access it, effectively locking down sensitive areas of the application.

##### Uploading

- The ```uploads`` blueprint in this Flask application manages the entire file ingestion workflow. It provides a web form for users with
  "admin" or "fileUploader" roles to upload one or more ZIP files. The blueprint validates these files, checking for correct file
  type (.zip) and ensuring they are within the configured size limits. Upon successful validation, it saves the files to a dedicated upload directory, creating a unique filename for each to prevent overwrites. It also records metadata about each upload, including the uploader's identity and IP address. Finally, it creates a  new job in the database and queues it for background processing to extract and analyze the contents of the uploaded ZIP files. While the uploads blueprint orchestrates the initial part of the process, the heavy  lifting of processing job_items and PDFs happens in the background. Here's a more detailed breakdown:
   1. Job and Job Item Creation: When you upload files, the uploads blueprint creates a master Job record to track the overall task For each individual ZIP file uploaded within that task, it creates a corresponding JobItem. This allows the system to monitor
      the status of each file independently. These records are stored in the database with an initial "queued" status.
   2. Background Worker: The blueprint then hands off the job to a background worker. This worker picks up the queued JobItems and
      begins processing them one by one. This ensures that the web application remains responsive and doesn't get blocked by
      long-running tasks.
   3. ZIP Extraction: For each JobItem, the worker first extracts the contents of the ZIP file. This typically includes images and
      one or more PDF reports.
   4. PDF Processing and OCR: Once the PDFs are extracted, the worker initiates the PDF processing pipeline. This pipeline iterates
      through the unprocessed PDFs, performs Optical Character Recognition (OCR) to extract text and data from specific regions of
      the pages. It looks for Diabetic Retinopathy and Glaucoma reports, and if found, it saves the extracted data into the
      database, linking it to the corresponding patient encounter. The individual report pages are also saved as separate PDF files
      for easy access.


- Then data cleaning needs to be performed such as dates, numeric values etc.



### Core Technologies

*   **Backend:** Python
*   **Web Framework:** Flask, Jinja2
*   **Database:** SQLAlchemy (ORM)
*   **Data Analysis:** Pandas, Numpy, Maplotlib
*   **Styling:** Bootstrap 5.3, SASS 
*   **JS:** Pure client side JS only. No TS or modules.
    *   Vendor: Photoswipe UMD, Bootstrap.min.js including popper.js, 
    *   Custom: Photo-swipe init, panzoom, password-policy, flash-toast messages, etc. No MODULES / TS style
*   **OCR:** Pytesseract
*   **Dependency Management:** uv
*   **Python Libraries:** Availble in [file](requirements.txt)


### Development Conventions

*   **Configuration:** The application uses a `.env` file for configuration. An example is provided in `.env.example`.
*   **Database:** Database models are defined in `models.py` using SQLAlchemy.
*   **Modular Design:** 
    *   **Blueprintes** with distinct responsibilities. 
    *   **CSS and JS** loaded from /static/css and /js. Assets are versioned using ```ASSETS_VERSION``` in ```.env``` for cache busting. 
        * ```assets\scss\boootstratp-theme.scss``` Base SASS template, OKLCH colors, RGB fallbacks, dark-mode variant using data-attributes.
        * ```static\css\bootstrap.min.css``` Generated Global CSS  
        * ```static\css\app.css``` CSS overrides and custom styles
    *   * **Templates** Sub-directories based on blueprintes. 
        * ```base.html``` having header, navbar, footer and global CSS and Scripts. It defines Jinja blocks for title, content, and page_scripts. The last one is to ensure page specific JS  and CSS gets loaded only of the specific template. Has Global SVG color filters (hidden) For images. Flash Toast messages shown for user feedback. 
        * ```_forms``` contains a Jinnja macro csrf_field() 
        * ```templates\grading\_viewer_card.html``` contains a Reusable grading image viewer card which Expects: image (EncounterFile with .uuid) . It has features to apply the  SVG color filters and brightness, contrast controls, reset and ketboard navigation. 
*   **Logging:** The application generates log files in the `logs/` directory to track the status of file processing.