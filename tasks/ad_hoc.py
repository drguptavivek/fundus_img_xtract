"""
Ad-hoc Task Creator routes (stubs): two-step flow using existing search utilities.
Restricted to admin and datamanager roles.
"""
from __future__ import annotations

from flask import Blueprint, render_template, request, jsonify, abort
from typing import Any
from datetime import timezone
import json

from models import Session, AdHocTaskCreation, GradingTask, utcnow, Disease
from flask_login import current_user
from auth.roles import roles_required
from utils.imageSearchUtil import search_images_strict, ImageSearchError
from db_transaction_manager import get_db_session
from utils.upload_eligibility import get_user_lab_unit_ids
from utils.suitability import check_suitability

# TODO: import role guard, CSRF, and DB context manager per project conventions
# from utils.auth import roles_required
# from utils.db import db_session  # as documented in docs/10-DEVELOP/DB CONTEXT MANAGER.md

bp = Blueprint('ad_hoc_tasks', __name__, url_prefix='/tasks/ad_hoc')


@bp.get('')
@roles_required('admin', 'data_manager')
def index():
    # Render with master data for target diseases
    with get_db_session() as db:
        # Master data needed by filters → convert to plain dicts to avoid detached instances
        from models import Hospital, LabUnit, Camera, Area
        diseases = [
            {'id': d.id, 'name': d.name}
            for d in db.query(Disease).order_by(Disease.name).all()
        ]
        hospitals = [
            {'id': h.id, 'name': h.name}
            for h in db.query(Hospital).order_by(Hospital.name).all()
        ]
        # Include hospital name for lab units to match template display
        from sqlalchemy.orm import joinedload
        lab_units = [
            {'id': lu.id, 'name': lu.name, 'hospital_name': (lu.hospital.name if getattr(lu, 'hospital', None) else None)}
            for lu in db.query(LabUnit).options(joinedload(LabUnit.hospital)).order_by(LabUnit.name).all()
        ]
        cameras = [
            {'id': c.id, 'name': c.name}
            for c in db.query(Camera).order_by(Camera.name).all()
        ]
        areas = [
            {'id': a.id, 'name': a.name}
            for a in db.query(Area).order_by(Area.name).all()
        ]
    default_filters = {
        'source': 'all', 'hospital_id': '', 'lab_unit_id': '', 'upload_start': '', 'upload_end': '',
        'camera_id': '', 'disease_id': '', 'area_id': '', 'is_mydriatic': None,
        'has_dr_report': None, 'has_glaucoma_report': None, 'capture_start': '', 'capture_end': ''
    }
    return render_template('tasks/ad_hoc/index.html', diseases=diseases, hospitals=hospitals, lab_units=lab_units, cameras=cameras, areas=areas, filters=default_filters)


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
        user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        is_admin_like = current_user.has_role('admin', 'data_manager', 'optometrist')
        lab_unit_ids = None
        if lab_unit_id:
            if not is_admin_like and lab_unit_id not in user_lab_unit_ids:
                abort(403, description='Access denied to this lab unit')
            lab_unit_ids = [lab_unit_id]
        elif not is_admin_like:
            lab_unit_ids = list(user_lab_unit_ids)

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
    candidates: list[dict[str, Any]] = []
    duplicates = 0
    for img in images:
        tasks_for = set(img.get('tasks_for_diseases_ids') or [])
        available = [d for d in diseases if d not in tasks_for]
        if available:
            candidates.append({
                'uuid': img.get('uuid'),
                'type': img.get('type'),
                'available_diseases': available,
                'lab_unit_id': img.get('lab_unit_id') or img.get('lab_unit') or None,
                'id': img.get('direct_image_upload_id') or img.get('encounter_file_id') or img.get('id') or img.get('encounter_id'),
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

    if not diseases or max_images <= 0 or not selected_refs:
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
        )
        session.add(batch)
        session.flush()

        # Create tasks where eligible, link to batch
        created = 0
        duplicates = 0
        unsuitable = 0
        errors = 0
        for ref in selected_refs[:max_images]:
            src = ref.get('source')
            image_id = ref.get('id')
            lab_unit_id = ref.get('lab_unit_id') or 1
            for d in diseases:
                try:
                    # Only enforce uniqueness: no duplicate task per image+disease
                    if src == 'direct':
                        task = GradingTask(direct_image_upload_id=image_id, disease_id=d, lab_unit_id=lab_unit_id, state='pending', ad_hoc_id=batch.id)
                    else:
                        task = GradingTask(encounter_file_id=image_id, disease_id=d, lab_unit_id=lab_unit_id, state='pending', ad_hoc_id=batch.id)
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
