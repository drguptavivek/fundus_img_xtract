"""Routes for search images."""

from __future__ import annotations

from datetime import datetime, date as _date, time, timezone
from typing import Any, List, Optional

from flask import current_app, render_template, request, url_for
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from models import (
    Area,
    Camera,
    Disease,
    Hospital,
    LabUnit,
)
from sqlalchemy.orm import joinedload
from utils.imageSearchUtil import search_images
from utils.upload_eligibility import get_user_lab_unit_ids
from db_transaction_manager import get_db_session


def _parse_bool_param(value: str | None) -> bool | None:
    """Parse a boolean parameter from request args."""
    if value is None or value == "":
        return None
    lowered = value.strip().lower()
    if lowered in {"all", "any", "*"}:
        return None
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    return None


def _parse_date(value: str | None) -> _date | None:
    """Parse a date parameter from request args."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@bp.route("/images", methods=["GET"])
@bp.route("/images/", methods=["GET"])
@roles_required("admin", "data_manager", "optometrist")
def search_images_route() -> str:
    """Search images using the centralized search_images function from utils.imageSearchUtil."""
    page = request.args.get("page", default=1, type=int) or 1
    source = (request.args.get("source") or "all").strip().lower()
    if source not in {"all", "zip", "direct"}:
        source = "all"

    hospital_id = request.args.get("hospital_id", type=int)
    lab_unit_id = request.args.get("lab_unit_id", type=int)
    camera_id = request.args.get("camera_id", type=int)
    disease_id = request.args.get("disease_id", type=int)
    area_id = request.args.get("area_id", type=int)
    is_mydriatic = _parse_bool_param(request.args.get("is_mydriatic"))
    search_query = request.args.get("search_query", "").strip() or None
    has_dr_report = _parse_bool_param(request.args.get("has_dr_report"))  # Get the DR report filter
    has_glaucoma_report = _parse_bool_param(request.args.get("has_glaucoma_report"))  # Get the Glaucoma report filter
    
    # If disease filter is applied, only show direct images since disease is only applicable to direct uploads
    if disease_id:
        source = "direct"

    # Parse date filters
    upload_start = _parse_date(request.args.get("upload_start"))
    upload_end = _parse_date(request.args.get("upload_end"))
    capture_start = _parse_date(request.args.get("capture_start"))
    capture_end = _parse_date(request.args.get("capture_end"))

    page = max(1, page)
    per_page = current_app.config.get("ANALYTICS_SEARCH_IMAGES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    with get_db_session() as db:
        # Check user permissions for lab unit access
        user_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        is_admin_like = current_user.has_role("admin", "data_manager", "optometrist")
        
        # Prepare filter parameters for the search_images function
        lab_unit_ids = None
        if lab_unit_id:
            if not is_admin_like and lab_unit_id not in user_lab_unit_ids:
                from flask import abort
                abort(403, description="Access denied to this lab unit")
            lab_unit_ids = [lab_unit_id]
        elif not is_admin_like:
            lab_unit_ids = list(user_lab_unit_ids)
        
        # Convert single IDs to lists for the search function
        camera_ids = [camera_id] if camera_id else None
        disease_ids = [disease_id] if disease_id else None
        area_ids = [area_id] if area_id else None
        
        # Convert source to image_type
        image_type = None if source == "all" else source
        
        # Use the centralized search_images function
        images, total = search_images(
            db_session=db,
            page=page,
            per_page=per_page,
            lab_unit_ids=lab_unit_ids,
            disease_ids=disease_ids,
            camera_ids=camera_ids,
            area_ids=area_ids,
            is_mydriatic=is_mydriatic,
            image_type=image_type,
            search_query=search_query,
            upload_start=upload_start,
            upload_end=upload_end,
            capture_start=capture_start,
            capture_end=capture_end,
            hospital_id=hospital_id, # Add hospital filter
            has_dr_report=has_dr_report,  # Add DR report filter
            has_glaucoma_report=has_glaucoma_report  # Add Glaucoma report filter
        )
        
        # Convert image data to the format expected by the template
        records = []
        for img in images:
            # Convert the image dict to match the template format
            record = {
                "uuid": img.get("uuid"),
                "source": img.get("type"),
                "hospital_name": img.get("hospital"),
                "lab_unit_name": img.get("lab_unit"),
                "camera_name": img.get("camera"),
                "disease_name": img.get("disease"),
                "area_name": img.get("area"),
                "record_date": img.get("upload_date"),  # Use new field
                "created_at": img.get("upload_date"),   # Use new field
                "upload_date": img.get("upload_date"),  # New field
                "capture_date": img.get("capture_date"), # Use new field
                "encounter_id": None, # Not available in the search_images function
                "has_dr": img.get("has_reports", {}).get("Diabetic Retinopathy", False),
                "has_glaucoma": img.get("has_reports", {}).get("Glaucoma", False),
                "is_mydriatic": img.get("is_mydriatic"),
                "view_url": None,  # Will be set below
            }
            
            # Set the appropriate view URL based on image type
            if img.get("type") == "direct":
                record["view_url"] = url_for("analytics.view_upload", uuid_str=img.get("uuid"))
            elif img.get("type") == "zip":
                # For ZIP images, we need to find the encounter ID
                # This is a limitation of the current search_images function
                # We would need to modify it to include encounter_id for ZIP images
                record["view_url"] = None
            
            records.append(record)

        # Filter hospitals, lab units, etc. to only show those the user has access to
        # Use joinedload to eagerly load relationships to prevent DetachedInstanceError
        if is_admin_like:
            hospital_objs = db.query(Hospital).options(joinedload(Hospital.lab_units)).order_by(Hospital.name).all()
            lab_unit_objs = db.query(LabUnit).options(joinedload(LabUnit.hospital)).order_by(LabUnit.name).all()
            camera_objs = db.query(Camera).order_by(Camera.name).all()
            disease_objs = db.query(Disease).order_by(Disease.name).all()
            area_objs = db.query(Area).order_by(Area.name).all()
        else:
            lab_unit_objs = (
                db.query(LabUnit)
                .options(joinedload(LabUnit.hospital))
                .filter(LabUnit.id.in_(list(user_lab_unit_ids)))
                .order_by(LabUnit.name)
                .all()
            )
            # Get hospitals for the allowed lab units
            hospital_ids = [lu.hospital_id for lu in lab_unit_objs]
            hospital_objs = (
                db.query(Hospital)
                .options(joinedload(Hospital.lab_units))
                .filter(Hospital.id.in_(hospital_ids))
                .order_by(Hospital.name)
                .all()
            )
            # For other filters, we'll still fetch them all but only show data from allowed lab units
            camera_objs = db.query(Camera).order_by(Camera.name).all()
            disease_objs = db.query(Disease).order_by(Disease.name).all()
            area_objs = db.query(Area).order_by(Area.name).all()
        
        # Convert SQLAlchemy objects to dictionaries to prevent DetachedInstanceError
        hospitals = [{"id": h.id, "name": h.name} for h in hospital_objs]
        lab_units = [{"id": lu.id, "name": lu.name, "hospital_name": lu.hospital.name if lu.hospital else None} for lu in lab_unit_objs]
        cameras = [{"id": c.id, "name": c.name} for c in camera_objs]
        diseases_all = [{"id": d.id, "name": d.name} for d in disease_objs]
        areas = [{"id": a.id, "name": a.name} for a in area_objs]

    # Add logging to validate the DetachedInstanceError hypothesis
    import logging
    runtime_logger = logging.getLogger("runtime_error")
    runtime_logger.info(f"Database session closed, passing {len(hospitals)} hospital dictionaries to template")
    runtime_logger.info(f"Hospital objects type: {type(hospitals[0]) if hospitals else 'No hospitals'}")
    runtime_logger.info(f"First hospital dict: {hospitals[0] if hospitals else 'N/A'}")

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    filter_params = {
        "source": source,
        "hospital_id": hospital_id,
        "lab_unit_id": lab_unit_id,
        "camera_id": camera_id,
        "disease_id": disease_id,
        "area_id": area_id,
        "upload_start": request.args.get("upload_start", ""),
        "upload_end": request.args.get("upload_end", ""),
        "capture_start": request.args.get("capture_start", ""),
        "capture_end": request.args.get("capture_end", ""),
        "is_mydriatic": request.args.get("is_mydriatic", ""),
        "search_query": request.args.get("search_query", ""),
        "has_dr_report": has_dr_report,
        "has_glaucoma_report": has_glaucoma_report,
    }

    def _filter_kwargs(target_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": target_page}
        for key, value in filter_params.items():
            if value:
                params[key] = value
        return params

    prev_url = url_for("search.search_images_route", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("search.search_images_route", **_filter_kwargs(page + 1)) if page < total_pages else None

    return render_template(
        "search/search_images.html",
        rows=records,
        page=page,
        total=total,
        total_pages=total_pages,
        prev_url=prev_url,
        next_url=next_url,
        filters=filter_params,
        hospitals=hospitals,
        lab_units=lab_units,
        cameras=cameras,
        diseases=diseases_all,
        areas=areas,
        api_lab_units_url=url_for("fundus_api.get_lab_units_by_hospital", hospital_id="0")
    )