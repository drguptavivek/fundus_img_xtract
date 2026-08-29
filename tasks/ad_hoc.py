"""
Ad-hoc Task Creator routes (stubs): two-step flow using existing search utilities.
Restricted to admin and datamanager roles.
"""
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, abort, current_app
from typing import Any
from datetime import timezone
import json
from uuid import uuid4

from models import AdHocTaskCreation, GradingTask, Disease, LabUnit
from flask_login import current_user
from auth.roles import roles_required
from utils.imageSearchUtil import search_images_strict, ImageSearchError
from db_transaction_manager import get_db_session
from ad_hoc_task_creation import (
    AdHocTaskCreationError,
    CreateAdHocTasksCommand,
    SourceReference,
    allowed_classical_lab_unit_ids,
    authorize_sources,
    create_tasks,
    validate_filter_scope,
    validate_root_diseases,
)
from utils.suitability import check_suitability
from utils.log_sanitize import sanitize_log_value

# TODO: import role guard, CSRF, and DB context manager per project conventions
# from utils.auth import roles_required
# from utils.db import db_session  # as documented in docs/10-DEVELOP/DB CONTEXT MANAGER.md

bp = Blueprint('ad_hoc_tasks', __name__, url_prefix='/tasks/ad_hoc')


def _allowed_lab_units() -> set[int]:
    with get_db_session() as db:
        allowed = set(allowed_classical_lab_unit_ids(db=db, actor=current_user))
        if not allowed:
            abort(403, description="No classical Lab Unit access")
        return allowed


def _int_or_none(value: Any, field: str = "value") -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise AdHocTaskCreationError(f"{field} must be a positive integer.")
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        raise AdHocTaskCreationError(f"{field} must be a positive integer.")
    return int(text)


def _source(value: Any) -> str:
    if value in (None, ""):
        return "all"
    if not isinstance(value, str) or value.strip().lower() not in {"all", "direct", "zip"}:
        raise AdHocTaskCreationError("source must be all, direct, or zip.")
    return value.strip().lower()


@bp.get('')
@roles_required('admin', 'data_manager')
def index():
    # Render with master data for target diseases
    with get_db_session() as db:
        allowed_lab_units = _allowed_lab_units()
        # Master data needed by filters → convert to plain dicts to avoid detached instances
        from models import Hospital, LabUnit, Camera, Area
        diseases = [
            {'id': d.id, 'name': d.name}
            for d in db.query(Disease).order_by(Disease.id).all()
        ]
        hospitals = [
            {'id': h.id, 'name': h.name}
            for h in db.query(Hospital)
            .join(LabUnit, LabUnit.hospital_id == Hospital.id)
            .filter(LabUnit.id.in_(allowed_lab_units))
            .distinct()
            .order_by(Hospital.id)
            .all()
        ]
        # Include hospital name for lab units to match template display
        from sqlalchemy.orm import joinedload
        lab_units = [
            {'id': lu.id, 'name': lu.name, 'hospital_name': (lu.hospital.name if getattr(lu, 'hospital', None) else None)}
            for lu in db.query(LabUnit)
            .options(joinedload(LabUnit.hospital))
            .filter(LabUnit.id.in_(allowed_lab_units))
            .order_by(LabUnit.id)
            .all()
        ]
        cameras = [
            {'id': c.id, 'name': c.name}
            for c in db.query(Camera).order_by(Camera.id).all()
        ]
        areas = [
            {'id': a.id, 'name': a.name}
            for a in db.query(Area).order_by(Area.id).all()
        ]
    default_filters = {
        'source': 'all', 'hospital_id': '', 'lab_unit_id': '', 'upload_start': '', 'upload_end': '',
        'camera_id': '', 'disease_id': '', 'area_id': '', 'is_mydriatic': None,
        'has_dr_report': None, 'has_glaucoma_report': None, 'capture_start': '', 'capture_end': ''
    }
    # Render template within the same session to avoid detached instance errors
    return render_template('tasks/ad_hoc/index.html', diseases=diseases, hospitals=hospitals, lab_units=lab_units, cameras=cameras, areas=areas, filters=default_filters)


@bp.get('/list')
@roles_required('admin', 'data_manager')
def list_batches():
    """List recent Ad-hoc batches with optional focus on a specific batch via ad_hoc_id."""
    ad_hoc_id = request.args.get('ad_hoc_id', type=int)
    with get_db_session() as db:
        from sqlalchemy import exists, or_, select

        allowed_lab_units = _allowed_lab_units()
        unauthorized_task = exists(
            select(GradingTask.id).where(
                GradingTask.ad_hoc_id == AdHocTaskCreation.id,
                or_(
                    GradingTask.project_id.is_not(None),
                    GradingTask.lab_unit_id.is_(None),
                    GradingTask.lab_unit_id.not_in(allowed_lab_units),
                ),
            )
        )
        q = (
            db.query(AdHocTaskCreation)
            .join(GradingTask, GradingTask.ad_hoc_id == AdHocTaskCreation.id)
            .filter(
                GradingTask.lab_unit_id.in_(allowed_lab_units),
                GradingTask.project_id.is_(None),
                ~unauthorized_task,
            )
            .order_by(AdHocTaskCreation.created_at.desc())
        )
        batches = q.distinct().limit(200).all()
        # Build display rows with disease names
        rows: list[dict[str, Any]] = []
        # Collect all disease IDs to resolve in bulk
        all_ids: set[int] = set()
        parsed_by_batch: dict[int, list[int]] = {}
        for b in batches:
            try:
                diseases = json.loads(b.diseases_json) if b.diseases_json else []
            except Exception:
                diseases = []
            parsed_by_batch[b.id] = diseases
            for did in diseases:
                if isinstance(did, int):
                    all_ids.add(did)
        names_by_id = {d.id: d.name for d in db.query(Disease).filter(Disease.id.in_(all_ids or {0})).all()}
        for b in batches:
            try:
                summary = json.loads(b.summary_json) if b.summary_json else {}
            except Exception:
                summary = {}
            diseases = parsed_by_batch.get(b.id, [])
            disease_names = [names_by_id.get(did, str(did)) for did in diseases]
            rows.append({
                'id': b.id,
                'created_at': b.created_at,
                'created_by': getattr(b.creator, 'username', None) if getattr(b, 'creator', None) else None,
                'randomized': b.randomized,
                'remarks': b.remarks,
                'max_images': b.max_images,
                'disease_ids': diseases,
                'disease_names': disease_names,
                'summary': summary,
            })
    # Render template within the same session to avoid detached instance errors
    return render_template('tasks/ad_hoc/list.html', rows=rows, focus_id=ad_hoc_id)


@bp.get('/detail/<int:ad_hoc_id>')
@roles_required('admin', 'data_manager')
def detail(ad_hoc_id: int):
    """Detail view for a single Ad-hoc batch: filters, remarks, diseases, summary."""
    with get_db_session() as db:
        allowed_lab_units = _allowed_lab_units()
        b: AdHocTaskCreation | None = db.query(AdHocTaskCreation).get(ad_hoc_id)
        if not b:
            abort(404, description='Batch not found')
        try:
            filters = json.loads(b.filters_json) if b.filters_json else {}
        except Exception:
            filters = {}
        try:
            summary = json.loads(b.summary_json) if b.summary_json else {}
        except Exception:
            summary = {}
        try:
            disease_ids = json.loads(b.diseases_json) if b.diseases_json else []
        except Exception:
            disease_ids = []
        # Resolve disease names
        names_by_id = {d.id: d.name for d in db.query(Disease).filter(Disease.id.in_(disease_ids or [0])).all()}
        disease_names = [names_by_id.get(did, str(did)) for did in disease_ids]
        # Build a readable filters list (skip nulls)
        pretty_filters = []
        for k, v in (filters or {}).items():
            if v in (None, '', []):
                continue
            pretty_filters.append({'key': k, 'value': v})
        # Serialize batch to plain dict to avoid detached instance in template
        batch_dict = {
            'id': b.id,
            'created_at': b.created_at,
            'created_by': getattr(getattr(b, 'creator', None), 'username', None),
            'randomized': b.randomized,
            'remarks': b.remarks,
            'max_images': b.max_images,
            'disease_ids': disease_ids,
            'disease_names': disease_names,
        }
        # Fetch created tasks for this batch and resolve image UUIDs (ORM joins; uuid for both models)
        from models import Disease as DiseaseModel, LabUnit as LabUnitModel, DirectImageUpload, EncounterFile
        all_batch_tasks = db.query(GradingTask).filter(GradingTask.ad_hoc_id == b.id).all()
        if not all_batch_tasks or any(
            task.project_id is not None or task.lab_unit_id not in allowed_lab_units
            for task in all_batch_tasks
        ):
            abort(403, description="No access to this complete batch")
        tasks_q = all_batch_tasks
        if not tasks_q:
            abort(403, description="No access to this batch")
        # Build lookup maps for disease and lab names
        disease_name_by_id = {d.id: d.name for d in db.query(DiseaseModel).all()}
        lab_name_by_id = {lu.id: lu.name for lu in db.query(LabUnitModel).all()}

        # Load UUIDs via ORM lookups (small N per batch)
        task_rows: list[dict[str, Any]] = []
        for t in tasks_q:
            src = 'direct' if t.direct_image_upload_id is not None else 'zip'
            uuid: str | None = None
            if src == 'direct' and t.direct_image_upload_id:
                di = db.query(DirectImageUpload).get(t.direct_image_upload_id)
                uuid = getattr(di, 'uuid', None) if di else None
            elif src == 'zip' and t.encounter_file_id:
                ef = db.query(EncounterFile).get(t.encounter_file_id)
                uuid = getattr(ef, 'uuid', None) if ef else None
            task_rows.append({
                'id': t.id,
                'type': src,
                'uuid': uuid,
                'disease': disease_name_by_id.get(t.disease_id, str(t.disease_id)),
                'lab_unit': lab_name_by_id.get(t.lab_unit_id, str(t.lab_unit_id)),
                'state': t.state,
            })
    # Render template within the same session to avoid detached instance errors
    return render_template('tasks/ad_hoc/detail.html', batch=batch_dict, disease_names=disease_names, filters=pretty_filters, summary=summary, task_rows=task_rows)


@bp.get('/search')
@roles_required('admin', 'data_manager')
def search():
    try:
        page = _int_or_none(request.args.get('page'), "page") or 1
        per_page = min(100, _int_or_none(request.args.get('per_page'), "per_page") or 60)
    except AdHocTaskCreationError as exc:
        return jsonify({'error': exc.message}), exc.status_code

    # Reuse same params as /search/images
    args = request.args
    try:
        source = _source(args.get('source'))
        hospital_id = _int_or_none(args.get('hospital_id'), "hospital_id")
        lab_unit_id = _int_or_none(args.get('lab_unit_id'), "lab_unit_id")
        camera_id = _int_or_none(args.get('camera_id'), "camera_id")
        disease_id = _int_or_none(args.get('disease_id'), "disease_id")
        area_id = _int_or_none(args.get('area_id'), "area_id")
    except AdHocTaskCreationError as exc:
        return jsonify({'error': exc.message}), exc.status_code
    is_mydriatic = args.get('is_mydriatic')
    has_dr_report = args.get('has_dr_report')
    has_glaucoma_report = args.get('has_glaucoma_report')
    upload_start = args.get('upload_start')
    upload_end = args.get('upload_end')
    capture_start = args.get('capture_start')
    capture_end = args.get('capture_end')

    with get_db_session() as db:
        allowed_lab_unit_ids = _allowed_lab_units()
        if lab_unit_id and lab_unit_id not in allowed_lab_unit_ids:
            abort(403, description='Access denied to this lab unit')
        lab_unit_ids = [lab_unit_id] if lab_unit_id else list(allowed_lab_unit_ids)
        allowed_hospital_ids = {
            hid for hid, in db.query(LabUnit.hospital_id).filter(LabUnit.id.in_(allowed_lab_unit_ids))
            if hid is not None
        }
        if hospital_id and hospital_id not in allowed_hospital_ids:
            abort(403, description='Access denied to this hospital')

        camera_ids = [camera_id] if camera_id else None
        disease_ids = [disease_id] if disease_id else None
        area_ids = [area_id] if area_id else None
        image_type = None if source == 'all' else source
        if image_type == 'zip':
            camera_ids = None
            disease_ids = None
            area_ids = None
            is_mydriatic = None
        elif image_type == 'direct':
            has_dr_report = None
            has_glaucoma_report = None
            capture_start = None
            capture_end = None

        from utils.search_params import parse_bool_param, parse_search_date
        try:
            images, total = search_images_strict(
                db_session=db,
                page=page,
                per_page=per_page,
                hospital_id=hospital_id,
                lab_unit_ids=lab_unit_ids,
                upload_start=parse_search_date(upload_start),
                upload_end=parse_search_date(upload_end),
                camera_ids=camera_ids,
                disease_ids=disease_ids,
                area_ids=area_ids,
                is_mydriatic=parse_bool_param(is_mydriatic),
                has_dr_report=parse_bool_param(has_dr_report),
                has_glaucoma_report=parse_bool_param(has_glaucoma_report),
                capture_start=parse_search_date(capture_start),
                capture_end=parse_search_date(capture_end),
                image_type=image_type,
                classical_only=True,
            )
        except ImageSearchError as e:
            current_app.logger.warning("Search failed: %s", sanitize_log_value(e))
            return jsonify({'error': 'Invalid search parameters', 'items': [], 'total': 0, 'page': page, 'per_page': per_page}), 400

    # images already enriched by search util with IDs; add canonical id key for UI convenience
    enriched: list[dict[str, Any]] = []
    for img in images:
        item = dict(img)
        img_type = (item.get('type') or '').lower()
        if img_type == 'direct':
            item['id'] = item.get('direct_image_upload_id')
        elif img_type == 'zip':
            item['id'] = item.get('encounter_file_id') or item.get('encounter_id')
        enriched.append(item)

    return jsonify({'items': enriched, 'total': total, 'page': page, 'per_page': per_page})


@bp.post('/preview')
@roles_required('admin', 'data_manager')
def preview():
    # CSRF protection via existing middleware; validate payload here.
    payload = request.get_json(silent=True) or {}
    diseases = payload.get('diseases')
    filters = payload.get('filters')
    randomize = payload.get('randomize', False)
    selected_refs = payload.get('selected_image_refs', [])
    try:
        max_images = _int_or_none(payload.get('max_images'), "max_images")
    except AdHocTaskCreationError as exc:
        return jsonify({'error': str(exc)}), exc.status_code

    # Validate inputs
    if not isinstance(diseases, list) or not all(isinstance(x, int) and not isinstance(x, bool) for x in diseases) or len(diseases) == 0:
        return jsonify({'error': 'diseases must be a non-empty array of ints'}), 400
    if max_images is None:
        return jsonify({'error': 'max_images must be > 0'}), 400
    if not isinstance(filters, dict) or not isinstance(randomize, bool) or not isinstance(selected_refs, list):
        return jsonify({'error': 'Invalid preview payload'}), 400

    # Fetch candidates using search util, cap to max_images
    page = 1
    per_page = max_images
    try:
        source = _source(filters.get('source'))
        hospital_id = _int_or_none(filters.get('hospital_id'), "hospital_id")
        lab_unit_id = _int_or_none(filters.get('lab_unit_id'), "lab_unit_id")
        camera_id = _int_or_none(filters.get('camera_id'), "camera_id")
        disease_id = _int_or_none(filters.get('disease_id'), "disease_id")
        area_id = _int_or_none(filters.get('area_id'), "area_id")
    except AdHocTaskCreationError as exc:
        return jsonify({'error': exc.message}), exc.status_code
    is_mydriatic = filters.get('is_mydriatic')
    has_dr_report = filters.get('has_dr_report')
    has_glaucoma_report = filters.get('has_glaucoma_report')
    upload_start = filters.get('upload_start')
    upload_end = filters.get('upload_end')
    capture_start = filters.get('capture_start')
    capture_end = filters.get('capture_end')

    with get_db_session() as db:
        try:
            validate_filter_scope(
                db=db,
                actor=current_user,
                hospital_id=hospital_id,
                lab_unit_id=lab_unit_id,
            )
            validate_root_diseases(db, tuple(diseases))
            if selected_refs:
                authorize_sources(
                    db=db,
                    actor=current_user,
                    references=tuple(
                        SourceReference.from_payload(ref) for ref in selected_refs
                    ),
                )
        except AdHocTaskCreationError as exc:
            return jsonify({"error": exc.message}), exc.status_code
        expanded_diseases = list(diseases)

        try:
            from utils.search_params import parse_bool_param, parse_search_date
            image_type = None if source == 'all' else source
            if image_type == 'zip':
                camera_id = None
                disease_id = None
                area_id = None
                is_mydriatic = None
            elif image_type == 'direct':
                has_dr_report = None
                has_glaucoma_report = None
                capture_start = None
                capture_end = None
            images, total = search_images_strict(
                db_session=db,
                page=page,
                per_page=per_page,
                hospital_id=hospital_id,
                lab_unit_ids=[lab_unit_id] if lab_unit_id else None,
                upload_start=parse_search_date(upload_start),
                upload_end=parse_search_date(upload_end),
                camera_ids=[camera_id] if camera_id else None,
                disease_ids=[disease_id] if disease_id else None,
                area_ids=[area_id] if area_id else None,
                is_mydriatic=parse_bool_param(is_mydriatic),
                has_dr_report=parse_bool_param(has_dr_report),
                has_glaucoma_report=parse_bool_param(has_glaucoma_report),
                capture_start=parse_search_date(capture_start),
                capture_end=parse_search_date(capture_end),
                image_type=image_type,
                user_id=current_user.id,
                classical_only=True,
            )
        except ImageSearchError as e:
            current_app.logger.warning("Preview search failed: %s", sanitize_log_value(e))
            return jsonify({'error': 'Invalid search filters', 'hint': 'Invalid search filters'}), 400

    # Determine eligibility: exclude images that already have a task for selected diseases
    def _build_meta(img: dict[str, Any]) -> dict[str, Any]:
        return {
            'camera': img.get('camera') or img.get('camera_name'),
            'hospital': img.get('hospital') or img.get('hospital_name'),
            'lab_unit': img.get('lab_unit') or img.get('lab_unit_name'),
            'capture_date': img.get('capture_date'),
            'upload_date': img.get('upload_date'),
            'tasks': img.get('tasks_for_diseases'),
            'area': img.get('area') or img.get('area_name'),
            'disease': img.get('disease'),
            'source': img.get('type'),
            'uploader': img.get('uploader'),
            'ai_diseases': img.get('ai_diseases'),
        }

    candidates: list[dict[str, Any]] = []
    duplicates = 0
    # If randomize requested and no manual selections, sample across all matches by drawing random pages
    if randomize and not selected_refs:
        # Gather across random pages until filled or exhausted
        import math, random
        sampled: list[dict[str, Any]] = []
        seen_ids: set[tuple[str, int | None]] = set()
        # conservative cap on attempts
        max_attempts = 10 + max_images
        attempts = 0
        while len(sampled) < max_images and attempts < max_attempts:
            attempts += 1
            # draw a random page index from 1..ceil(total/per_page)
            total_pages = max(1, math.ceil(max(1, total) / per_page))
            page_pick = random.randint(1, total_pages)
            try:
                page_images, _ = search_images_strict(
                    db_session=db,
                    page=page_pick,
                    per_page=per_page,
                    hospital_id=hospital_id,
                    lab_unit_ids=[lab_unit_id] if lab_unit_id else None,
                    upload_start=parse_search_date(upload_start),
                    upload_end=parse_search_date(upload_end),
                    camera_ids=[camera_id] if camera_id else None,
                    disease_ids=[disease_id] if disease_id else None,
                    area_ids=[area_id] if area_id else None,
                    is_mydriatic=parse_bool_param(is_mydriatic),
                    has_dr_report=parse_bool_param(has_dr_report),
                    has_glaucoma_report=parse_bool_param(has_glaucoma_report),
                    capture_start=parse_search_date(capture_start),
                    capture_end=parse_search_date(capture_end),
                        image_type=None if source == 'all' else source,
                        user_id=current_user.id,
                        classical_only=True,
                    )
            except ImageSearchError as exc:
                current_app.logger.warning(
                    "Randomized ad-hoc preview failed: %s",
                    sanitize_log_value(exc),
                )
                return jsonify({'error': 'Unable to complete randomized preview'}), 400
            for img in page_images:
                if len(sampled) >= max_images:
                    break
                tasks_for = set(img.get('tasks_for_diseases_ids') or [])
                available = [d for d in expanded_diseases if d not in tasks_for]
                if not available:
                    continue
                src = (img.get('type') or '').lower()
                img_id = img.get('direct_image_upload_id') or img.get('encounter_file_id') or img.get('id') or img.get('encounter_id')
                key = (src, int(img_id) if isinstance(img_id, (int,)) or (isinstance(img_id, str) and img_id.isdigit()) else None)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                meta = _build_meta(img)
                sampled.append({
                    'uuid': img.get('uuid'),
                    'type': img.get('type'),
                    'available_diseases': available,
                    'lab_unit_id': img.get('lab_unit_id') or img.get('lab_unit') or None,
                    'id': img_id,
                    'meta': meta,
                })
        candidates = sampled
    else:
        for img in images:
            tasks_for = set(img.get('tasks_for_diseases_ids') or [])
            available = [d for d in expanded_diseases if d not in tasks_for]
            if available:
                meta = _build_meta(img)
                candidates.append({
                    'uuid': img.get('uuid'),
                    'type': img.get('type'),
                    'available_diseases': available,
                    'lab_unit_id': img.get('lab_unit_id') or img.get('lab_unit') or None,
                    'id': img.get('direct_image_upload_id') or img.get('encounter_file_id') or img.get('id') or img.get('encounter_id'),
                    'meta': meta,
                })
            else:
                duplicates += 1

    eligible_count = len(candidates)
    return jsonify({'eligible_count': eligible_count, 'candidates': candidates[:max_images], 'summary': {'duplicates': duplicates, 'unsuitable': 0}})


@bp.post('/create')
@roles_required('admin', 'data_manager')
def create():
    payload = request.get_json(silent=True) or {}
    filters = payload.get('filters')
    if not isinstance(filters, dict):
        return jsonify({'error': 'filters must be an object'}), 400
    try:
        source = _source(filters.get('source'))
        filters_norm = {
        'hospital_id': _int_or_none(filters.get('hospital_id'), "hospital_id"),
        'lab_unit_id': _int_or_none(filters.get('lab_unit_id'), "lab_unit_id"),
        'camera_id': _int_or_none(filters.get('camera_id'), "camera_id"),
        'disease_id': _int_or_none(filters.get('disease_id'), "disease_id"),
        'area_id': _int_or_none(filters.get('area_id'), "area_id"),
        'is_mydriatic': filters.get('is_mydriatic') or None,
        'has_dr_report': filters.get('has_dr_report') or None,
        'has_glaucoma_report': filters.get('has_glaucoma_report') or None,
        'upload_start': filters.get('upload_start') or None,
        'upload_end': filters.get('upload_end') or None,
        'capture_start': filters.get('capture_start') or None,
        'capture_end': filters.get('capture_end') or None,
        'image_type': (None if source == 'all' else source),
        'source': source,
        }
    except AdHocTaskCreationError as exc:
        return jsonify({'error': exc.message}), exc.status_code
    if filters_norm.get('image_type') == 'zip':
        filters_norm['camera_id'] = None
        filters_norm['disease_id'] = None
        filters_norm['area_id'] = None
        filters_norm['is_mydriatic'] = None
    elif filters_norm.get('image_type') == 'direct':
        filters_norm['has_dr_report'] = None
        filters_norm['has_glaucoma_report'] = None
        filters_norm['capture_start'] = None
        filters_norm['capture_end'] = None
    refs_to_use = payload.get('selected_image_refs') or []
    randomize = payload.get('randomize', False)
    try:
        max_images = int(payload.get('max_images'))
    except (TypeError, ValueError):
        max_images = 0

    with get_db_session() as db:
        try:
            validate_filter_scope(
                db=db,
                actor=current_user,
                hospital_id=filters_norm.get('hospital_id'),
                lab_unit_id=filters_norm.get('lab_unit_id'),
            )
        except AdHocTaskCreationError as exc:
            return jsonify({'error': exc.message}), exc.status_code
        if randomize is True and not refs_to_use and max_images > 0:
            from random import sample
            from utils.search_params import parse_bool_param, parse_search_date

            try:
                images, _ = search_images_strict(
                    db_session=db,
                    page=1,
                    per_page=min(1000, max(100, max_images * 10)),
                    hospital_id=filters_norm.get('hospital_id'),
                    lab_unit_ids=[filters_norm['lab_unit_id']] if filters_norm.get('lab_unit_id') else None,
                    upload_start=parse_search_date(filters_norm.get('upload_start')),
                    upload_end=parse_search_date(filters_norm.get('upload_end')),
                    camera_ids=[filters_norm['camera_id']] if filters_norm.get('camera_id') else None,
                    disease_ids=[filters_norm['disease_id']] if filters_norm.get('disease_id') else None,
                    area_ids=[filters_norm['area_id']] if filters_norm.get('area_id') else None,
                    is_mydriatic=parse_bool_param(filters_norm.get('is_mydriatic')),
                    has_dr_report=parse_bool_param(filters_norm.get('has_dr_report')),
                    has_glaucoma_report=parse_bool_param(filters_norm.get('has_glaucoma_report')),
                    capture_start=parse_search_date(filters_norm.get('capture_start')),
                    capture_end=parse_search_date(filters_norm.get('capture_end')),
                    image_type=filters_norm.get('image_type'),
                    user_id=current_user.id,
                    classical_only=True,
                )
            except (ImageSearchError, ValueError):
                return jsonify({'error': 'Invalid search filters'}), 400
            candidates = [
                {
                    'source': (image.get('type') or '').lower(),
                    'id': image.get('direct_image_upload_id') or image.get('encounter_file_id'),
                }
                for image in images
                if image.get('direct_image_upload_id') or image.get('encounter_file_id')
            ]
            refs_to_use = sample(candidates, min(max_images, len(candidates)))

        try:
            command = CreateAdHocTasksCommand.from_payload(
                disease_ids=payload.get('diseases'),
                references=refs_to_use,
                max_images=payload.get('max_images'),
                filters=filters_norm,
                randomize=randomize,
                remarks=payload.get('remarks'),
            )
            result = create_tasks(db=db, actor=current_user, command=command)
        except AdHocTaskCreationError as exc:
            return jsonify({'error': exc.message}), exc.status_code

        summary = {'created': result.created, 'duplicates': 0, 'unsuitable': 0, 'errors': 0}
        return jsonify({'ad_hoc_id': result.batch_id, 'summary': summary})
