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
- ```app.py```: Application factory and entry-point for the Flask app. Initializes configuration, environment, logging, DB schema, thread pool, and registers all blueprints. Provides the homepage route (`/`). Has features for security, and protetcion of routes
- ```models.py```: 

- ```main.py``` : Data processing pipeline designed to extract and analyze medical reports from Remedio FOP camera zip files which contain a named directory about the encounter with sub-directories for images and PDF report on Diabetic Retinopathy and Glaucoma screening results. The workflow begins by ingesting multiple zip files, extracting their contents (PDFs and images).
- ```process_pdfs.py``` and ```ocr_extraction.py```: Performing Optical Character Recognition (OCR) on the PDFs to extract key medical data points. The extracted information is then stored in a structured database. 
- 

Then data cleaning needs to be performed such as dates, numeric values etc.



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
