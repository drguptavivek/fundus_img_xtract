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


**Confidentiality** is a key aspect of the grading workflow, handled through two main principles: masking patient identity and ensuring grader independence. 
    *   First, the grading interface is "masked" to protect patient privacy. When a grader views an image, the system only displays the image   itself and non-identifying metadata like the capture date and image UUID. It deliberately withholds all patient-identifying information, such as name or patient ID, so the grader has no knowledge of whose image they are assessing.
    *   Second, the system ensures that each grader's assessment is independent and confidential from other graders. A user can only see their own previous grading for an image, not the assessments made by their colleagues. This prevents one expert's opinion from influencing another's, which is crucial for an unbiased assessment and for later analysis of inter-rater agreement.


### Progress So far

#### Models 

- ```models.py```: The database manages medical imaging data, specifically retinal fundus images, from ingestion to analysis and grading.[Documentation](docs/models.md)

#### Standlone scripts

- ```main.py``` : Data processing pipeline designed to extract and analyze medical reports from Remedio FOP camera zip files which contain a named directory about the encounter with sub-directories for images and PDF report on Diabetic Retinopathy and Glaucoma screening results. The workflow begins by ingesting multiple zip files, extracting their contents (PDFs and images). 
    -  During the initial processing in main.py, files are checked for disallowed extensions, path traversal, and content-type mismatches. 
    - Generate MD5 hash to check for duplicate ZIP file uploads. 
    - UUIDs are generated and assigned only during the initial processing of ZIP files in main.py. When an image or an original PDF is extracted, the system creates a corresponding EncounterFile record in the database and assigns it a unique UUID. 
    - Further, In ```models.py```, the uuid column in the ```EncounterFiles``` table is defined with a  default value that automatically generates a UUID. This means that even though main.py doesn't explicitly create a UUID when it  creates new EncounterFiles records, the database handles it automatically. As a result, every original image and every original report gets it own unique UUID.  [Documentation](docs/main.md). 

- ```process_pdfs.py``` and ```ocr_extraction.py```: Performing Optical Character Recognition (OCR) on the PDFs to extract key medical data points. The extracted information is then stored in a structured database.  The split, single-page PDFs for Diabetic Retinopathy and Glaucoma reports, which are created later by process_pdfs.py, are also assigned their own UUIDs. In ```models.py```, the uuid column in the DiabeticRetinopathyReport, and GlaucomaReport tables is defined with a  default value that automatically generates a UUID. This means that even though process_pdfs.py doesn't explicitly create a UUID when it  creates new report records, the database handles it automatically. As a result, every split PDF report gets it own unique UUID.  [Documentation process_pdfs](docs/process_pdfs.md) and [Documentation ocr_extraction](docs/ocr_extraction.md) 

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
  type (.zip) and ensuring they are within the configured size limits. Upon successful validation, it saves the files to a dedicated upload directory, creating a unique filename for each to prevent overwrites. 
  - The uploads blueprint  does handle filename collisions to prevent overwriting existing files. It achieves this using a helper function called _uniquify. When a file is uploaded, this function checks if a file with the same name already exists in the destination directory. If it does, it  appends a sequential number in parentheses to the filename (e.g., my_file (1).zip, my_file (2).zip) until it finds a unique name. This  ensures that all uploaded files are saved without conflict, even if they originally had the same name.
  - It also records metadata about each upload, including the uploader's identity and IP address. 
  - Finally, it creates a  new job in the database and queues it for background processing to extract and analyze the contents of the uploaded ZIP files. 
  - While the uploads blueprint orchestrates the initial part of the process, the heavy  lifting of processing job_items and PDFs happens in the background. Here's a more detailed breakdown:
   1. Job and Job Item Creation: When you upload files, the uploads blueprint creates a master Job record to track the overall task 
   2. For each individual ZIP file uploaded within that task, it creates a corresponding JobItem. This allows the system to monitor the status of each file independently. These records are stored in the database with an initial "queued" status.
   2. Background Worker: The blueprint then hands off the job to a background worker. This worker picks up the queued JobItems and begins processing them one by one. This ensures that the web application remains responsive and doesn't get blocked by long-running tasks.
   3. ZIP Extraction: For each JobItem, the worker first extracts the contents of the ZIP file. During the initial processing in main.py, files are checked for disallowed extensions, path traversal, and content-type mismatches. If any of these security checks fail, a MaliciousZipError is raised, and the background worker immediately flags the corresponding JobItem in the database with an "error" state and stores the specific reason for the failure. For other processing errors, like a corrupted ZIP file, the same process occurs. The worker catches the exception, marks the JobItem  "error," and records the error message. 
   4. PDF Processing and OCR: Once the PDFs are extracted, the worker initiates the PDF processing pipeline. This pipeline iterates through the unprocessed PDFs, performs Optical Character Recognition (OCR) to extract text and data from specific regions of the pages. It looks for Diabetic Retinopathy and Glaucoma reports, and if found, it saves the extracted data into the database, linking it to the corresponding patient encounter. The individual report pages are also saved as separate PDF files for easy access. 
    5. If any JobItem within a batch fails, the parent Job is also marked as "error." This typically includes images andone or more PDF reports. This is done by ```main.py``` describe above.
    6. The ```jobs``` blueprint is designed to monitor the status of background processing tasks created after file uploads. It provides a main page that lists the 100 most recent jobs, showing at a glance which ones have completed or encountered errors. For more detailed insight,administrators can access specific job pages. Each job has a dedicated page that displays the real-time status of every individual file (JobItem) within that job, polling for update to show whether each file is queued, processing, or finished. 
    7. The ```/admin/malicious-uploads ``` path gives admins view into who is uplaodin malacious files


##### Serving Images and PDFs

 * The /media blueprint has two main routes. media.serve_image serves images directly by their filename, while media.serve_file_by_uuid is more versatile, serving either an image or an original PDF based on the file's unique ID from the database.

  * The /reports blueprint is dedicated to serving the single-page, split PDF reports. The serve_dr_pdf and serve_glaucoma_pdf routes serve these reports by filename, while the serve_dr_pdf_by_uuid and serve_glaucoma_pdf_by_uuid routes provide access to the same reports using  their stable UUIDs. Finally, glaucoma_results_redirect is a simple redirect to maintain compatibility with an older URL structure


##### Automated Data Audits
  * `audit.missing_capture_date`: This is a data quality assurance endpoint for administrators. It identifies and lists all patient
     encounters in the database that are missing a valid, machine-readable capture date, allowing admins to easily find and correct
     incomplete records.

   * `glaucoma.glaucoma_clean_workflow`: This is a data processing endpoint for administrators that takes the raw, text-based glaucoma
     results from the OCR process and cleans them. It parses values like the Vertical Cup-to-Disc Ratio (VCDR) into a standardized, numeric
     format and saves them to a separate table, preparing the data for reliable analysis and visualization.


##### Viewing and Searching Patient Encounters / Screeinings

The `screenings.list_screenings` route displays a searchable and paginated list of all patient encounters, ordered with the most recent first. It allows administrators and ophthalmologists to quickly find specific encounters by searching for a patient's name, or ID.

From that list, the `screenings.screening_detail` endpoint provides a comprehensive view of a single encounter. It displays all associated  images in a gallery, provides links to the generated DR and Glaucoma PDF reports, and includes navigation to easily move to the previous or next patient encounter in the timeline.

Patient details are NOT masked in these screens. Hence confidential payinet data will be revealed to teh viewers. Only selected persons whoudl eb given access to these screens.

##### Manual Data Verification for Glaucoma Reports

From the Navbar `Glacuoma > Verify` menu, the `glaucoma.list` endpoint provides a workflow-oriented view for data verification, listing all glaucoma reports paginated by date. It allows users to  filter for "verified" or "unverified" encounters and provides a shortcut to jump to the most recent unverified date, streamlining the process of finding and reviewing records that need attention. From here, users can navigate to the edit page to perform the verification.

The `glaucoma.glaucoma_edit` endpoint displays all the images that are associated with a single patient encounter, alongside the editable data extracted from the corresponding glaucoma report. This page serves as a critical data verification and enrichment tool. Its main functionalities include:
   1. Editing Data: It allows authorized users to correct or update the OCR-extracted data, such as the VCDR values, results and qualitative results.
   2. Tagging Laterality: For each image displayed, the user must tag it as belonging to the "right" eye, "left" eye, or "cannot_tell".
   3. Verification: Once all the data is confirmed and every image has been tagged, the user can mark the entire encounter as "verified,"
      signaling that it is complete and ready for analysis. This verification step is blocked until all images are tagged.

This information is saved across several tables in the database to ensure data integrity and traceability:

   1. Laterality (Eye Side): The eye side ("right", "left", or "cannot_tell") is saved in the `eye_side` column of the **EncounterFile** table. 
      This is done via an AJAX call from the glaucoma_edit` page, which updates the specific image record when a user clicks the corresponding
      button.

   2. Verification Status: The verification status, along with the verifier's username and the timestamp, is stored in the `PatientEncounters`
      table. There are separate columns for glaucoma and DR verification (e.g., glaucoma_verified_status, glaucoma_verified_by). This status is
       updated when a user clicks the "Verify" or "Unverify" button on the edit page.

   3. Cleaned Data: The cleaned, numeric VCDR values are stored in the `GlaucomaResultsCleaned` table. This table is populated by the
      glaucoma_clean_workflow endpoint, which parses the raw OCR text. Users can also manually update this cleaned data via the glaucoma_edit
      page.

   4. Original Data: The original, raw text extracted by the OCR process is preserved in the `GlaucomaReport` and `DiabeticRetinopathyReport`
      tables. Additionally, for traceability, the GlaucomaResultsCleaned table keeps a copy of the original VCDR text strings alongside the
      cleaned numeric values.

  The `glaucoma.results` route serves as an analytics dashboard, presenting a high-level overview of the cleaned glaucoma data. It displays aggregate  statistics, such as the total number of reports and unique patients, and shows the distribution of qualitative results. The key feature is the pair of histograms that visualize the distribution of the numeric VCDR (Vertical Cup-to-Disc Ratio) values for both right and left  eyes. It can be acessed from the Navbar `"Glacucoma > Dashboard"`


Patient details are  masked in these screens. Hence confidential patinet data will be proetcted from the viewers. 

##### Manual Data Verification for Diabetic Retinopathy Reports
To Be Developed
The laterality of some of the images would already be marked as part of the Glaucoma workflow.

##### Grading of Glaucoma

Clicking a "Gradiing" button on the navigation bar takes the user to the  `grading.index` route accessible at `\grading\`. This route serves as the central dashboard for the image grading workflow, accessible to ophthalmologists, optometrists, and  administrators. It provides several key features to streamline the process.
- To help users jump directly into their work, it includes a "Start Grading" feature that finds a random, ungraded image and provides a  direct link to its grading page. 
- The page also includes a form to look up a specific image by its UUID 
- It also has a paginated list of the  current user's previously graded images, which can be filtered by disease and impression, allowing for easy review of past work.
- It displays several Key Performance Indicators (KPIs) to provide a summary of the overall grading activity. These
  include:
   * A count of Total Glaucoma Gradings and Total DR Gradings.
   * The number of Total Unique Images that have received at least one grade.
   * An Overall Total of all grading records in the system.
   * A breakdown of Gradings by Impression, showing the counts for each clinical assessment category, such as "Normal," "Glaucoma Suspect,"
     and "Glaucoma."
The KPIs displayed on the /grading/ dashboard, such as the total counts for glaucoma and DR gradings and the breakdown by impression, represent the overall gradings done by anyone in the entire system.
 

When a user clicks the `"Start Glaucoma Grading"` button, the system prioritizes images that are both recent and ungraded by that specific  user. The logic first identifies the 50 most recent images that do not have a corresponding glaucoma grading record for the currently logged-in user. From this pool of 50 recent, ungraded images, it then selects one at random to present for grading. This method ensures that graders are generally working on the newest available images while the randomization helps distribute the workload if multiple graders are active at the same time.

**GRADING:** Grading screen is served at route  `grading.glaucoma_image` accessible at `grading/glaucoma/image/<image UUID>`). This is the primary interface for grading an individual fundus image for glaucoma. It takes an image's unique ID (UUID) from the URL and displays the image to a qualified user, such as an ophthalmologist or optometrist. Alongside the image, it presents a grading form with a predefined list of clinical impressions. 

If the user has previously graded that same image, the form comes pre-filled with their prior assessment, allowing them to  easily review or revise it. This route is focused solely on presenting the image and the form for capturing the user's expert opinion. The template for the glaucoma grading route is designed for an efficient clinical workflow, and the backend saves the data using a robust "upsert" method.  Based on the current implementation, the same grader can submit a glaucoma grade for an image multiple times, but only the most recent grade will be saved. 

The system is designed to "upsert" the grading record, meaning it updates the existing record if one is found for that specific user and image, rather than creating a new one. Because it overwrites the previous assessment, the system does not store a history of a single  user's past gradings for the same image.

**Therefore, with the current functionality, intra-rater agreement cannot be assessed, as there is only ever one grading instance per user per image stored in the database. To measure this, the system would need to be modified to store multiple, separate grading records from  the same user for the same image.** THIS IS A DEDICATED FEATURE THAT NEEDS TO BE BUILT WITH POISSBLE ITS OWN UNIQUE DATA MODEL


- The grading page prominently features an **advanced image viewer** which, based on the project's conventions, includes controls for fullscteen, R, G, B, Y, H and none filters, brightness, and contrast, with keyboard navigation allowing for detailed examination of the fundus image. 
- The **grading form** itself uses large, color-coded  buttons for quick selection of a clinical impression like "Normal" or "Glaucoma Suspect." If an image is deemed "Not gradable," a  secondary list of buttons appears to let the user specify the reason. 

- When a user selects the "Not gradable" option during grading, a list of predefined reasons appears as clickable buttons. The reasons are:
   * Disc not focussed
   * Retina not focussed
   * Disc not complete
   * Artefacts
   * Other

  Clicking one of these buttons automatically appends that reason to the "Remarks" text field, providing a quick and standardized way to explain why the image could not be assessed. Text in that field can be edited anytime. The data is saved in as it is form.

- The form also includes "Save & Next" and "Save & Close" buttons to  streamline the process of grading multiple images in a single session. There is also a 'Clear" button to reset choices and a back to "Grading Dashboard" button.
- **Results**   When a grading is submitted, the system uses an "upsert" (a combination of update and insert) logic. It checks the ImageGrading table to see if the current user has already graded that specific image for glaucoma. If a previous grading exists, the system simply updates that record with the new impression and remarks. If it's the first time the user is grading that image, a new record is created in the ImageGrading table, linking the user, the image, their role, and their clinical assessment.

Patient details are  masked in these screens. Hence confidential patinet data will be proetcted from the viewers. 

##### Grading of Dianetic Retnopathy
The grading.dr_image route is the dedicated interface for grading a fundus image for Diabetic Retinopathy (DR). Similar to its glaucoma  counterpart, it takes an image's UUID and displays the image along with a grading form to a qualified user. The route also prefills the  form with the user's previous DR grading for that image, if one exists, allowing for review or revision.

The specific grades collected for DR are based on the standard classification for the disease. The user must select one of the following  impressions from a predefined list: "No DR", "Mild NPDR", "Moderate NPDR", "Severe NPDR", "PDR" (Proliferative Diabetic Retinopathy), or  "Not gradable". This selection, along with any optional remarks, is then saved to the database as the user's official grading for that  image.


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