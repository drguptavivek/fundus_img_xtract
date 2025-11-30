"""Routes for search images."""

from __future__ import annotations

from datetime import datetime, date as _date, time, timezone
from typing import Any, List, Optional

from flask import current_app, render_template, request, url_for, flash, redirect
from flask_login import current_user
from auth.roles import roles_required

from . import bp
from models import (
    Area,
    Camera,
    Disease,
    Hospital,
    LabUnit,
    DirectImageUpload,
)
from sqlalchemy.orm import joinedload
from utils.imageSearchUtil import search_images_strict, ImageSearchError
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
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
@roles_required(
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
)
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
    
    # Parse date filters
    upload_start = _parse_date(request.args.get("upload_start"))
    upload_end = _parse_date(request.args.get("upload_end"))
    capture_start = _parse_date(request.args.get("capture_start"))
    capture_end = _parse_date(request.args.get("capture_end"))

    page = max(1, page)
    per_page = current_app.config.get("ANALYTICS_SEARCH_IMAGES_PAGE_SIZE", 50)
    per_page = per_page if isinstance(per_page, int) and per_page > 0 else 50

    with get_db_session() as db:
        # Check user permissions for lab unit access (no admin override)
        allowed_lab_unit_ids = set(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return redirect(url_for("home.index"))
        allowed_hospital_ids = {
            hid
            for hid, in db.query(LabUnit.hospital_id).filter(LabUnit.id.in_(allowed_lab_unit_ids))
            if hid is not None
        }

        # Prepare filter parameters for the search_images function
        lab_unit_ids = None
        if lab_unit_id:
            if lab_unit_id not in allowed_lab_unit_ids:
                from flask import abort
                abort(403, description="Access denied to this lab unit")
            lab_unit_ids = [lab_unit_id]
        else:
            lab_unit_ids = list(allowed_lab_unit_ids)

        if hospital_id and hospital_id not in allowed_hospital_ids:
            from flask import abort
            abort(403, description="Access denied to this hospital")
        
        # Convert single IDs to lists for the search function
        camera_ids = [camera_id] if camera_id else None
        disease_ids = [disease_id] if disease_id else None
        area_ids = [area_id] if area_id else None
        
        # Convert source to image_type
        image_type = None if source == "all" else source
        
        # Use the new search_images_strict function with improved filter separation
        try:
            # Debug logging for pagination
            import logging
            debug_logger = logging.getLogger("pagination_debug")
            debug_logger.info(f"Search request - Page: {page}, Per page: {per_page}")
            debug_logger.info(f"Filters - source: {source}, hospital_id: {hospital_id}, lab_unit_id: {lab_unit_id}")
            debug_logger.info(f"Boolean filters - is_mydriatic: {is_mydriatic}, has_dr_report: {has_dr_report}, has_glaucoma_report: {has_glaucoma_report}")
            
            images, total = search_images_strict(
                db_session=db,
                page=page,
                per_page=per_page,
                hospital_id=hospital_id,
                lab_unit_ids=lab_unit_ids,
                upload_start=upload_start,
                upload_end=upload_end,
                # Direct image filters
                camera_ids=camera_ids,
                disease_ids=disease_ids,
                area_ids=area_ids,
                is_mydriatic=is_mydriatic,
                # ZIP image filters
                has_dr_report=has_dr_report,
                has_glaucoma_report=has_glaucoma_report,
                capture_start=capture_start,
                capture_end=capture_end,
                # Additional options
                search_query=search_query,
                user_id=current_user.id,  # Explicit user ID for scoping
                image_type=image_type  # Pass the source parameter to restrict search scope
            )
            
            debug_logger.info(f"Search results - Total: {total}, Images returned: {len(images)}")
            debug_logger.info(f"Total pages calculated: {max(1, (total + per_page - 1) // per_page) if total else 1}")
            
        except ImageSearchError as e:
            # Handle filter conflicts and other search errors gracefully
            from flask import flash
            flash(f"Search error: {str(e)}", "error")
            images, total = [], 0
        
        # Convert image data to the format expected by the template
        records = []
        for img in images:
            # Debug logging for first few images
            if len(records) < 3:
                import logging
                runtime_logger = logging.getLogger("runtime_debug")
                runtime_logger.info(f"Image {img.get('uuid')}: has_dr_report = {img.get('has_dr_report')}")
                runtime_logger.info(f"Image {img.get('uuid')}: has_glaucoma_report = {img.get('has_glaucoma_report')}")
                runtime_logger.info(f"Image {img.get('uuid')}: has_reports = {img.get('has_reports', {})}")
                runtime_logger.info(f"Image {img.get('uuid')}: type = {img.get('type')}")
            
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
                "encounter_id": img.get("encounter_id"), # Include encounter ID for ZIP images
                # Fix DR report mapping - use direct fields for ZIP images, fallback to has_reports for direct images
                "has_dr": img.get("has_dr_report", img.get("has_reports", {}).get("DR", False)),
                "has_glaucoma": img.get("has_glaucoma_report", img.get("has_reports", {}).get("Glaucoma", False)),
                "is_mydriatic": img.get("is_mydriatic"),
                "view_url": None,  # Will be set below
                "uploader": img.get("uploader"),  # Include uploader information for direct images
                "file_hash": img.get("file_hash"),  # Include file hash for direct images
                "tasks_for_diseases": img.get("tasks_for_diseases", []),  # Include task disease information
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
        
        lab_unit_objs = (
            db.query(LabUnit)
            .options(joinedload(LabUnit.hospital))
            .filter(LabUnit.id.in_(list(allowed_lab_unit_ids)))
            .order_by(LabUnit.name)
            .all()
        )
        hospital_ids = [lu.hospital_id for lu in lab_unit_objs if lu.hospital_id]
        hospital_objs = (
            db.query(Hospital)
            .options(joinedload(Hospital.lab_units))
            .filter(Hospital.id.in_(hospital_ids))
            .order_by(Hospital.name)
            .all()
        )
        camera_objs = (
            db.query(Camera)
            .join(DirectImageUpload, DirectImageUpload.camera_id == Camera.id)
            .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Camera.name)
            .all()
        )
        disease_objs = (
            db.query(Disease)
            .join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id)
            .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Disease.name)
            .all()
        )
        area_objs = (
            db.query(Area)
            .join(DirectImageUpload, DirectImageUpload.area_id == Area.id)
            .filter(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids))
            .distinct()
            .order_by(Area.name)
            .all()
        )
        
        # Convert SQLAlchemy objects to dictionaries to prevent DetachedInstanceError
        hospitals = [{"id": h.id, "name": h.name} for h in hospital_objs]
        lab_units = [{"id": lu.id, "name": lu.name, "hospital_name": lu.hospital.name if lu.hospital else None} for lu in lab_unit_objs]
        cameras = [{"id": c.id, "name": c.name} for c in camera_objs]
        diseases_all = [{"id": d.id, "name": d.name} for d in disease_objs]
        areas = [{"id": a.id, "name": a.name} for a in area_objs]



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
        "is_mydriatic": is_mydriatic,
        "search_query": request.args.get("search_query", ""),
        "has_dr_report": has_dr_report,
        "has_glaucoma_report": has_glaucoma_report,
    }

    def _filter_kwargs(target_page: int) -> dict[str, Any]:
        params: dict[str, Any] = {"page": target_page}
        # Include all filter parameters to maintain state in pagination
        # This ensures filters are preserved when navigating between pages
        for key, value in filter_params.items():
            # Only include boolean parameters if they have an actual value (True or False)
            if key in ["has_dr_report", "has_glaucoma_report", "is_mydriatic"]:
                if value is not None:
                    params[key] = str(value).lower()
            # For search_query, only include if it has a value
            elif key == "search_query":
                if value:
                    params[key] = value
            # Include all other parameters as empty strings if not set
            else:
                params[key] = value if value is not None else ""
        return params

    prev_url = url_for("search.search_images_route", **_filter_kwargs(page - 1)) if page > 1 else None
    next_url = url_for("search.search_images_route", **_filter_kwargs(page + 1)) if page < total_pages else None

    # Calculate serial numbers for each record
    start_serial = (page - 1) * per_page + 1
    for idx, record in enumerate(records):
        record['sr_no'] = start_serial + idx

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
