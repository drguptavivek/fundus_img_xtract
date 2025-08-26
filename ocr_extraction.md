Here’s a compact, developer-facing doc for your OCR module, tailored to how it will be used alongside your ingestion pipeline and database models.

# OCR Extraction Module — Technical Documentation

**File:** `ocr_extraction.py`
**Purpose:** Locate DR & Glaucoma report pages inside exported clinical PDFs and extract key text snippets (overall results, VCDR values, and qualitative notes) using **PyMuPDF** for rendering and **Tesseract** for OCR.

---

## 1) External Dependencies

* **PyMuPDF** (`fitz`) — PDF rendering to raster images (pixmaps).
* **Pillow** (`PIL.Image`) — image object manipulation and cropping.
* **pytesseract** — OCR engine (requires native Tesseract installation and correct PATH).
* **matplotlib** — optional (disabled by default) to save debug images with grid overlays for coordinate tuning.

> Install:

```bash
pip install pymupdf pillow pytesseract matplotlib
# plus native tesseract-ocr per OS
```

---

## 2) Public API

### `find_report_pages_by_coords_with_grid(pdf_path: str) -> tuple`

Scans all pages of `pdf_path` and returns 8 values (or `(None, None)` on open error):

1. `pageNumberDiabeticReport: int | None` — 1-based index of page containing “diabetic”.
2. `pageNumberGlaucomaReport: int | None` — 1-based index of page containing “glaucoma”.
3. `text_diabetic_result: str | None` — DR result (from a fixed results region).
4. `text_diabetic_qual_result: str | None` — DR qualitative notes/warnings.
5. `text_glaucoma_result: str | None` — Glaucoma result (from a fixed results region).
6. `vcdr_rt: str | None` — VCDR Right eye.
7. `vcdr_lt: str | None` — VCDR Left eye.
8. `text_gl_qual_result: str | None` — Glaucoma qualitative notes.

**Errors & behavior**

* If the PDF cannot be opened → prints error and returns `(None, None)`.
* If neither page is located, corresponding fields remain `None`.
* When a report type is found on a page, OCR reads the specific sub-regions (see §3).

---

## 3) Page Regions (Pixel Coordinates)

All coordinates are **pixel rectangles** `(x1, y1, x2, y2)` applied to a **300 DPI** rasterized page. These assume a consistent PDF template/layout. Adjust when templates change.

### Diabetic Retinopathy (DR) Regions

* `diabetic_report_coords = (0, 200, 1200, 400)`
  *Page detector:* should contain the word “diabetic” (lowercased).
* `diabetic_result_coords = (350, 650, 2000, 800)`
  *Primary result text.*
* `diabetic_qual_coords = (50, 3100, 1600, 3200)`
  *Qualitative result / warnings area.*

### Glaucoma Regions

* `glaucoma_report_coords = (0, 400, 1200, 600)`
  *Page detector:* should contain the word “glaucoma” (lowercased).
* `glaucoma_result_coords = (0, 1550, 2000, 1650)`
  *Primary result text.*
* `glaucoma_vcdr_rt_coords = (0, 1300, 1000, 1500)`
  *VCDR Right.*
* `glaucoma_vcdr_lt_coords = (1300, 1300, 2200, 1500)`
  *VCDR Left.*
* `glaucoma_qual_coords = (50, 3100, 1700, 3200)`
  *Qualitative notes.*

> These rectangles are tuned for **300 DPI** rasters (`page.get_pixmap(dpi=300)`). If you change DPI, **re-tune** coordinates or convert them proportionally: `scale = new_dpi / 300`.

---

## 4) Processing Flow

1. **Open PDF** with `fitz.open(pdf_path)`.
2. **Iterate pages** until both reports are found (early exit optimization).
3. **Render page @300 DPI** and load into Pillow (`Image`).
4. **(Optional grid overlay)**
   A commented block draws a red grid and saves a `page_{n}_with_grid.png` debug image (helpful for coordinate tuning). Uncomment to use.
5. **Detect DR page**

   * Crop `diabetic_report_coords`, OCR lowercased text, check substring `"diabetic"`.
   * If present, mark page number (1-based) and OCR `diabetic_result_coords` and `diabetic_qual_coords`.
6. **Detect Glaucoma page**

   * Crop `glaucoma_report_coords`, OCR lowercased text, check substring `"glaucoma"`.
   * If present, mark page number and OCR `glaucoma_result_coords`, `glaucoma_vcdr_rt_coords`, `glaucoma_vcdr_lt_coords`, and `glaucoma_qual_coords`.
7. **Close document**, print a short summary to stdout, and **return the tuple** described above.

---

## 5) Example Usage

```python
from ocr_extraction import find_report_pages_by_coords_with_grid

pdf_path = "files/pdfs/ABC123_Some_Name_2025-08-20_report.pdf"
(
    dr_page, gl_page,
    dr_result, dr_qual,
    gl_result, vcdr_rt, vcdr_lt, gl_qual
) = find_report_pages_by_coords_with_grid(pdf_path)

print(dr_page, gl_page, dr_result, dr_qual, gl_result, vcdr_rt, vcdr_lt, gl_qual)
```

---

## 6) Integration with Your Database Models

This module **does not write to DB**. It returns strings you can persist with your SQLAlchemy models defined in `models.py`.

### Suggested persistence flow (in your PDF processor):

* Identify the `PatientEncounters` row for this PDF (you already create an `EncounterFile` with `file_type='pdf'` during ZIP processing).
* Create and attach `DiabeticRetinopathyReport` and/or `GlaucomaReport` rows when content is found.
* Optionally mark the corresponding `EncounterFile.ocr_processed = True`.

**Example snippet:**

```python
# assumes: session, patient_encounter (loaded), and pdf_filename already known
(
    dr_page, gl_page,
    dr_result, dr_qual,
    gl_result, vcdr_rt, vcdr_lt, gl_qual
) = find_report_pages_by_coords_with_grid(pdf_full_path)

from models import DiabeticRetinopathyReport, GlaucomaReport, EncounterFile

if dr_page is not None:
    session.add(DiabeticRetinopathyReport(
        patient_encounter_id=patient_encounter.id,
        result=(dr_result or "").strip(),
        qualitative_result=(dr_qual or "").strip(),
        report_file_name=pdf_filename,
    ))

if gl_page is not None:
    session.add(GlaucomaReport(
        patient_encounter_id=patient_encounter.id,
        vcdr_right=(vcdr_rt or "").strip(),
        vcdr_left=(vcdr_lt or "").strip(),
        result=(gl_result or "").strip(),
        qualitative_result=(gl_qual or "").strip(),
        report_file_name=pdf_filename,
    ))

# mark file OCRed
ef = session.query(EncounterFile).filter_by(
    patient_encounter_id=patient_encounter.id, filename=pdf_filename
).first()
if ef:
    ef.ocr_processed = True

session.commit()
```

---

## 7) Quality & Robustness Tips

* **Tesseract configuration:**
  Add language and PSM/OEM when needed:
  `pytesseract.image_to_string(img, config="--psm 6")`
  If your PDFs are English only: `-l eng`.
* **Preprocessing:**
  For better OCR, consider grayscale/binarization, or sharpening (`ImageOps` / OpenCV) before OCRing each crop.
* **Coordinate drift:**
  If templates vary (different vendors, scaling, or margins), either:

  * Normalize by **percent-of-page** coordinates (convert to pixels after rendering), or
  * Use **text search** on full-page OCR to locate anchors (slower but robust).
* **DPI:**
  300 DPI is a good default. If pages are small/thin fonts, try 400–600 DPI (trade-off: speed & memory).
* **Error handling:**
  The function prints exceptions for open failures; you may wrap calls and log structured errors to your existing logging system.
* **Idempotency:**
  If run twice, ensure your DB layer avoids duplicate report rows per `patient_encounter_id` & `report_file_name` (e.g., upsert semantics).

---

## 8) Debugging with Grid Overlays (Optional)

Uncomment the matplotlib block to save `page_{i}_with_grid.png` with a 200-px grid. This helps you map new coordinates by reading approximate `(x, y)` from the axes ticks.

---

## 9) Return Value Contract (for callers)

* On success, returns tuple of 8 elements (strings may be empty or contain trailing whitespace; caller should `.strip()`).
* On PDF open error, returns `(None, None)` (legacy behavior); treat as a hard failure for that file.
* No side effects on disk besides optional debug PNGs (commented out by default).

---

## 10) Common Gotchas

* **Blank outputs** can happen when the crop is slightly off; tune coordinates using the grid overlay.
* **Trailing newlines** from Tesseract → always `.strip()` before storing.
* **VCDR parsing:** If your downstream expects numeric values, add a parser that safely extracts numbers (`re` with tolerances like `0.1–0.99`) and stores both raw & parsed.

---
