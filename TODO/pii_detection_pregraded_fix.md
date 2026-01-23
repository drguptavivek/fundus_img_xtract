# Issue: Missing PII Detection Trigger in Pre-graded Upload Route

## Description
The pre-graded upload route (`direct_uploads/pregraded.py`) currently does not enqueue asynchronous PII detection jobs. This is inconsistent with the Zip Ingestion and Direct Upload workflows, where images are automatically queued for OCR scanning upon receipt.

## Impact
Images uploaded via the pre-graded route are not automatically scanned for PII. While these images are intended to be "pre-graded" and "pre-cleared," the lack of an automated safety scan represents a gap in the system's anonymization defense-in-depth, especially if the source datasets are not perfectly cleaned.

## Proposed Fix
1.  Import `enqueue_pii_detection` from `utils.pii_detection_queue` (or the relevant utility) into `direct_uploads/pregraded.py`.
2.  Inside the loop where `DirectImageUpload` records are created, call the enqueue function for the new image.
3.  Ensure that this trigger is only called for unique images (not duplicates that were moved to the dup directory).

## Location
-   **File**: `direct_uploads/pregraded.py`
-   **Logic**: After `db_session.add(direct_upload)` and `db_session.flush()` (enabling access to the image ID/UUID).

## Status
- [ ] Implement `enqueue_pii_detection` call in `pregraded.py`
- [ ] Verify PII status correctly transitions from `pending` to `clear`/`detected` for pre-graded images.
- [ ] Update `docs/02-Verify-Anonymize/PII-Detector.md` to remove from "Exceptions".
