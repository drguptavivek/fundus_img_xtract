
# Purpose
To extract data from remedio camera zip files
Uses PyTesseract, pyUPDF



```bash
git clone https://github.com/drguptavivek/fundus_img_xtract.git
uv init
uv sync

```


## To Run

```bash
# TO RESET all files excepot teh /files/uplaoded directory . delete  the DB
# ALL  PROCESSED FILES GET MOVED BACK TO /UPLOADED
# ALL DUPL    Md5 FILES GET MOVED BACK TO /UPLOADED
python reset.py

# To create directories and A NEW empty DB
python initialize.py

Standalone database setup utility.

Usage examples (PowerShell):
  # Create tables only (fast)
  python scripts/setup_db.py

  # Create tables + backfill UUIDs (EncounterFile + Reports)
  python scripts/setup_db.py --migrate-uuids

  # Check-only UUID migration (no changes, just counts/indexes)
  python scripts/setup_db.py --migrate-uuids --check-only

#Options:
#  --batch-size N        Rows to update per batch (UUID backfill)
#  --progress-every N    Print progress every N batches


# Extract PDFs and images from ZIPs in the /uplaoded directory and move source ZIPs  to prcessed direcy
python main.py


#  Iterates through all PDF files in the PDF_DIR, performs OCR,
#  stores the extracted results into the database, and
#  splits and saves individual report pages to new directories.
#  The OCR is run using           ocr_extraction.py  
#  ocr_extraction.py contains the coordinates of all areas of interest for text extraction
# ocr_extraction.py USES -   PyMuPDF  PIL pytesseract   matplotlib.pyplot 
python process_pdfs.py

```

## FLASP APP

```bash
python app.py

```



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
