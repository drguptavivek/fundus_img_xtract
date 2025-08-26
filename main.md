Got it—here’s a clear, “how it gets populated” doc based entirely on your `main.py` flow. It explains the first-time population of every table and where files go on disk.

# How the schema is first populated (from `main.py`)

## 0) What you run

```bash
python main.py
```

This executes `main()` which orchestrates **directory setup**, **DB setup**, then **iterates over every ZIP** in `files/uploaded/*.zip`.

---

## 1) Environment & database setup

### 1.1 Create directories (idempotent)

`setup_environment()` ensures these exist:

* `files/uploaded` — incoming ZIPs (source)
* `files/images` — extracted/renamed images
* `files/pdfs` — extracted/renamed PDFs
* `files/processed` — successfully handled ZIPs
* `files/processing_error` — failed ZIPs
* `logs/zip_main_process_log.txt` — append-only processing log

### 1.2 Create database & tables (idempotent)

`setup_database()` calls `Base.metadata.create_all(engine)` creating:

* `zip_files`
* `patient_encounters`
* `encounter_files`
* (`diabetic_retinopathy_reports` / `glaucoma_reports` exist but are **not** populated by this script; another PDF-processing script does that later)

---

## 2) What qualifies a ZIP & how metadata is extracted

### 2.1 Duplicate detection (content-level)

* The script computes **MD5** of the ZIP: `calculate_md5(zip_path)`
* It queries `ZipFile` by `md5_hash`.

  * **If found** → The ZIP is treated as a **duplicate**:

    * It is **moved** to `/files/dupmd5_YYYY-MM-DD/` (created on the fly under `files/`).
    * A log line is written with status `SKIPPED_DUPMD5` and the **original filename** that first introduced this MD5.
    * **No DB inserts** happen for duplicates.

### 2.2 Required folder structure inside the ZIP

While scanning entries inside the archive, the script tries to locate a **top-level parent directory** whose **name matches** the pattern:

```
Name_ID_Date
```

(loosely parsed by splitting on underscores and ensuring at least 3 parts)

From that directory name:

* `capture_date` = last part
* `patient_id` = second last part
* `name` = everything before the final two parts (spaces preserved)

**If no such directory is found:** it raises `ValueError("No directory matching the 'Name_ID_Date' format found.")`, rolls back, and routes the ZIP to the **error** directory.

> Practical tip: Keep your ZIP layout as
> `Some Name_123456_2024-11-03/...files...`
> or generally `Name_With_Spaces_ABC123_YYYY-MM-DD`.

---

## 3) How rows are inserted on success

All file extraction and database writes happen inside a single transaction boundary; a **commit** at the end persists everything, otherwise it **rolls back**.

### 3.1 `zip_files` (one row per accepted ZIP)

* `zip_filename` = the uploaded zip’s name with Windows duplicate suffixes removed, e.g. `abc (1).zip` → `abc.zip` (via `clean_filename`)
* `md5_hash` = computed MD5 for deduplication

### 3.2 `patient_encounters` (exactly one row per `zip_files`)

* Linked to `zip_files` via **1–1** (`zip_file_id` unique)
* Values:

  * `name` = parsed from parent dir (everything before `_ID_Date`)
  * `patient_id` = parsed from parent dir (the penultimate part)
  * `capture_date` = parsed from parent dir (the last part)

> The assignment is done via relationship:
>
> ```python
> new_zip_file.patient_encounter = PatientEncounters(...)
> ```

### 3.3 `encounter_files` (one row per extracted file in the identified parent tree)

The script **extracts** only files that are:

* Under the **identified parent directory** (`Name_ID_Date/...`)
* Have supported extensions:

  * Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp` → saved to `files/images`
  * PDFs: `.pdf` → saved to `files/pdfs`
* Others are skipped (no DB row, no extraction)

Each extracted file is **renamed** with a **stable pattern**:

```
{patient_id}_{name_with_underscores}_{capture_date}_{original_filename}
```

Examples:

* `123456_Some_Name_2024-11-03_fundus_right.jpg`
* `123456_Some_Name_2024-11-03_report.pdf`

For each extracted file, an `EncounterFile` row is created:

* `filename` = the new filename (as saved on disk)
* `file_type` = `'image'` or `'pdf'`
* `ocr_processed` = `False` (default; another script updates this later)

> The rows are attached via:
>
> ```python
> new_patient_encounter.encounter_files = [EncounterFile(...), ...]
> ```

### 3.4 Commit

If all goes well:

* `session.commit()` persists:

  * 1 row in `zip_files`
  * 1 row in `patient_encounters`
  * N rows in `encounter_files` (N = extracted files under the parent)
* The ZIP is **moved** to `files/processed`.

---

## 4) What happens on failure

### 4.1 ZIP format or structure errors

* `zipfile.BadZipFile` or `ValueError` (e.g., bad structure) → `session.rollback()`
* ZIP is moved to `files/processing_error`.

### 4.2 Any other exception

* `session.rollback()`
* ZIP is moved to `files/processing_error`.

### 4.3 Windows file locks

All final moves use a **retrying `safe_move()`** (up to 5 attempts with backoff) to mitigate temporary locks. If the final move still fails, a **clear error** is logged.

---

## 5) Logging (append-only)

Every ZIP processed gets a line in `logs/zip_main_process_log.txt`:

```
[YYYY-MM-DD HH:MM:SS] <zipname> -> <STATUS> | <message?>
```

Statuses used by this script:

* `SUCCESS` — fully processed, DB committed, moved to `processed`
* `ERROR` — failed, rolled back, moved to `processing_error` (exception text appended)
* `SKIPPED_DUPMD5` — duplicate by content; moved to daily `dupmd5_YYYY-MM-DD` folder with a note of the original filename

---

## 6) What this script does **not** populate

* `diabetic_retinopathy_reports`
* `glaucoma_reports`

Those are intentionally left for the **PDF processing script** that:

* Parses the saved PDFs in `files/pdfs`
* Inserts rows into `diabetic_retinopathy_reports` and `glaucoma_reports`
* Marks the corresponding `encounter_files.ocr_processed = True` (if your OCR step sets it)

---

## 7) End-to-end example (happy path)

1. Place `Some Name_ABC123_2025-08-20.zip` in `files/uploaded/`.
2. Run `python main.py`.
3. Script:

   * Ensures directories & tables exist.
   * Sees it’s a new MD5 (not a duplicate).
   * Finds parent dir `Some Name_ABC123_2025-08-20/` inside the ZIP.
   * Extracts supported files under that dir:

     * Saves images to `files/images/ABC123_Some_Name_2025-08-20_<original>.jpg`
     * Saves PDFs to `files/pdfs/ABC123_Some_Name_2025-08-20_<original>.pdf`
   * Inserts:

     * `zip_files` (1 row)
     * `patient_encounters` (1 row, linked)
     * `encounter_files` (N rows, linked)
   * Commits and moves the ZIP to `files/processed`.
   * Logs `SUCCESS`.

---

## 8) Operational checklist

* ✅ ZIP internal tree must contain a folder named like `Name_ID_Date` (at least 3 underscore-separated parts).
* ✅ Place ZIPs in `files/uploaded/`.
* ✅ Run `python main.py`.
* ✅ Check `logs/zip_main_process_log.txt` for outcomes.
* ✅ Inspect `files/processed/` (success), `files/processing_error/` (failures), and `files/dupmd5_YYYY-MM-DD/` (duplicates).
* ⌛ Run your **PDF processing script** afterwards to populate DR/Glaucoma report tables and update `ocr_processed`.

---

## 9) Data integrity & idempotency notes

* **Duplicate content** is filtered by `md5_hash` (content-level), not by filename.
* `patient_encounters.zip_file_id` is **unique**, enforcing **one encounter per ZIP**.
* Filenames on disk are deterministic—reruns won’t re-extract duplicates because the ZIP will have been moved out of `files/uploaded` on success, or flagged on subsequent runs by the same MD5.
* On any failure, no partial DB writes remain (transaction rollback).

---

If you’d like, I can also draft a short **README “Importer” section** you can drop into your repo, or produce a **sample run log** and **example DB snapshot** (tabular) to include in docs.
