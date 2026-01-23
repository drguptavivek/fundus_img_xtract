---
title: EXIF Stripping Workflow
description: Technical implementation of metadata removal for image anonymization.
last_updated: 2026-01-23
---
# EXIF Stripping Workflow

This document details how personally identifiable information (PII) is removed from image metadata (EXIF/IPTC/XMP) within the fundus_img_xtract system.

## Overview

The system uses a "pixels-only" reconstruction method to ensure that all sensitive technical metadata is completely stripped from images before they are persisted to the clinical file system. This is a critical security layer that prevents data leakage of patient names, unique device IDs, or GPS coordinates often embedded by medical cameras.

## Implementation Details

The core logic resides in `utils/image_processing.py` within the `strip_exif_data()` function.

### How it works:
1.  **Pixel Extraction**: The raw pixel data is extracted from the source image buffer using PIL's pixel access methods.
2.  **Clean Reconstruction**: A brand-new image object is created using only the extracted pixels and the original image's dimensions/mode.
3.  **Metadata Discard**: Because the new image object is built from scratch, none of the original metadata chunks (EXIF, IPTC, etc.) are carried over.
4.  **Safe Save**: The resulting "clean" image is then saved in the desired format (typically JPEG).

## Trigger Points

EXIF stripping is integrated into all primary image ingestion and modification paths:

### 1. Zip Ingestion (Encounter Files)
In `zip_processor.py`, images are intercepted during extraction from the Zip archive.
-   **Sequence**: Extract Buffer → Strip EXIF → Save to `IMAGE_DIR`.
-   **Security**: The original image from the Zip is never written to the public-facing image directory without being stripped first.

### 2. Direct Uploads
In `direct_uploads/upload.py`, incoming files are processed synchronously.
-   **Sequence**: Receive MultiPart → Strip EXIF → Save Original (`orig`) → Generate Thumbnail.
-   **Impact**: Even the "original" version stored in the system is already metadata-scrubbed.

### 3. Image Editing (Preprocessing)
When a user manually edits an image (crops or masks) in the browser, the resulting save operation in `direct_uploads/save_image.py` re-triggers the stripping logic.
-   **Sequence**: Receive Edited Data → Strip EXIF → Save Edited Variant (`edited`) → Update Metadata Record.
-   **Consistency**: Ensures that even manual modifications maintain the anonymity of the technical metadata.

## Exceptions

### Pre-graded Uploads
In `direct_uploads/pregraded.py`, the system intentionally **skips** the EXIF stripping process.
-   **Reason**: Pre-graded datasets are often derived from historical or external research sources where original technical metadata is required for scientific indexing or cross-referencing.
-   **Security**: These uploads are automatically marked as `verified` and usually originate from trusted sources where metadata has been pre-cleared or is governed by specific research protocols.
-   **Integrity**: Preserving the original file buffer ensures that research-critical tags (like pixel spacing or manufacturer-specific diagnostic metrics) remain intact.

## Verification

You can verify that EXIF data has been stripped by attempting to read it with standard tools (e.g., `exiftool` or `identify -verbose`). A stripped image will contain only the minimal information required to render pixels (dimensions, color space, and compression tags).

> [!IMPORTANT]
> Because even the `orig` variant in the database is stripped, the system does not store the original medical camera metadata at any point for clinical uploads. If such data is needed for research, it must be extracted *before* ingestion or sourced from the original Zip files (which are kept in a separate `PROCESSED_DIR` with restricted access).
