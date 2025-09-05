
# Fundus Image Manager

A comprehensive system for an eye hospital to manage retinal fundus images. It facilitates the generation of curated datasets for training and validating Artificial Intelligence (AI) models targeted at detecting Glaucoma, Diabetic Retinopathy (DR), and Age-related Macular Degeneration (AMD).

## Setup

```bash
git clone https://github.com/drguptavivek/fundus_img_xtract.git

# Install NPM packages and create directories
python3 setup_env_and_npm.py 
python setup_env_and_npm.py 

# Create venv in .venv and install packages listed in uv.lock
uv init
uv add -r requirements.txt

# Activate virtual environment
source .venv/bin/activate

# Set up database
python -m scripts.setup_db

# Create initial user and assign roles
python -m scripts.create_user
python -m scripts.assign_roles admin --roles admin
python -m scripts.assign_roles admin --roles admin data_manager
python -m scripts.assign_roles admin --roles fileUploader
```

## Running the Application

```bash
uv run app.py
```

## Data Processing Workflow

### Initial Setup
```bash
# To create directories and a new empty DB
python initialize.py

# Standalone database setup utility
# Usage examples:
# Create tables only (fast)
python scripts/setup_db.py

# Create tables + backfill UUIDs (EncounterFile + Reports)
python scripts/setup_db.py --migrate-uuids

# Check-only UUID migration (no changes, just counts/indexes)
python scripts/setup_db.py --migrate-uuids --check-only
```

### Main Processing Pipeline
```bash
# Extract PDFs and images from ZIPs in the /uploaded directory and move source ZIPs to processed directory
python main.py

# Iterates through all PDF files in the PDF_DIR, performs OCR,
# stores the extracted results into the database, and
# splits and saves individual report pages to new directories.
# The OCR is run using ocr_extraction.py  
# ocr_extraction.py contains the coordinates of all areas of interest for text extraction
# ocr_extraction.py uses: PyMuPDF, PIL, pytesseract, matplotlib.pyplot 
python process_pdfs.py
```

## Documentation

- [App Architecture](docs/app.md)
- [Database Models](docs/models.md)
- [Main Processing Pipeline](docs/main.md)
- [PDF Processing](docs/process_pdfs.md)
- [OCR Extraction](docs/ocr_extraction.md)
- [ZIP Uploads](docs/zip_uploads.md)
- [Direct Uploads](docs/direct_uploads.md)
- [Audit Workflows](docs/audit.md)
- [Grading System](docs/Grading.md)
- [Direct Grading](docs/direct_grading.md)
- [Security](docs/Security.md)
- [Logging](docs/Logging.md)

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
