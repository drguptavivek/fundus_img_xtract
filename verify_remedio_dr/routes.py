from flask import render_template, request, current_app, url_for, redirect, flash
from flask_login import current_user
from sqlalchemy import func
from sqlalchemy.orm import selectinload, joinedload
from datetime import datetime, date as _date

from auth.roles import roles_required
from . import bp

from models import Session, DiabeticRetinopathyReport, PatientEncounters, EncounterFile, utcnow, LabUnit, Disease
from utils.upload_eligibility import get_user_lab_unit_ids
from process_pdfs import DR_PDF_DIR

# Import task creation services
from services.taskCreationServices import ensure_task


@bp.route("/list", methods=["GET"])
@roles_required("admin", "optometrist", "data_manager")
def verify_dr_list():
    """Date-wise pagination: each page shows all reports for one capture_date_dt."""
    page = request.args.get("page", default=1, type=int) or 1
    selected_date = (request.args.get("date") or "").strip() or None
    ver = (request.args.get("ver") or "all").strip().lower()
    if ver not in {"all", "yes", "no"}:
        ver = "all"
    page = max(1, page)

    db = Session()
    try:
        restricted_lab_units = None
        if not (current_user.has_role('admin') or current_user.has_role('data_manager')):
            allowed_lab_units = get_user_lab_unit_ids(current_user.id)
            restricted_lab_units = allowed_lab_units or {-1}

        # Build ordered list of distinct dates with data
        date_query = (
            db.query(PatientEncounters.capture_date_dt)
              .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .distinct()
        )
        if restricted_lab_units is not None:
            date_query = date_query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
        date_rows = date_query.order_by(PatientEncounters.capture_date_dt.desc()).all()
        dates: list[_date] = [r[0] for r in date_rows]

        # Find most recent date that has at least one unverified encounter
        unv_query = (
            db.query(PatientEncounters.capture_date_dt)
              .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .filter(
                  (PatientEncounters.dr_verified_status.is_(None)) |
                  (PatientEncounters.dr_verified_status != 'verified')
              )
              .distinct()
        )
        if restricted_lab_units is not None:
            unv_query = unv_query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
        unv_rows = unv_query.order_by(PatientEncounters.capture_date_dt.desc()).all()
        most_recent_unverified = unv_rows[0][0] if unv_rows else None

        # Find most recent date that has at least one verified encounter
        ver_query = (
            db.query(PatientEncounters.capture_date_dt)
              .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
              .filter(PatientEncounters.capture_date_dt.isnot(None))
              .filter(PatientEncounters.dr_verified_status == 'verified')
              .distinct()
        )
        if restricted_lab_units is not None:
            ver_query = ver_query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
        ver_rows = ver_query.order_by(PatientEncounters.capture_date_dt.desc()).all()
        most_recent_verified = ver_rows[0][0] if ver_rows else None

        total_pages = max(1, len(dates))
        # Determine focused date by selected_date or page index
        focus_idx = 0
        sel_dt: _date | None = None
        if selected_date:
            try:
                sel_dt = datetime.strptime(selected_date, "%Y-%m-%d").date()
            except Exception:
                sel_dt = None
        if sel_dt and sel_dt in dates:
            focus_idx = dates.index(sel_dt)
        else:
            # page is 1-based index over dates
            focus_idx = min(max(1, page), total_pages) - 1

        focus_date = dates[focus_idx] if dates else None
        # Normalize page and selected_date for template/links
        page = focus_idx + 1 if total_pages else 1
        selected_date = focus_date.isoformat() if focus_date else None

        # Recent unverified page index
        recent_unverified_url = None
        if most_recent_unverified and most_recent_unverified in dates:
            ru_idx = dates.index(most_recent_unverified) + 1
            recent_unverified_url = url_for('verify_remedio_dr.verify_dr_list', page=ru_idx, ver='no')

        # Recent verified page index
        recent_verified_url = None
        if most_recent_verified and most_recent_verified in dates:
            rv_idx = dates.index(most_recent_verified) + 1
            recent_verified_url = url_for('verify_remedio_dr.verify_dr_list', page=rv_idx, ver='yes')

        # Pull all reports for the focused date
        if focus_date is not None:
            items_query = (
                db.query(DiabeticRetinopathyReport)
                  .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                  .filter(PatientEncounters.capture_date_dt == focus_date)
                  .order_by(DiabeticRetinopathyReport.id.desc())
                  .options(selectinload(DiabeticRetinopathyReport.patient_encounter))
            )
            if restricted_lab_units is not None:
                items_query = items_query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
            items = items_query.all()
            # Apply verified filter within date
            if ver == "yes":
                items = [dr for dr in items if dr.patient_encounter and dr.patient_encounter.dr_verified_status == 'verified']
            elif ver == "no":
                items = [dr for dr in items if dr.patient_encounter and (dr.patient_encounter.dr_verified_status is None or dr.patient_encounter.dr_verified_status != 'verified')]
        else:
            items = []

        # Build "my recently verified" list (up to 20) for the logged-in user
        my_recent_verified = []
        try:
            from flask_login import current_user as cu
            uname = getattr(cu, 'username', None)
            if uname:
                recent_query = (
                    db.query(DiabeticRetinopathyReport)
                      .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                      .filter(PatientEncounters.dr_verified_status == 'verified')
                      .filter(PatientEncounters.dr_verified_by == uname)
                      .order_by(PatientEncounters.dr_verified_at.desc(), DiabeticRetinopathyReport.id.desc())
                      .options(selectinload(DiabeticRetinopathyReport.patient_encounter))
                      .limit(20)
                )
                if restricted_lab_units is not None:
                    recent_query = recent_query.filter(PatientEncounters.lab_unit_id.in_(restricted_lab_units))
                my_recent_verified = recent_query.all()
        except Exception:
            my_recent_verified = []
    finally:
        db.close()

    has_prev = page > 1
    has_next = page < total_pages

    return render_template(
        "verify_remedio_dr/list.html",
        items=items,
        page=page,
        per_page=len(items),
        total=len(items),
        total_pages=total_pages,
        has_prev=has_prev,
        has_next=has_next,
        prev_url=url_for("verify_remedio_dr.verify_dr_list", page=page-1, ver=ver) if has_prev else None,
        next_url=url_for("verify_remedio_dr.verify_dr_list", page=page+1, ver=ver) if has_next else None,
        selected_date=selected_date,
        ver=ver,
        recent_unverified_url=recent_unverified_url,
        recent_verified_url=recent_verified_url,
        my_recent_verified=my_recent_verified,
    )


@bp.route("/detail/<int:report_id>", methods=["GET"])
@roles_required("admin", "optometrist", "data_manager")
def verify_dr_detail(report_id: int):
    """Detail view aligned to DR list ordering (date desc, id desc).
    Prev/Next follow the report sequence.
    """
    IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp"}

    db = Session()
    try:
        row = (
            db.query(DiabeticRetinopathyReport)
            .options(
                joinedload(DiabeticRetinopathyReport.patient_encounter).joinedload(PatientEncounters.zip_file),
                joinedload(DiabeticRetinopathyReport.patient_encounter).selectinload(PatientEncounters.encounter_files),
                joinedload(DiabeticRetinopathyReport.patient_encounter).selectinload(PatientEncounters.dr_reports),
                joinedload(DiabeticRetinopathyReport.patient_encounter).selectinload(PatientEncounters.glaucoma_reports),
                joinedload(DiabeticRetinopathyReport.patient_encounter).joinedload(PatientEncounters.lab_unit).joinedload(LabUnit.hospital),
            )
            .filter(DiabeticRetinopathyReport.id == report_id)
            .first()
        )
        if not row or not row.patient_encounter:
            from flask import abort
            abort(404)

        enc = row.patient_encounter

        # Compute prev/next by global DR ordering
        d = enc.capture_date_dt
        cur_id = row.id

        prev_row = (
            db.query(DiabeticRetinopathyReport)
            .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
            .filter(
                (
                    PatientEncounters.capture_date_dt > d
                )
                | (
                    (PatientEncounters.capture_date_dt == d)
                    & (DiabeticRetinopathyReport.id > cur_id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.asc(), DiabeticRetinopathyReport.id.asc())
            .first()
        )

        next_row = (
            db.query(DiabeticRetinopathyReport)
            .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
            .filter(
                (
                    PatientEncounters.capture_date_dt < d
                )
                | (
                    (PatientEncounters.capture_date_dt == d)
                    & (DiabeticRetinopathyReport.id < cur_id)
                )
            )
            .order_by(PatientEncounters.capture_date_dt.desc(), DiabeticRetinopathyReport.id.desc())
            .first()
        )

        prev_url = url_for("verify_remedio_dr.verify_dr_detail", report_id=prev_row.id) if prev_row else None
        next_url = url_for("verify_remedio_dr.verify_dr_detail", report_id=next_row.id) if next_row else None

        # Build images list from encounter files
        images = []
        for ef in (enc.encounter_files or []):
            ft = (ef.file_type or "").lower().strip()
            ext = ef.filename.rsplit(".", 1)[-1].lower() if ef.filename and "." in ef.filename else ""
            if ft.startswith("image/") or ext in IMAGE_EXTS or ft == 'image':
                images.append(ef)

        dr_reports = enc.dr_reports or []
        gl_reports = enc.glaucoma_reports or []

    finally:
        db.close()

    gallery_id = f"pswp-gallery-enc-{enc.id}"

    # Compute page index for this date to preserve list position
    page_idx = 1
    if enc.capture_date_dt is not None:
        with Session() as db2:
            date_rows = (
                db2.query(PatientEncounters.capture_date_dt)
                   .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                   .filter(PatientEncounters.capture_date_dt.isnot(None))
                   .distinct()
                   .order_by(PatientEncounters.capture_date_dt.desc())
                   .all()
            )
            dates = [r[0] for r in date_rows]
            if enc.capture_date_dt in dates:
                page_idx = dates.index(enc.capture_date_dt) + 1
    back_url = url_for("verify_remedio_dr.verify_dr_list", page=page_idx)
    back_label = f"Date {enc.capture_date_dt.strftime('%Y-%m-%d') if enc.capture_date_dt else ''}"

    # Reuse the screenings detail template for consistent UI
    return render_template(
        "screenings/detail.html",
        encounter=enc,
        images=images,
        dr_reports=dr_reports,
        gl_reports=gl_reports,
        back_url=back_url,
        prev_url=prev_url,
        next_url=next_url,
        gallery_id=gallery_id,
        back_label=back_label,
    )


@bp.route("/edit/<int:report_id>", methods=["GET", "POST"])
@roles_required("admin", "optometrist", "data_manager")
def verify_dr_edit(report_id: int):
    db = Session()
    try:
        row = (
            db.query(DiabeticRetinopathyReport)
              .options(
                  joinedload(DiabeticRetinopathyReport.patient_encounter)
                    .selectinload(PatientEncounters.encounter_files)
              )
              .filter(DiabeticRetinopathyReport.id == report_id)
              .first()
        )
        if not row:
            from flask import abort
            abort(404)

        encounter = row.patient_encounter
        lab_unit_id = getattr(encounter, "lab_unit_id", None) if encounter else None
        if lab_unit_id is not None and not (current_user.has_role('admin') or current_user.has_role('data_manager')):
            allowed_lab_units = get_user_lab_unit_ids(current_user.id)
            if lab_unit_id not in allowed_lab_units:
                flash("You don't have permission to access this encounter.", "danger")
                return redirect(url_for("verify_remedio_dr.verify_dr_list"))

        if request.method == "POST":
            row.result = (request.form.get("result") or "").strip() or None
            row.qualitative_result = (request.form.get("qualitative_result") or "").strip() or None
            # Update basic encounter fields
            enc = encounter
            if enc is not None:
                new_pid = (request.form.get("patient_id") or "").strip()
                if new_pid:
                    enc.patient_id = new_pid
                date_str = (request.form.get("capture_date_dt") or "").strip()
                if date_str:
                    try:
                        from datetime import datetime as _dt
                        d = _dt.strptime(date_str, "%Y-%m-%d").date()
                        enc.capture_date_dt = d
                        # keep string field in sync for legacy displays
                        enc.capture_date = d.isoformat()
                    except Exception:
                        pass

            db.add(row)
            db.commit()

            # Verify that all images for this encounter have laterality set
            missing = (
                db.query(EncounterFile)
                  .filter(EncounterFile.patient_encounter_id == row.patient_encounter_id)
                  .filter(EncounterFile.file_type == 'image')
                  .filter(
                      (EncounterFile.eye_side.is_(None)) |
                      (~EncounterFile.eye_side.in_(['right','left','cannot_tell']))
                  )
                  .count()
            )
            if missing and missing > 0:
                flash(f"Saved. {missing} image(s) still untagged. Please mark Right/Left/Cannot tell.", "danger")
            else:
                flash("Saved. All images are tagged.", "success")
            return redirect(url_for("verify_remedio_dr.verify_dr_edit", report_id=row.id))

        # Compute prev/next neighbors for navigation on edit page
        enc = encounter
        d = enc.capture_date_dt if enc else None
        cur_id = row.id
        prev_row = None
        next_row = None
        if d is not None:
            prev_row = (
                db.query(DiabeticRetinopathyReport)
                .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                .filter(
                    (PatientEncounters.capture_date_dt > d)
                    | ((PatientEncounters.capture_date_dt == d) & (DiabeticRetinopathyReport.id > cur_id))
                )
                .order_by(PatientEncounters.capture_date_dt.asc(), DiabeticRetinopathyReport.id.asc())
                .first()
            )
            next_row = (
                db.query(DiabeticRetinopathyReport)
                .join(PatientEncounters, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                .filter(
                    (PatientEncounters.capture_date_dt < d)
                    | ((PatientEncounters.capture_date_dt == d) & (DiabeticRetinopathyReport.id < cur_id))
                )
                .order_by(PatientEncounters.capture_date_dt.desc(), DiabeticRetinopathyReport.id.desc())
                .first()
            )
        prev_url = url_for("verify_remedio_dr.verify_dr_edit", report_id=prev_row.id) if prev_row else None
        next_url = url_for("verify_remedio_dr.verify_dr_edit", report_id=next_row.id) if next_row else None
        # Compute back_url to DR list page for this date
        back_url = None
        if enc and enc.capture_date_dt is not None:
            date_rows = (
                db.query(PatientEncounters.capture_date_dt)
                  .join(DiabeticRetinopathyReport, DiabeticRetinopathyReport.patient_encounter_id == PatientEncounters.id)
                  .filter(PatientEncounters.capture_date_dt.isnot(None))
                  .distinct()
                  .order_by(PatientEncounters.capture_date_dt.desc())
                  .all()
            )
            dates = [r[0] for r in date_rows]
            if enc.capture_date_dt in dates:
                page_idx = dates.index(enc.capture_date_dt) + 1
                back_url = url_for("verify_remedio_dr.verify_dr_list", page=page_idx)
    finally:
        db.close()

    return render_template("verify_remedio_dr/edit.html", row=row, prev_url=prev_url, next_url=next_url, back_url=back_url)
 

@bp.route("/edit/<int:report_id>/verify", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def verify_dr_verify(report_id: int):
    db = Session()
    try:
        row = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.id == report_id).first()
        if not row:
            from flask import abort
            abort(404)
        encounter = db.query(PatientEncounters).filter(PatientEncounters.id == row.patient_encounter_id).first()
        if encounter and not (current_user.has_role('admin') or current_user.has_role('data_manager')):
            allowed_lab_units = get_user_lab_unit_ids(current_user.id)
            if encounter.lab_unit_id not in allowed_lab_units:
                flash("You don't have permission to verify this encounter.", "danger")
                return redirect(url_for('verify_remedio_dr.verify_dr_list'))
        # Save incoming form data (same fields as edit save)
        row.result = (request.form.get("result") or "").strip() or None
        row.qualitative_result = (request.form.get("qualitative_result") or "").strip() or None
        enc = encounter
        if enc:
            new_pid = (request.form.get("patient_id") or "").strip()
            if new_pid:
                enc.patient_id = new_pid
            date_str = (request.form.get("capture_date_dt") or "").strip()
            if date_str:
                try:
                    from datetime import datetime as _dt
                    d = _dt.strptime(date_str, "%Y-%m-%d").date()
                    enc.capture_date_dt = d
                    enc.capture_date = d.isoformat()
                except Exception:
                    pass
            db.add(enc)
        db.add(row)
        db.commit()
        # Ensure all images are tagged before verification
        missing = (
            db.query(EncounterFile)
              .filter(EncounterFile.patient_encounter_id == row.patient_encounter_id)
              .filter(EncounterFile.file_type == 'image')
              .filter(
                  (EncounterFile.eye_side.is_(None)) | (~EncounterFile.eye_side.in_(['right','left','cannot_tell']))
              )
              .count()
        )
        if missing:
            msg = f"{missing} image(s) still untagged; cannot verify."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "incomplete", "message": msg}, 400
            flash(msg, "danger")
            return redirect(url_for('verify_remedio_dr.verify_dr_edit', report_id=report_id))

        if enc:
            enc.dr_verified_status = 'verified'
            try:
                enc.dr_verified_by = current_user.username  # type: ignore[attr-defined]
            except Exception:
                enc.dr_verified_by = 'unknown'
            enc.dr_verified_at = utcnow()
            db.add(enc)
            db.commit()
            
            # Create grading tasks for all images in the encounter for DR
            try:
                # Get all images in this encounter
                images = db.query(EncounterFile).filter(
                    EncounterFile.patient_encounter_id == enc.id
                ).all()
                
                # Create a grading task for each image for DR disease
                dr_disease = db.query(Disease).filter(
                    func.lower(Disease.name).in_(['diabetic retinopathy', 'dr'])
                ).first()
                
                if dr_disease:
                    for image in images:
                        try:
                            ensure_task(image.uuid, dr_disease.id)
                            current_app.logger.info(
                                "Created DR grading task for image UUID %s", image.uuid
                            )
                        except Exception as task_error:
                            current_app.logger.exception(
                                "Failed to create DR grading task for image UUID %s: %s", 
                                image.uuid, task_error
                            )
                            # Continue with other images even if one fails
                else:
                    current_app.logger.warning("DR disease not found in database")
            except Exception as e:
                current_app.logger.exception(
                    "Failed to create grading tasks for DR verified encounter %s: %s", 
                    enc.id, e
                )
                # Don't fail the verification if task creation fails, just log it

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": enc.dr_verified_status if enc else 'verified', "by": enc.dr_verified_by if enc else current_user.username}
        flash("Encounter verified.", "success")
        return redirect(url_for('verify_remedio_dr.verify_dr_edit', report_id=report_id))
    finally:
        db.close()


@bp.route("/edit/<int:report_id>/unverify", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def verify_dr_unverify(report_id: int):
    db = Session()
    try:
        row = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.id == report_id).first()
        if not row:
            from flask import abort
            abort(404)
        enc = db.query(PatientEncounters).filter(PatientEncounters.id == row.patient_encounter_id).first()
        if enc and not (current_user.has_role('admin') or current_user.has_role('data_manager')):
            allowed_lab_units = get_user_lab_unit_ids(current_user.id)
            if enc.lab_unit_id not in allowed_lab_units:
                flash("You don't have permission to modify this encounter.", "danger")
                return redirect(url_for('verify_remedio_dr.verify_dr_list'))
        if enc:
            # Check if we can unverify the encounter (all tasks must be pending)
            from services.taskCreationServices import can_unverify_image, remove_pending_tasks
            can_unverify = True
            images = db.query(EncounterFile).filter(
                EncounterFile.patient_encounter_id == enc.id
            ).all()
            
            for image in images:
                if not can_unverify_image(db, kind="encounter", image_id=image.id):
                    can_unverify = False
                    break
            
            if not can_unverify:
                if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                    return {"ok": False, "error": "tasks_in_progress", "message": "Cannot unverify encounter - some images have non-pending tasks."}, 400
                else:
                    flash("Cannot unverify encounter - some images have non-pending tasks.", "danger")
                    return redirect(url_for('verify_remedio_dr.verify_dr_edit', report_id=report_id))
            
            # Proceed with unverification
            enc.dr_verified_status = None
            enc.dr_verified_by = None
            enc.dr_verified_at = None
            db.add(enc)
            db.commit()
            
            # Remove any pending grading tasks for DR disease for all images in this encounter
            try:
                # Remove pending grading tasks for each image
                from services.taskCreationServices import remove_pending_tasks
                dr_disease = db.query(Disease).filter(
                    func.lower(Disease.name).in_(['diabetic retinopathy', 'dr'])
                ).first()
                
                if dr_disease:
                    for image in images:
                        try:
                            removed_count = remove_pending_tasks(db, kind="encounter", image_id=image.id)
                            if removed_count > 0:
                                current_app.logger.info(
                                    "Removed %d pending DR grading task(s) for unverified image UUID %s", 
                                    removed_count, image.uuid
                                )
                        except Exception as task_error:
                            current_app.logger.exception(
                                "Failed to remove DR grading tasks for unverified image UUID %s: %s", 
                                image.uuid, task_error
                            )
                            # Continue with other images even if one fails
                else:
                    current_app.logger.warning("DR disease not found in database when trying to remove tasks")
            except Exception as e:
                current_app.logger.exception(
                    "Failed to remove grading tasks for DR unverified encounter %s: %s", 
                    enc.id, e
                )
                # Don't fail the unverification if task removal fails, just log it

        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "status": enc.dr_verified_status if enc else None}
        flash("Encounter unverified.", "warning")
        return redirect(url_for('verify_remedio_dr.verify_dr_edit', report_id=report_id))
    finally:
        db.close()

@bp.route("/edit/<int:report_id>/mark_eye", methods=["POST"])
@roles_required("admin", "optometrist", "data_manager")
def verify_dr_mark_eye(report_id: int):
    side = (request.form.get("side") or "").strip().lower()
    ef_id = request.form.get("ef_id")
    if side not in {"right", "left", "cannot_tell"}:
        # AJAX response if requested
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_side"}, 400
        flash("Invalid selection.", "danger")
        return redirect(url_for("verify_remedio_dr.verify_dr_edit", report_id=report_id))
    try:
        ef_id_int = int(ef_id)
    except Exception:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": False, "error": "invalid_image"}, 400
        flash("Invalid image id.", "danger")
        return redirect(url_for("verify_remedio_dr.verify_dr_edit", report_id=report_id))

    db = Session()
    try:
        row = db.query(DiabeticRetinopathyReport).filter(DiabeticRetinopathyReport.id == report_id).first()
        if not row:
            from flask import abort
            abort(404)
        ef = db.query(EncounterFile).filter(EncounterFile.id == ef_id_int).first()
        if not ef or ef.patient_encounter_id != row.patient_encounter_id:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
                return {"ok": False, "error": "not_found"}, 404
            flash("Image not found for this encounter.", "danger")
            return redirect(url_for("verify_remedio_dr.verify_dr_edit", report_id=report_id))
        ef.eye_side = side
        db.add(ef)
        db.commit()
        # AJAX response: avoid full page reload
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or ""):
            return {"ok": True, "ef_id": ef.id, "side": ef.eye_side}
        flash("Image laterality updated.", "success")
    finally:
        db.close()
    return redirect(url_for("verify_remedio_dr.verify_dr_edit", report_id=report_id))
