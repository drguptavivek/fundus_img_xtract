Here’s a tight, developer-focused doc for your **PDF OCR + persistence** runner. It explains what the script does, how it finds the right DB rows, what it writes, where split pages go, how it logs, and how it behaves on errors/duplicates.

# PDF OCR & Report Persistence — Runner Documentation

**File:** (your script that calls OCR; run as `python <this_file>.py`)
**Purpose:**

1. Iterate over PDFs saved by the ZIP ingestor in `files/pdfs`.
2. Use `ocr_extraction.find_report_pages_by_coords_with_grid()` to extract DR/Glaucoma text snippets + page numbers.
3. Persist results to `DiabeticRetinopathyReport` / `GlaucomaReport`. In ```models.py```, the uuid column in the DiabeticRetinopathyReport, and GlaucomaReport tables is defined with a  default value that automatically generates a UUID. This means that even though process_pdfs.py doesn't explicitly create a UUID when it  creates new report records, the database handles it automatically. As a result, every split PDF report gets it own unique UUID. 
4. Optionally **split and save** the detected DR/GL pages to dedicated folders.
5. Mark the corresponding `EncounterFile.ocr_processed = True`.
6. Log success/error lines.

---

## 1) Prerequisites & Imports

* **Relies on models.py** for:

  * `Session` (SQLAlchemy session factory), `engine` (not directly used), `PDF_DIR`
  * Models: `PatientEncounters`, `EncounterFile`, `DiabeticRetinopathyReport`, `GlaucomaReport`
* **Calls** `find_report_pages_by_coords_with_grid` from `ocr_extraction.py`
  (Your OCR function must already be tuned for the document layout.)

**External libs used here:**

* `fitz` (PyMuPDF) — opening PDFs and exporting single pages.
* `datetime` — log timestamps.
* `pathlib` — safe paths.
* `sqlalchemy.orm` — DB session typing.

---

## 2) Directory Layout (created/used)

* **Input PDFs:** `files/pdfs/` (populated by the ZIP pipeline).
* **Output split pages:**

  * `files/dr_pdfs/` — single-page DR reports (optional, when DR page is found).
  * `files/glaucoma_pdfs/` — single-page Glaucoma reports (optional, when GL page is found).
* **Logs:**

  * `logs/process_pdf_success_log.txt`
  * `logs/process_pdf_error_log.txt`

The runner creates the *split* output directories if missing.

---

## 3) File Naming & Encounter Lookup

**Expected PDF filename format (produced by ZIP processing):**

```
{patient_id}_{name_with_underscores}_{capture_date}_{original_filename}
```

* The runner parses **only the first token** as `extracted_patient_id` (`parts[0]`).
* It looks up the encounter:
  `db_session.query(PatientEncounters).filter_by(patient_id=extracted_patient_id).first()`

**If no encounter exists:**

* The PDF is **skipped**, and an error log line is written.

> Tip: The encounter lookup is by **patient\_id** only; if there can be multiple encounters per patient, consider tightening this (e.g., include capture\_date) in a future revision.

---

## 4) Idempotency & Duplicate Work

Before doing any OCR, it checks whether **any** DR or GL report already exists for the encounter:

```python
existing_dr_report = session.query(DiabeticRetinopathyReport).filter_by(patient_encounter_id=...).first()
existing_gl_report = session.query(GlaucomaReport).filter_by(patient_encounter_id=...).first()
```

* If either exists → **Skip OCR**, write a log line (“already exist”), and (optionally) flip `EncounterFile.ocr_processed = True` for this PDF.

> This is coarse-grained idempotency at the encounter level (not filename-level); if you have multiple PDFs per encounter and want one report per PDF, add uniqueness rules accordingly.

---

## 5) OCR Call & Returned Values

For each eligible PDF:

```python
(dr_page, gl_page,
 dr_result, dr_qual,
 gl_result, vcdr_rt, vcdr_lt, gl_qual) = find_report_pages_by_coords_with_grid(pdf_path)
```

* `*_page` are **1-based** indices of detected pages.
* Text fields may be `None` or contain newlines; the helper `clean_ocr_text()` flattens whitespace.

---

## 6) Splitting & Saving the Detected Pages (optional but implemented)

If a DR page is found, the runner:

* Opens the PDF with PyMuPDF.
* Creates a new 1-page PDF for that page.
* Saves it to `files/dr_pdfs/` with the name:

  ```
  {patient_id}_{patient_name_from_db}_{capture_date_from_db}_DR_Page{dr_page}.pdf
  ```

Same for Glaucoma pages → `files/glaucoma_pdfs/` with `_GL_Page{gl_page}.pdf`.

> Note: Pages in PyMuPDF are **0-indexed**, so `dr_page - 1` and `gl_page - 1` are used when extracting.

---

## 7) Database Writes

### 7.1 Diabetic Retinopathy

If a DR page is detected, it inserts **one** `DiabeticRetinopathyReport` row:

* `patient_encounter_id` → resolved from DB
* `result` → cleaned OCR text from `dr_result`
* `qualitative_result` → cleaned OCR text from `dr_qual`
* `report_file_name` → the split DR PDF filename (or `None` if split failed)

### 7.2 Glaucoma

If a GL page is detected, it inserts **one** `GlaucomaReport` row:

* `patient_encounter_id`
* `vcdr_right` / `vcdr_left` → cleaned OCR strings
* `result` → cleaned OCR text from `gl_result`
* `qualitative_result` → cleaned OCR text from `gl_qual`
* `report_file_name` → the split GL PDF filename (or `None` if split failed)

### 7.3 Mark the source file as OCR’d

It looks up the associated `EncounterFile` row by:

```python
patient_encounter_id = <found encounter>
filename = pdf_path.name
```

If found, sets `ocr_processed = True`.

### 7.4 Transaction

* Commits **per PDF** after all inserts/updates for that file are queued.
* On any exception, rolls back the **current PDF**.

---

## 8) Logging

Two append-only logs in `logs/`:

* **Success log:** `process_pdf_success_log.txt`

  ```
  [YYYY-MM-DD HH:MM:SS] SUCCESS <filename> | <message?>
  ```

  Examples:

  * “Marked '<pdf>' as OCR processed in EncounterFile.”
  * “OCR and split pages completed”
  * “PDF OCR processing workflow finished.”

* **Error log:** `process_pdf_error_log.txt`

  ```
  [YYYY-MM-DD HH:MM:SS] ERROR <filename> | <message>
  ```

  Examples:

  * Malformed filename
  * Encounter not found
  * PyMuPDF open/save errors
  * General exceptions (with message)

Console prints mirror these entries.

---

## 9) Control Flow Summary

```
process_all_pdfs_for_ocr():
  - Make split dirs (dr_pdfs, glaucoma_pdfs)
  - pdf_files = PDF_DIR/*.pdf
  - if none -> log error and return

  For each pdf_path:
    parse patient_id from filename
    encounter = PatientEncounters.by(patient_id)
    if not encounter -> log error, continue

    if any report already exists for encounter:
        log "already exist"; optionally set ocr_processed=True; continue

    # OCR
    (dr_page, gl_page, dr_result, dr_qual, gl_result, vcdr_rt, vcdr_lt, gl_qual) = OCR(pdf)

    # open original pdf if any page found (for splitting)
    # split DR page -> save to files/dr_pdfs/..., remember dr_pdf_filename
    # split GL page -> save to files/glaucoma_pdfs/..., remember gl_pdf_filename

    # insert DR/GL rows with cleaned text + saved filenames
    # mark EncounterFile.ocr_processed=True for this filename

    commit()
    success logs

  finally: close session; write workflow-finished success log
```

---

## 10) Edge Cases & Behavior Notes

* **Malformed filename** (cannot split into ≥4 parts): skip + error log.
* **Encounter missing** (by patient\_id): skip + error log.
* **OCR finds no DR/GL page**: no report rows inserted; still marks `ocr_processed = True` if the `EncounterFile` exists, and logs success (because processing completed).
* **Split failures**: inserts report rows **without** `report_file_name` (kept `None`) and logs the save error.
* **Repeat runs**: If reports already exist for the encounter, the script **skips OCR** and may set `ocr_processed=True`.

---
