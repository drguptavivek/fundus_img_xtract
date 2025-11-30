"""
Ad-hoc Task Creator routes (stubs): two-step flow using existing search utilities.
Restricted to admin and datamanager roles.
"""
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, abort
from typing import Any
from datetime import timezone
import json
from uuid import uuid4

from models import Session, AdHocTaskCreation, GradingTask, utcnow, Disease
from flask_login import current_user
from auth.roles import roles_required
from utils.imageSearchUtil import search_images_strict, ImageSearchError
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from utils.suitability import check_suitability

# TODO: import role guard, CSRF, and DB context manager per project conventions
# from utils.auth import roles_required
# from utils.db import db_session  # as documented in docs/10-DEVELOP/DB CONTEXT MANAGER.md

bp = Blueprint('ad_hoc_tasks', __name__, url_prefix='/tasks/ad_hoc')


def _allowed_lab_units() -> set[int]:
    allowed = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
    if not allowed:
        abort(403, description="No lab unit access")
    return allowed


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
        allowed_lab_units = _allowed_lab_units()
        q = (
            db.query(AdHocTaskCreation)
            .join(GradingTask, GradingTask.ad_hoc_id == AdHocTaskCreation.id)
            .filter(GradingTask.lab_unit_id.in_(allowed_lab_units))
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
        tasks_q = (
            db.query(GradingTask)
            .filter(GradingTask.ad_hoc_id == b.id, GradingTask.lab_unit_id.in_(allowed_lab_units))
            .all()
        )
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
    page = max(1, int(request.args.get('page', 1)))
    per_page = max(1, min(100, int(request.args.get('per_page', 60))))

    # Reuse same params as /search/images
    args = request.args
    source = (args.get('source') or 'all').strip().lower()
    hospital_id = args.get('hospital_id', type=int)
    lab_unit_id = args.get('lab_unit_id', type=int)
    camera_id = args.get('camera_id', type=int)
    disease_id = args.get('disease_id', type=int)
    area_id = args.get('area_id', type=int)
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

        # Parse dates and booleans like route_search_images does
        from search.route_search_images import _parse_date, _parse_bool_param
        try:
            images, total = search_images_strict(
                db_session=db,
                page=page,
                per_page=per_page,
                hospital_id=hospital_id,
                lab_unit_ids=lab_unit_ids,
                upload_start=_parse_date(upload_start),
                upload_end=_parse_date(upload_end),
                camera_ids=camera_ids,
                disease_ids=disease_ids,
                area_ids=area_ids,
                is_mydriatic=_parse_bool_param(is_mydriatic),
                has_dr_report=_parse_bool_param(has_dr_report),
                has_glaucoma_report=_parse_bool_param(has_glaucoma_report),
                capture_start=_parse_date(capture_start),
                capture_end=_parse_date(capture_end),
                image_type=image_type,
            )
        except ImageSearchError as e:
            return jsonify({'error': str(e), 'items': [], 'total': 0, 'page': page, 'per_page': per_page}), 400

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
    diseases = payload.get('diseases') or []
    max_images = int(payload.get('max_images') or 0)
    filters = payload.get('filters') or {}
    randomize = bool(payload.get('randomize') or False)
    selected_refs = payload.get('selected_image_refs') or []

    # Validate inputs
    if not isinstance(diseases, list) or not all(isinstance(x, int) for x in diseases) or len(diseases) == 0:
        return jsonify({'error': 'diseases must be a non-empty array of ints'}), 400
    if max_images <= 0:
        return jsonify({'error': 'max_images must be > 0'}), 400

    # Fetch candidates using search util, cap to max_images
    page = 1
    per_page = max_images
    # Translate flat filter form into arguments expected by search_images_strict
    # Accept both flat ids and arrays from UI
    def _int_or_none(v: Any) -> int | None:
        try:
            return int(v) if v not in (None, '', 'null', 'None') else None
        except Exception:
            return None

    source = (filters.get('source') or 'all').strip().lower()
    hospital_id = _int_or_none(filters.get('hospital_id'))
    lab_unit_id = _int_or_none(filters.get('lab_unit_id'))
    camera_id = _int_or_none(filters.get('camera_id'))
    disease_id = _int_or_none(filters.get('disease_id'))
    area_id = _int_or_none(filters.get('area_id'))
    is_mydriatic = filters.get('is_mydriatic')
    has_dr_report = filters.get('has_dr_report')
    has_glaucoma_report = filters.get('has_glaucoma_report')
    upload_start = filters.get('upload_start')
    upload_end = filters.get('upload_end')
    capture_start = filters.get('capture_start')
    capture_end = filters.get('capture_end')

    with get_db_session() as db:
        try:
            from search.route_search_images import _parse_date, _parse_bool_param
            images, total = search_images_strict(
                db_session=db,
                page=page,
                per_page=per_page,
                hospital_id=hospital_id,
                lab_unit_ids=[lab_unit_id] if lab_unit_id else None,
                upload_start=_parse_date(upload_start),
                upload_end=_parse_date(upload_end),
                camera_ids=[camera_id] if camera_id else None,
                disease_ids=[disease_id] if disease_id else None,
                area_ids=[area_id] if area_id else None,
                is_mydriatic=_parse_bool_param(is_mydriatic),
                has_dr_report=_parse_bool_param(has_dr_report),
                has_glaucoma_report=_parse_bool_param(has_glaucoma_report),
                capture_start=_parse_date(capture_start),
                capture_end=_parse_date(capture_end),
                image_type=None if source == 'all' else source,
            )
        except ImageSearchError as e:
            return jsonify({'error': str(e), 'hint': 'Invalid search filters'}), 400

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
                    upload_start=_parse_date(upload_start),
                    upload_end=_parse_date(upload_end),
                    camera_ids=[camera_id] if camera_id else None,
                    disease_ids=[disease_id] if disease_id else None,
                    area_ids=[area_id] if area_id else None,
                    is_mydriatic=_parse_bool_param(is_mydriatic),
                    has_dr_report=_parse_bool_param(has_dr_report),
                    has_glaucoma_report=_parse_bool_param(has_glaucoma_report),
                    capture_start=_parse_date(capture_start),
                    capture_end=_parse_date(capture_end),
                    image_type=None if source == 'all' else source,
                )
            except ImageSearchError:
                break
            for img in page_images:
                if len(sampled) >= max_images:
                    break
                tasks_for = set(img.get('tasks_for_diseases_ids') or [])
                available = [d for d in diseases if d not in tasks_for]
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
            available = [d for d in diseases if d not in tasks_for]
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
    # roles_required('admin', 'datamanager')
    payload = request.get_json(silent=True) or {}
    diseases = payload.get('diseases') or []
    max_images = int(payload.get('max_images') or 0)
    filters = payload.get('filters') or {}
    selected_refs = payload.get('selected_image_refs') or []
    randomize = bool(payload.get('randomize') or False)

    if not diseases or max_images <= 0:
        return jsonify({'error': 'Invalid request'}), 400

    # Persist batch record
    # Normalize filters to persist consistent snapshot with batch record
    def _int_or_none(v: Any) -> int | None:
        try:
            return int(v) if v not in (None, '', 'null', 'None') else None
        except Exception:
            return None

    source = (filters.get('source') or 'all').strip().lower()
    filters_norm = {
        'hospital_id': _int_or_none(filters.get('hospital_id')),
        'lab_unit_id': _int_or_none(filters.get('lab_unit_id')),
        'camera_id': _int_or_none(filters.get('camera_id')),
        'disease_id': _int_or_none(filters.get('disease_id')),
        'area_id': _int_or_none(filters.get('area_id')),
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

    with Session() as session:
        batch = AdHocTaskCreation(
            created_by_id=getattr(current_user, 'id', None) or 0,
            created_at=utcnow(),
            diseases_json=json.dumps(diseases),
            max_images=max_images,
            filters_json=json.dumps(filters_norm),
            selected_image_refs_json=json.dumps(selected_refs),
            randomized=(randomize or None),
            remarks=(payload.get('remarks') or None),
        )
        session.add(batch)
        session.flush()

        # Create tasks where eligible, link to batch
        created = 0
        duplicates = 0
        unsuitable = 0
        errors = 0
        refs_to_use = selected_refs
        # If randomize requested and no manual selections, sample server-side across all matches
        if randomize and not refs_to_use:
            # Rebuild search args like preview
            from search.route_search_images import _parse_date, _parse_bool_param
            page = 1
            per_page = min(200, max_images)
            try:
                images, total = search_images_strict(
                    db_session=session,
                    page=page,
                    per_page=per_page,
                    hospital_id=filters_norm.get('hospital_id'),
                    lab_unit_ids=[filters_norm.get('lab_unit_id')] if filters_norm.get('lab_unit_id') else None,
                    upload_start=_parse_date(filters_norm.get('upload_start')),
                    upload_end=_parse_date(filters_norm.get('upload_end')),
                    camera_ids=[filters_norm.get('camera_id')] if filters_norm.get('camera_id') else None,
                    disease_ids=[filters_norm.get('disease_id')] if filters_norm.get('disease_id') else None,
                    area_ids=[filters_norm.get('area_id')] if filters_norm.get('area_id') else None,
                    is_mydriatic=_parse_bool_param(filters_norm.get('is_mydriatic')),
                    has_dr_report=_parse_bool_param(filters_norm.get('has_dr_report')),
                    has_glaucoma_report=_parse_bool_param(filters_norm.get('has_glaucoma_report')),
                    capture_start=_parse_date(filters_norm.get('capture_start')),
                    capture_end=_parse_date(filters_norm.get('capture_end')),
                    image_type=filters_norm.get('image_type'),
                )
            except ImageSearchError:
                images, total = [], 0
            # Simple sampling: reuse preview sampler logic via random pages
            import math, random
            sampled_refs = []
            seen = set()
            total_pages = max(1, math.ceil(max(1, total) / per_page))
            attempts = 0
            while len(sampled_refs) < max_images and attempts < (10 + max_images):
                attempts += 1
                page_pick = random.randint(1, total_pages)
                try:
                    page_images, _ = search_images_strict(
                        db_session=session,
                        page=page_pick,
                        per_page=per_page,
                        hospital_id=filters_norm.get('hospital_id'),
                        lab_unit_ids=[filters_norm.get('lab_unit_id')] if filters_norm.get('lab_unit_id') else None,
                        upload_start=_parse_date(filters_norm.get('upload_start')),
                        upload_end=_parse_date(filters_norm.get('upload_end')),
                        camera_ids=[filters_norm.get('camera_id')] if filters_norm.get('camera_id') else None,
                        disease_ids=[filters_norm.get('disease_id')] if filters_norm.get('disease_id') else None,
                        area_ids=[filters_norm.get('area_id')] if filters_norm.get('area_id') else None,
                        is_mydriatic=_parse_bool_param(filters_norm.get('is_mydriatic')),
                        has_dr_report=_parse_bool_param(filters_norm.get('has_dr_report')),
                        has_glaucoma_report=_parse_bool_param(filters_norm.get('has_glaucoma_report')),
                        capture_start=_parse_date(filters_norm.get('capture_start')),
                        capture_end=_parse_date(filters_norm.get('capture_end')),
                        image_type=filters_norm.get('image_type'),
                    )
                except ImageSearchError:
                    break
                for img in page_images:
                    if len(sampled_refs) >= max_images:
                        break
                    tasks_for = set(img.get('tasks_for_diseases_ids') or [])
                    available = [d for d in diseases if d not in tasks_for]
                    if not available:
                        continue
                    src = (img.get('type') or '').lower()
                    image_id = img.get('direct_image_upload_id') or img.get('encounter_file_id') or img.get('id') or img.get('encounter_id')
                    key = (src, image_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    sampled_refs.append({'source': src, 'id': image_id, 'lab_unit_id': img.get('lab_unit_id') or img.get('lab_unit') or None})
            refs_to_use = sampled_refs

        for ref in refs_to_use[:max_images]:
            src = ref.get('source')
            image_id = ref.get('id')
            lab_unit_id = ref.get('lab_unit_id') or 1
            for d in diseases:
                try:
                    # Only enforce uniqueness: no duplicate task per image+disease
                    if src == 'direct':
                        task = GradingTask(uuid=str(uuid4()), direct_image_upload_id=image_id, disease_id=d, lab_unit_id=lab_unit_id, state='pending', ad_hoc_id=batch.id)
                    else:
                        task = GradingTask(uuid=str(uuid4()), encounter_file_id=image_id, disease_id=d, lab_unit_id=lab_unit_id, state='pending', ad_hoc_id=batch.id)
                    session.add(task)
                    session.flush()
                    created += 1
                except Exception:
                    # Likely uniqueness violation => duplicate
                    session.rollback()
                    duplicates += 1
                    # Reattach batch state
                    session.add(batch)
                    session.flush()
                    continue

        summary = {'created': created, 'duplicates': duplicates, 'unsuitable': unsuitable, 'errors': errors}
        batch.summary_json = json.dumps(summary)
        session.commit()

        return jsonify({'ad_hoc_id': batch.id, 'summary': summary})
