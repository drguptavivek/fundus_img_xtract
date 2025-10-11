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
    Session as DBSession,
)
from utils.imageSearchUtil import search_images
from utils.upload_eligibility import get_user_lab_unit_ids


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

    # Parse date filters
    upload_start = _parse_date(request.args.get("upload_start"))
    upload_end = _parse_date(request.args.get("upload_end"))
    capture_start = _parse_date(request.args.get("capture_start"))
    capture_end = _parse_date(request.args.get("capture_end"))

    page = max(1, page)
    per_page = current_app.config.get("ANALYTICS_SEARCH_IMAGES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    db = DBSession()
    try:
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
            search_query=search_query
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
                "record_date": img.get("created_at"),
                "created_at": img.get("created_at"),
                "capture_date": None,  # Not available in the search_images function
                "encounter_id": None,  # Not available in the search_images function
                "has_dr": img.get("has_tasks", {}).get("Diabetic Retinopathy", False),
                "has_glaucoma": img.get("has_tasks", {}).get("Glaucoma", False),
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
        if is_admin_like:
            hospitals = db.query(Hospital).order_by(Hospital.name).all()
            lab_units = db.query(LabUnit).order_by(LabUnit.name).all()
            cameras = db.query(Camera).order_by(Camera.name).all()
            diseases_all = db.query(Disease).order_by(Disease.name).all()
            areas = db.query(Area).order_by(Area.name).all()
        else:
            lab_units = (
                db.query(LabUnit)
                .filter(LabUnit.id.in_(list(user_lab_unit_ids)))
                .order_by(LabUnit.name)
                .all()
            )
            # Get hospitals for the allowed lab units
            hospital_ids = [lu.hospital_id for lu in lab_units]
            hospitals = (
                db.query(Hospital)
                .filter(Hospital.id.in_(hospital_ids))
                .order_by(Hospital.name)
                .all()
            )
            # For other filters, we'll still fetch them all but only show data from allowed lab units
            cameras = db.query(Camera).order_by(Camera.name).all()
            diseases_all = db.query(Disease).order_by(Disease.name).all()
            areas = db.query(Area).order_by(Area.name).all()

    finally:
        db.close()

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
    )