# FOP PDF OCR Coordinates

These coordinates are for legacy Remidio FOP report PDFs that contain separate
Diabetic Retinopathy and Glaucoma report pages. They are based on the coordinate
grid examples used for the existing FOP OCR flow and the current
`ocr_extraction.py` crop definitions.

## Coordinate System

- Origin: top-left corner of the rendered page.
- X increases left to right.
- Y increases top to bottom.
- Boxes use `(x1, y1, x2, y2)`.
- Render convention: `page.get_pixmap(dpi=300)` in PyMuPDF.
- Observed FOP grid examples are approximately `2500 x 3500` pixels.
- These coordinates follow the existing FOP OCR grid/render convention, not the
  PRISTINE `2048 x 1536` first-page render.

If the render size changes, scale coordinates proportionally or retune with a
grid overlay.

## Existing OCR Extraction Coordinates

Current `ocr_extraction.py` coordinates:

| Purpose | Coordinates |
| --- | --- |
| DR report page detector | `(0, 200, 1200, 400)` |
| DR result text | `(350, 650, 2000, 800)` |
| DR qualitative/warnings text | `(50, 3100, 1600, 3200)` |
| Glaucoma report page detector | `(0, 400, 1200, 600)` |
| Glaucoma result text | `(0, 1550, 2000, 1650)` |
| Glaucoma VCDR right | `(0, 1300, 1000, 1500)` |
| Glaucoma VCDR left | `(1300, 1300, 2200, 1500)` |
| Glaucoma qualitative text | `(50, 3100, 1700, 3200)` |

## Gender Coordinates

Use the report page type to select the gender OCR region:

| Report page type | Field | Scope | Coordinates |
| --- | --- | --- | --- |
| Diabetic Retinopathy report | Gender | Patient | `(1175, 420, 1400, 500)` |
| Glaucoma Screening report | Gender | Patient | `(1275, 850, 1500, 980)` |

## Notes

- The DR and glaucoma page layouts place the patient metadata in different
  vertical bands.
- Gender is patient metadata, not encounter metadata.
- Encounter date should continue to come from the strongest available source for
  the FOP path, currently the ZIP folder name / parsed `PatientEncounters.capture_date_dt`
  unless a future OCR contract supersedes it.
