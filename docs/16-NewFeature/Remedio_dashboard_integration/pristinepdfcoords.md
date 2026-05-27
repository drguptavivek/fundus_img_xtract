# PRISTINE PDF First-Page OCR Coordinates

These coordinates are for Remidio PRISTINE ZIP report PDFs. They are tuned from
the samples in `REMIDIO_Samples/PRISTINE_Samples` and apply to the first page
rendered as a `2048 x 1536` image.

Use only page 1 for these PRISTINE PDF metadata fields, even when the report PDF
has multiple pages.

## Coordinate System

- Origin: top-left corner of the rendered page.
- X increases left to right.
- Y increases top to bottom.
- Boxes use `(x1, y1, x2, y2)`.
- Render size: `2048 x 1536`.

If the render size changes, scale coordinates proportionally.

## Fields

| Field | Scope | Coordinates |
| --- | --- | --- |
| Patient name | Patient | `(185, 70, 445, 132)` |
| Patient ID | Patient | `(576, 70, 770, 132)` |
| Age | Patient | `(940, 70, 985, 132)` |
| Gender | Patient | `(990, 70, 1150, 132)` |
| Date | Encounter | `(1240, 70, 1440, 132)` |

## Defaults

For this parser path:

- `camera_type = PRISTINE`
- `source_kind = remidio_zip`
- `report_type = pristine_imaging_report`

## Notes

- Patient name, patient ID, age, and gender are patient metadata.
- Date is encounter metadata.
- The PRISTINE report PDFs observed so far are image-only from normal PDF text
  extraction, so these regions should be OCR crops from the rendered first page.
- The standalone JPG files in the PRISTINE ZIP remain the clinical images. The
  PDF should be stored as a report/document attachment and used to populate
  metadata.
