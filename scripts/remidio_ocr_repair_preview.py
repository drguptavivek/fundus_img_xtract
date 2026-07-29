"""Preview or repair Remidio AI PDFs that missed DR OCR extraction.

Run this inside the OCR worker because it depends on Tesseract/pytesseract:

    docker compose exec celery-ocr-worker uv run python scripts/remidio_ocr_repair_preview.py --limit 3

Dry-run is the default and prints old attachment OCR vs newly extracted OCR.
Use --apply only after reviewing the preview output:

    docker compose exec celery-ocr-worker uv run python scripts/remidio_ocr_repair_preview.py --limit 50 --apply
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from auth.utils import utcnow
from models import BASE_DIR, PatientEncounters, Session
from encounter_sets.models import EncounterSetAttachment

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")


@dataclass(frozen=True)
class Candidate:
    attachment_id: int
    encounter_id: int
    encounter_uuid: str
    project_id: int | None
    original_filename: str
    pdf_path: Path
    old_ocr: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Maximum candidate PDFs to process. Default: 3.")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many candidates after filtering.")
    parser.add_argument("--project-id", type=int, default=None, help="Only scan one project_id.")
    parser.add_argument("--attachment-id", type=int, action="append", default=[], help="Only process specific attachment IDs.")
    parser.add_argument("--apply", action="store_true", help="Persist new OCR metadata and clinical report rows.")
    parser.add_argument("--jsonl", action="store_true", help="Print one JSON object per candidate instead of readable blocks.")
    parser.add_argument("--verbose-ocr", action="store_true", help="Show raw print output from the OCR extractor.")
    args = parser.parse_args()

    if args.limit < 1:
        raise SystemExit("--limit must be >= 1")
    if args.offset < 0:
        raise SystemExit("--offset must be >= 0")

    session = Session()
    try:
        candidates = find_candidates(
            session,
            limit=args.limit,
            offset=args.offset,
            project_id=args.project_id,
            attachment_ids={int(value) for value in args.attachment_id},
        )
        print(
            f"mode={'APPLY' if args.apply else 'DRY_RUN'} "
            f"limit={args.limit} offset={args.offset} candidates={len(candidates)}"
        )
        for candidate in candidates:
            result = repair_candidate(session, candidate, apply=args.apply, verbose_ocr=args.verbose_ocr)
            if args.jsonl:
                print(json.dumps(result, default=str, sort_keys=True))
            else:
                print_result(result)
        return 0
    finally:
        session.close()


def find_candidates(
    session,
    *,
    limit: int,
    offset: int,
    project_id: int | None,
    attachment_ids: set[int],
) -> list[Candidate]:
    query = (
        session.query(EncounterSetAttachment, PatientEncounters)
        .join(PatientEncounters, EncounterSetAttachment.patient_encounter_id == PatientEncounters.id)
        .filter(
            PatientEncounters.is_set_based.is_(True),
            (EncounterSetAttachment.asset_kind == "pdf") | (EncounterSetAttachment.mime_type == "application/pdf"),
        )
        .order_by(EncounterSetAttachment.id.asc())
    )
    if project_id is not None:
        query = query.filter(PatientEncounters.project_id == project_id)
    if attachment_ids:
        query = query.filter(EncounterSetAttachment.id.in_(attachment_ids))

    candidates: list[Candidate] = []
    skipped = 0
    for attachment, encounter in query.yield_per(100):
        metadata = attachment.metadata_json or {}
        if not _is_remidio_ai_report(metadata):
            continue
        pdf_path = _attachment_path(attachment)
        if not pdf_path.exists():
            continue
        ocr = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        if _has_dr_ocr_data(ocr):
            continue
        if skipped < offset:
            skipped += 1
            continue
        candidates.append(
            Candidate(
                attachment_id=attachment.id,
                encounter_id=encounter.id,
                encounter_uuid=encounter.uuid,
                project_id=encounter.project_id,
                original_filename=attachment.original_filename,
                pdf_path=pdf_path,
                old_ocr=ocr,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def repair_candidate(session, candidate: Candidate, *, apply: bool, verbose_ocr: bool) -> dict[str, Any]:
    old_summary = summarize_ocr(candidate.old_ocr)
    if apply:
        from process_pdfs import process_pdf_for_ocr
        from services.encounter_referral_suggestion import update_encounter_referral_suggestion_from_attachments

        attachment = session.get(EncounterSetAttachment, candidate.attachment_id)
        if attachment is None:
            raise RuntimeError(f"Attachment {candidate.attachment_id} disappeared")
        encounter = session.get(PatientEncounters, candidate.encounter_id)
        if encounter is None:
            raise RuntimeError(f"Encounter {candidate.encounter_id} disappeared")

        upload_date_str = (attachment.created_at or utcnow()).strftime("%Y_%m_%d")
        new_ocr = process_pdf_for_ocr(
            session,
            pdf_path=candidate.pdf_path,
            patient_encounter=encounter,
            upload_date_str=upload_date_str,
        )
        source_report_datetime = (attachment.metadata_json or {}).get("remidio_report_datetime")
        if source_report_datetime:
            new_ocr["source_report_datetime"] = source_report_datetime
        new_ocr["completed_at"] = utcnow().isoformat()
        new_ocr["completed_by_task"] = "scripts.remidio_ocr_repair_preview"

        metadata = dict(attachment.metadata_json or {})
        metadata["ocr"] = new_ocr
        attachment.metadata_json = metadata
        session.add(attachment)
        update_encounter_referral_suggestion_from_attachments(session, attachment.patient_encounter_id)
        session.commit()
    else:
        from ocr_extraction import find_report_pages_by_coords_with_grid

        if verbose_ocr:
            ocr_result = find_report_pages_by_coords_with_grid(str(candidate.pdf_path))
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                ocr_result = find_report_pages_by_coords_with_grid(str(candidate.pdf_path))
        new_ocr = ocr_tuple_to_preview(ocr_result)

    return {
        "applied": apply,
        "attachment_id": candidate.attachment_id,
        "encounter_id": candidate.encounter_id,
        "encounter_uuid": candidate.encounter_uuid,
        "project_id": candidate.project_id,
        "filename": candidate.original_filename,
        "pdf_path": str(candidate.pdf_path),
        "old": old_summary,
        "new": summarize_ocr(new_ocr),
    }


def ocr_tuple_to_preview(ocr_result: tuple[Any, ...]) -> dict[str, Any]:
    if len(ocr_result) == 11:
        (
            dr_page,
            amd_page,
            glaucoma_page,
            dr_result,
            dr_qual,
            amd_result,
            amd_qual,
            glaucoma_result,
            vcdr_right,
            vcdr_left,
            glaucoma_qual,
        ) = ocr_result
    elif len(ocr_result) == 10:
        (
            dr_page,
            glaucoma_page,
            dr_result,
            dr_qual,
            amd_result,
            amd_qual,
            glaucoma_result,
            vcdr_right,
            vcdr_left,
            glaucoma_qual,
        ) = ocr_result
        amd_page = dr_page if amd_result or amd_qual else None
    elif len(ocr_result) == 8:
        (
            dr_page,
            glaucoma_page,
            dr_result,
            dr_qual,
            glaucoma_result,
            vcdr_right,
            vcdr_left,
            glaucoma_qual,
        ) = ocr_result
        amd_page = None
        amd_result = amd_qual = None
    elif len(ocr_result) == 2:
        dr_page, glaucoma_page = ocr_result
        amd_page = None
        dr_result = dr_qual = amd_result = amd_qual = None
        glaucoma_result = vcdr_right = vcdr_left = glaucoma_qual = None
    else:
        raise ValueError(f"OCR function returned {len(ocr_result)} values, expected 2, 8, 10, or 11")

    return {
        "status": "preview",
        "dr_report": {
            "detected": dr_page is not None,
            "page": dr_page,
            "dr_data": {"result": _clean(dr_result), "qualitative_result": _clean(dr_qual)},
        },
        "amd_report": {
            "detected": amd_page is not None,
            "page": amd_page,
            "amd_data": {"result": _clean(amd_result), "qualitative_result": _clean(amd_qual)},
        },
        "glaucoma_report": {
            "detected": glaucoma_page is not None,
            "page": glaucoma_page,
            "glaucoma_data": {
                "result": _clean(glaucoma_result),
                "qualitative_result": _clean(glaucoma_qual),
                "vcdr_right": _clean(vcdr_right),
                "vcdr_left": _clean(vcdr_left),
            },
        },
    }


def summarize_ocr(ocr: dict[str, Any]) -> dict[str, Any]:
    dr_report = ocr.get("dr_report") if isinstance(ocr.get("dr_report"), dict) else {}
    amd_report = ocr.get("amd_report") if isinstance(ocr.get("amd_report"), dict) else {}
    glaucoma_report = ocr.get("glaucoma_report") if isinstance(ocr.get("glaucoma_report"), dict) else {}
    dr_data = dr_report.get("dr_data") if isinstance(dr_report.get("dr_data"), dict) else {}
    amd_data = amd_report.get("amd_data") if isinstance(amd_report.get("amd_data"), dict) else {}
    glaucoma_data = glaucoma_report.get("glaucoma_data") if isinstance(glaucoma_report.get("glaucoma_data"), dict) else {}
    return {
        "status": ocr.get("status"),
        "dr": {
            "detected": dr_report.get("detected"),
            "page": dr_report.get("page"),
            "result": _clean(dr_data.get("result")),
            "qualitative_result": _clean(dr_data.get("qualitative_result")),
        },
        "amd": {
            "detected": amd_report.get("detected"),
            "page": amd_report.get("page"),
            "result": _clean(amd_data.get("result")),
            "qualitative_result": _clean(amd_data.get("qualitative_result")),
        },
        "glaucoma": {
            "detected": glaucoma_report.get("detected"),
            "page": glaucoma_report.get("page"),
            "result": _clean(glaucoma_data.get("result")),
            "qualitative_result": _clean(glaucoma_data.get("qualitative_result")),
            "vcdr_right": _clean(glaucoma_data.get("vcdr_right")),
            "vcdr_left": _clean(glaucoma_data.get("vcdr_left")),
        },
    }


def print_result(result: dict[str, Any]) -> None:
    print("\n" + "=" * 96)
    print(
        f"attachment_id={result['attachment_id']} encounter_id={result['encounter_id']} "
        f"encounter_uuid={result['encounter_uuid']} project_id={result['project_id']} applied={result['applied']}"
    )
    print(f"filename={result['filename']}")
    print(f"path={result['pdf_path']}")
    print("-- OLD OCR --")
    print(json.dumps(result["old"], indent=2, sort_keys=True))
    print("-- NEW OCR --")
    print(json.dumps(result["new"], indent=2, sort_keys=True))


def _attachment_path(attachment: EncounterSetAttachment) -> Path:
    return BASE_DIR / (attachment.folder_rel or "") / (attachment.stored_filename or attachment.original_filename)


def _is_remidio_ai_report(metadata: dict[str, Any]) -> bool:
    return bool(metadata.get("remidio_report_id") and metadata.get("remidio_report_type") == "aiReport")


def _has_dr_ocr_data(ocr: dict[str, Any]) -> bool:
    dr_report = ocr.get("dr_report") if isinstance(ocr.get("dr_report"), dict) else {}
    dr_data = dr_report.get("dr_data") if isinstance(dr_report.get("dr_data"), dict) else {}
    return dr_report.get("detected") is True and bool(_clean(dr_data.get("result")))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


if __name__ == "__main__":
    raise SystemExit(main())
