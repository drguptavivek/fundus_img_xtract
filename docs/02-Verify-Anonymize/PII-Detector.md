---
title: PII Detector (OCR)
description: Automated detection of patient identifiers in medical image overlays.
last_updated: 2026-01-23
---
# PII Detector (OCR)

## Purpose
The PII detector scans the top-left region of each image for text overlays that may contain patient identifiers (name, ID, date, etc.). It runs automatically on demand (OCR) and stores results in the database for reuse.

## Where It Runs
- Dataset curation screen (PII badges) via `/api/ocr/pii/*`
- Anonymize image page via OCR overlay + manual override
- Direct upload edit page via OCR overlay

## Background Triggers (Async)
The system automatically enqueues PII detection jobs for new images to ensure they are pre-scanned before manual verification:
- **Zip Ingestion**: `zip_processor.py` enqueues detection for every extracted JPG/JPEG.
- **Direct Uploads**: `direct_uploads/upload.py` enqueues detection for the `orig` variant immediately upon receipt.
- **Image Editing**: `direct_uploads/save_image.py` enqueues a new detection job for the `edited` variant after any modification.

## Exceptions
### Pre-graded Uploads
In `direct_uploads/pregraded.py`, the system currently **skips** the automated PII detection enqueueing.
- **Reason**: Similar to EXIF stripping, pre-graded data is often assumed to be pre-cleared or legacy data where automated scanning is not required by the source.
- **Security**: This is tracked as a deficiency in [pii_detection_pregraded_fix.md](file:///Users/vivekgupta/workspace/fundus_img_xtract/TODO/pii_detection_pregraded_fix.md).

## ROI (Region of Interest)
The detector only inspects a small ROI in the top-left corner:
- `roi_height_ratio = 0.20`
- `roi_width_ratio = 0.30`

If the ROI is larger than `max_roi_dim = 1200`, it is scaled down before OCR.

## OCR Preprocessing
Multiple preprocessing strategies are used on the ROI, including:
- Adaptive threshold
- Histogram equalization + binary
- Inverted binary
- CLAHE
- Edge detection

Each preprocessed image is passed through Tesseract with multiple configs:
- `--psm 6 --oem 3`
- `--psm 11 --oem 3`
- `--psm 12 --oem 3`
- `--psm 7 --oem 3`

Timeout per OCR pass: **20 seconds** (`tesseract_timeout_seconds`).

## Detection Rules
We compute:
- **valid_detections**: OCR snippets with confidence > 50 and length ≥ 2.
- **pattern_matches**: valid detections that match PII-like patterns.

PII-like patterns include:
- Digits (≥ 4) or mixed alphanumeric strings
- Keywords: `OD`, `OS`, `NAME`, `ID`, `DATE`, `DOB`, `AGE`
- Strings with both letters and digits

Status is set as:

```
has_text = valid_detections >= 1
has_patterns = pattern_matches > 0
is_pii = (has_text_structure AND has_text) OR has_patterns
status = detected | clear
```

`has_text_structure` is a simple heuristic for text-like structure within the ROI.

## Stored Results
All OCR runs store results in `image_pii_verifications`:
- `pii_status`: detected | clear | error
- `source`: auto | manual
- `detections_json`: OCR box data (text, confidence, bounding boxes)
- `roi_json`: ROI box metadata

## Manual Override
In the anonymize page, reviewers can manually set status to **clear** or **detected**. This writes:
- `source = manual`
- `pii_status = clear|detected`

Manual overrides **block auto OCR** for the image until the user clicks **OCR Redetect**.

## UI Behavior
- **Refresh PII status** pulls stored DB results (no OCR run).
- **Redetect** forces OCR and updates stored results.
- **Pending** means no row exists in `image_pii_verifications` for that image + variant.

## Troubleshooting
- False positives often come from small alphanumeric overlays.
- Increase `min_confidence` or tighten `pattern_matches` to reduce false positives.
- Use the OCR overlay to inspect the detected text and bounding boxes.
