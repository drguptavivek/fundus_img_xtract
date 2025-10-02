# direct_uploads/dashboard.py

from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select, func
from datetime import datetime, timezone
from models import (
    User,
    LabUnit,
    Hospital,
    DirectImageUpload,
    Camera,
    Disease,
    Area,
    ImageGrading,
    GradingTask,
    utcnow,
)

from . import bp
from utils.utils import with_session
from auth.roles import roles_required
from utils.fileUtils import abs_from_parts
from utils.upload_eligibility import get_user_lab_unit_ids



# --- helpers ---
def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

@bp.route("/direct/dashboard", methods=["GET", "POST"])
@roles_required('fileUploader', 'optometrist', 'data_manager', 'admin')
def dashboard():
    with with_session() as db_session:
        allowed_lab_unit_ids = get_user_lab_unit_ids(current_user.id)
        allowed_lab_unit_ids_list = list(allowed_lab_unit_ids)
        is_admin_like = current_user.has_role("admin", "data_manager")

        if not allowed_lab_unit_ids_list and not is_admin_like:
            flash("You do not have access to any lab units.", "warning")
            if request.method == "POST":
                return redirect(url_for("direct_uploads.dashboard"), code=303)

        allowed_hospital_ids: set[int] = set()
        if allowed_lab_unit_ids_list and not is_admin_like:
            allowed_hospital_ids = {
                hid for hid, in db_session.execute(
                    select(LabUnit.hospital_id).where(LabUnit.id.in_(allowed_lab_unit_ids_list))
                )
                if hid is not None
            }

        if request.method == "POST":
            selected_ids = request.form.getlist('selected_uploads')
            action = request.form.get('action')

            if len(selected_ids) > 50:
                flash("Maximum 50 files can be processed in a single operation.", "danger")
                return redirect(url_for("direct_uploads.dashboard"), code=303)

            elif action == "bulk_edit" and selected_ids:
                # Get the new values from the form
                new_hospital_id = request.form.get('new_hospital_id')
                new_lab_unit_id = request.form.get('new_lab_unit_id')
                new_camera_id = request.form.get('new_camera_id')
                new_disease_id = request.form.get('new_disease_id')
                new_area_id = request.form.get('new_area_id')
                new_is_mydriatic = request.form.get('new_is_mydriatic')

                # Coerce IDs safely
                try:
                    ids = [int(x) for x in selected_ids]
                except Exception:
                    ids = [int(x) for x in selected_ids if str(x).isdigit()]

                if not ids:
                    flash("No valid rows selected.", "warning")
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                q = select(DirectImageUpload).where(DirectImageUpload.id.in_(ids))
                if not is_admin_like and allowed_lab_unit_ids_list:
                    q = q.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids_list))

                # Non-admins can only edit their own uploads
                if not is_admin_like:
                    q = q.where(DirectImageUpload.uploader_id == current_user.id)
                    
                rows = db_session.execute(q).scalars().all()

                if not is_admin_like and allowed_lab_unit_ids_list and not rows:
                    flash("No uploads matched your selection and permissions.", "warning")
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                if new_lab_unit_id and not is_admin_like:
                    try:
                        new_lab_unit_id_int = int(new_lab_unit_id)
                    except (TypeError, ValueError):
                        flash("Invalid lab unit selection.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)
                    if allowed_lab_unit_ids_list and new_lab_unit_id_int not in allowed_lab_unit_ids_list:
                        flash("You cannot assign uploads to that lab unit.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)

                if new_hospital_id and not is_admin_like:
                    try:
                        new_hospital_id_int = int(new_hospital_id)
                    except (TypeError, ValueError):
                        flash("Invalid hospital selection.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)
                    if allowed_hospital_ids and new_hospital_id_int not in allowed_hospital_ids:
                        flash("You cannot assign uploads to that hospital.", "danger")
                        return redirect(url_for("direct_uploads.dashboard"), code=303)

                upload_ids = [upload.id for upload in rows]
                tasks_by_upload: dict[int, list[GradingTask]] = {}
                if upload_ids:
                    task_rows = db_session.execute(
                        select(GradingTask).where(GradingTask.direct_image_upload_id.in_(upload_ids))
                    ).scalars().all()
                    for task in task_rows:
                        if task.direct_image_upload_id is None:
                            continue
                        tasks_by_upload.setdefault(task.direct_image_upload_id, []).append(task)

                blocked_uploads: list[DirectImageUpload] = []
                updatable_uploads: list[tuple[DirectImageUpload, list[GradingTask]]] = []
                for upload in rows:
                    related_tasks = tasks_by_upload.get(upload.id, [])
                    if any(task.state != 'pending' for task in related_tasks):
                        blocked_uploads.append(upload)
                        continue
                    updatable_uploads.append((upload, related_tasks))

                if not updatable_uploads:
                    blocked_ids = ", ".join(str(upload.id) for upload in blocked_uploads)
                    flash(
                        "Update cancelled. Tasks already in progress for upload(s): "
                        f"{blocked_ids}.",
                        "danger",
                    )
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                new_hospital_id_int = int(new_hospital_id) if new_hospital_id else None
                new_lab_unit_id_int = int(new_lab_unit_id) if new_lab_unit_id else None
                new_camera_id_int = int(new_camera_id) if new_camera_id else None
                new_disease_id_int = int(new_disease_id) if new_disease_id else None
                new_area_id_int = int(new_area_id) if new_area_id else None
                new_is_mydriatic_bool = (
                    new_is_mydriatic == 'on' if new_is_mydriatic is not None else None
                )

                updated_count = 0
                updated_tasks = 0
                for upload, related_tasks in updatable_uploads:
                    if new_hospital_id_int is not None:
                        upload.hospital_id = new_hospital_id_int
                    if new_lab_unit_id_int is not None:
                        upload.lab_unit_id = new_lab_unit_id_int
                    if new_camera_id_int is not None:
                        upload.camera_id = new_camera_id_int
                    if new_disease_id_int is not None:
                        upload.disease_id = new_disease_id_int
                    if new_area_id_int is not None:
                        upload.area_id = new_area_id_int
                    if new_is_mydriatic_bool is not None:
                        upload.is_mydriatic = new_is_mydriatic_bool

                    for task in related_tasks:
                        task_changed = False
                        if new_lab_unit_id_int is not None and task.lab_unit_id != new_lab_unit_id_int:
                            task.lab_unit_id = new_lab_unit_id_int
                            task_changed = True
                        if new_disease_id_int is not None and task.disease_id != new_disease_id_int:
                            task.disease_id = new_disease_id_int
                            task_changed = True
                        if task_changed:
                            task.updated_at = utcnow()
                            updated_tasks += 1

                    updated_count += 1

                db_session.commit()
                if blocked_uploads:
                    blocked_ids = ", ".join(str(upload.id) for upload in blocked_uploads)
                    flash(
                        "Partially updated. Skipped upload(s) with in-progress tasks: "
                        f"{blocked_ids}.",
                        "warning",
                    )
                flash(
                    f"Successfully updated {updated_count} uploads. Updated {updated_tasks} pending task(s).",
                    "success",
                )
                return redirect(url_for("direct_uploads.dashboard"), code=303)

            elif action == "bulk_delete" and selected_ids:
                # Coerce IDs safely
                try:
                    ids = [int(x) for x in selected_ids]
                except Exception:
                    ids = [int(x) for x in selected_ids if str(x).isdigit()]

                if not ids:
                    flash("No valid rows selected.", "warning")
                    return redirect(url_for("direct_uploads.dashboard"), code=303)

                q = select(DirectImageUpload).where(DirectImageUpload.id.in_(ids))
                if not is_admin_like and allowed_lab_unit_ids_list:
                    q = q.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids_list))

                # Non-admins can only delete their own uploads
                if not is_admin_like:
                    q = q.where(DirectImageUpload.uploader_id == current_user.id)
                    
                rows = db_session.execute(q).scalars().all()

                deleted_files = 0
                deleted_rows = 0

                for u in rows:
                    # Try to delete edited first (if present)
                    if getattr(u, "edited_filename", None):
                        try:
                            ep = abs_from_parts(u.folder_rel, u.edited_filename, "edited")
                            if ep.exists():
                                ep.unlink()
                                deleted_files += 1
                            else:
                                current_app.logger.info(
                                    "Edited file missing on disk; will still delete DB row. upload_id=%s path=%s",
                                    u.id, ep
                                )
                        except Exception as e:
                            current_app.logger.warning(
                                "Failed to delete edited file for upload_id=%s (folder_rel=%r, edited_filename=%r): %s",
                                u.id, u.folder_rel, u.edited_filename, e
                            )

                    # Then delete original
                    try:
                        op = abs_from_parts(u.folder_rel, u.filename, "orig")
                        if op.exists():
                            op.unlink()
                            deleted_files += 1
                        else:
                            current_app.logger.info(
                                "Original file missing on disk; will still delete DB row. upload_id=%s path=%s",
                                u.id, op
                            )
                    except Exception as e:
                        current_app.logger.warning(
                            "Failed to delete original file for upload_id=%s (folder_rel=%r, filename=%r): %s",
                            u.id, u.folder_rel, u.filename, e
                        )

                    # Always remove DB row (even if files were missing)
                    db_session.delete(u)
                    deleted_rows += 1

                db_session.commit()
                flash(f"Deleted {deleted_rows} record(s). Removed {deleted_files} file(s) from disk.", "success")
                return redirect(url_for("direct_uploads.dashboard"), code=303)


            else:
                flash("No uploads selected for operation.", "warning")

            return redirect(url_for("direct_uploads.dashboard"), code=303)

        # GET (filters + pagination)
        page     = request.args.get('page', 1, type=int)
        per_page = 50

        # keep dates as strings (do NOT _to_int these)
        f_date_from   = request.args.get('date_from')
        f_date_to     = request.args.get('date_to')
        f_lab_unit_id = _to_int(request.args.get('lab_unit_id'))
        f_uploader_id = _to_int(request.args.get('uploader_id'))
        f_hospital_id = _to_int(request.args.get('hospital_id'))
        f_camera_id   = _to_int(request.args.get('camera_id'))
        f_disease_id  = _to_int(request.args.get('disease_id'))
        f_area_id     = _to_int(request.args.get('area_id'))

        if page < 1:
            page = 1

        q = select(DirectImageUpload)
        if not is_admin_like:
            if allowed_lab_unit_ids_list:
                q = q.where(DirectImageUpload.lab_unit_id.in_(allowed_lab_unit_ids_list))
            else:
                q = q.where(DirectImageUpload.id == -1)

        # Date filters
        if f_date_from:
            try:
                start_dt = datetime.strptime(f_date_from, '%Y-%m-%d')
                q = q.where(DirectImageUpload.created_at >= start_dt)
            except ValueError:
                pass
        if f_date_to:
            try:
                end_dt = datetime.strptime(f_date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                q = q.where(DirectImageUpload.created_at <= end_dt)
            except ValueError:
                pass

        # ID filters
        if f_lab_unit_id is not None:
            q = q.where(DirectImageUpload.lab_unit_id == f_lab_unit_id)
        if f_hospital_id is not None:
            q = q.where(DirectImageUpload.hospital_id == f_hospital_id)
        if f_camera_id is not None:
            q = q.where(DirectImageUpload.camera_id == f_camera_id)
        if f_disease_id is not None:
            q = q.where(DirectImageUpload.disease_id == f_disease_id)
        if f_area_id is not None:
            q = q.where(DirectImageUpload.area_id == f_area_id)

        # RBAC: only admins/managers can filter by uploader; other roles already scoped by lab-unit
        if is_admin_like and f_uploader_id is not None:
            q = q.where(DirectImageUpload.uploader_id == f_uploader_id)

        # ---- Build filtered ID subquery (no ORDER BY here) ----
        filtered_ids_sq = (
            q.with_only_columns(DirectImageUpload.id)  # SELECT id FROM (filtered)
            .order_by(None)
            .subquery()
        )

        # Count from filtered set
        total_count = db_session.execute(
            select(func.count()).select_from(filtered_ids_sq)
        ).scalar_one()

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        if page > total_pages:
            page = max(total_pages, 1)

        # ---- Page rows: JOIN back to entity on id (prevents duplicates) ----
        main_q = (
            select(DirectImageUpload)
            .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
            .order_by(DirectImageUpload.created_at.desc(), DirectImageUpload.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        uploads = db_session.execute(main_q).scalars().all()

        # Fetch gradings for these uploads
        upload_ids = [u.id for u in uploads]
        gradings = {}
        if upload_ids:
            grading_rows = db_session.execute(
                select(ImageGrading)
                .where(ImageGrading.direct_image_upload_id.in_(upload_ids))
            ).scalars().all()
            
            # Group gradings by upload_id
            for grading in grading_rows:
                if grading.direct_image_upload_id not in gradings:
                    gradings[grading.direct_image_upload_id] = []
                gradings[grading.direct_image_upload_id].append(grading)

        # Side lookups for the current page
        ids = lambda attr: {getattr(u, attr) for u in uploads}
        hospitals = {h.id: h for h in db_session.execute(select(Hospital).where(Hospital.id.in_(ids("hospital_id")))).scalars().all()} if uploads else {}
        lab_units = {l.id: l for l in db_session.execute(select(LabUnit).where(LabUnit.id.in_(ids("lab_unit_id")))).scalars().all()} if uploads else {}
        cameras   = {c.id: c for c in db_session.execute(select(Camera).where(Camera.id.in_(ids("camera_id")))).scalars().all()} if uploads else {}
        diseases  = {d.id: d for d in db_session.execute(select(Disease).where(Disease.id.in_(ids("disease_id")))).scalars().all()} if uploads else {}
        areas     = {a.id: a for a in db_session.execute(select(Area).where(Area.id.in_(ids("area_id")))).scalars().all()} if uploads else {}
        users     = {u.id: u for u in db_session.execute(select(User).where(User.id.in_({u.uploader_id for u in uploads}))).scalars().all()} if uploads else {}

        # Full lists for filters
        if is_admin_like:
            all_lab_units = db_session.execute(select(LabUnit).order_by(LabUnit.name)).scalars().all()
            all_hospitals = db_session.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        else:
            all_lab_units = db_session.execute(
                select(LabUnit).where(LabUnit.id.in_(allowed_lab_unit_ids_list)).order_by(LabUnit.name)
            ).scalars().all() if allowed_lab_unit_ids_list else []

            allowed_hospital_ids_local = {lu.hospital_id for lu in all_lab_units if lu.hospital_id is not None}
            all_hospitals = db_session.execute(
                select(Hospital).where(Hospital.id.in_(allowed_hospital_ids_local)).order_by(Hospital.name)
            ).scalars().all() if allowed_hospital_ids_local else []
        all_cameras   = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        all_diseases  = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        all_areas     = db_session.execute(select(Area).order_by(Area.name)).scalars().all()
        all_users     = db_session.execute(select(User).order_by(User.username)).scalars().all()

        # ---- KPIs from the SAME filtered set (join on id) ----
        kpi_total_uploads = total_count

        camera_kpis = {
            name: cnt for name, cnt in db_session.execute(
                select(Camera.name, func.count())
                .join(DirectImageUpload, DirectImageUpload.camera_id == Camera.id)
                .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
                .group_by(Camera.name)
            ).all()
        }
        disease_kpis = {
            name: cnt for name, cnt in db_session.execute(
                select(Disease.name, func.count())
                .join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id)
                .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
                .group_by(Disease.name)
            ).all()
        }
        area_kpis = {
            name: cnt for name, cnt in db_session.execute(
                select(Area.name, func.count())
                .join(DirectImageUpload, DirectImageUpload.area_id == Area.id)
                .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
                .group_by(Area.name)
            ).all()
        }

        # Build hierarchical KPI of counts by hospital -> lab unit -> disease
        hospital_lab_disease_rows = db_session.execute(
            select(
                Hospital.id.label("hospital_id"),
                Hospital.name.label("hospital_name"),
                LabUnit.id.label("lab_unit_id"),
                LabUnit.name.label("lab_unit_name"),
                Disease.name.label("disease_name"),
                func.count().label("image_count"),
            )
            .select_from(DirectImageUpload)
            .join(filtered_ids_sq, DirectImageUpload.id == filtered_ids_sq.c.id)
            .join(LabUnit, DirectImageUpload.lab_unit_id == LabUnit.id)
            .join(Hospital, LabUnit.hospital_id == Hospital.id)
            .join(Disease, DirectImageUpload.disease_id == Disease.id)
            .group_by(
                Hospital.id,
                Hospital.name,
                LabUnit.id,
                LabUnit.name,
                Disease.name,
            )
            .order_by(Hospital.name, LabUnit.name, Disease.name)
        ).all()

        hospital_lab_unit_disease_kpis: list[dict[str, object]] = []
        hospital_index: dict[int, dict[str, object]] = {}
        lab_index: dict[int, dict[int, dict[str, object]]] = {}

        for row in hospital_lab_disease_rows:
            hosp_entry = hospital_index.get(row.hospital_id)
            if hosp_entry is None:
                hosp_entry = {
                    "hospital_id": row.hospital_id,
                    "hospital_name": row.hospital_name,
                    "lab_units": [],
                }
                hospital_index[row.hospital_id] = hosp_entry
                hospital_lab_unit_disease_kpis.append(hosp_entry)

            lab_map = lab_index.setdefault(row.hospital_id, {})
            lab_entry = lab_map.get(row.lab_unit_id)
            if lab_entry is None:
                lab_entry = {
                    "lab_unit_id": row.lab_unit_id,
                    "lab_unit_name": row.lab_unit_name,
                    "diseases": [],
                }
                lab_map[row.lab_unit_id] = lab_entry
                hosp_entry["lab_units"].append(lab_entry)

            lab_entry["diseases"].append(
                {
                    "disease_name": row.disease_name,
                    "image_count": row.image_count,
                }
            )

        current_app.logger.info(
            "Dashboard accessed by %s (%s). Page:%s Total:%s",
            current_user.username, current_user.id, page, total_count
        )

        return render_template(
            "direct_uploads/dashboard.html",
            uploads=uploads,
            gradings=gradings,
            hospitals=hospitals, lab_units=lab_units, cameras=cameras,
            diseases=diseases, areas=areas, users=users,
            all_hospitals=all_hospitals, all_lab_units=all_lab_units,
            all_cameras=all_cameras, all_diseases=all_diseases, all_areas=all_areas, all_users=all_users,
            current_page=page, total_pages=total_pages,
            total_count=total_count, per_page=per_page,
            kpi_total_uploads=kpi_total_uploads,
            camera_kpis=camera_kpis, disease_kpis=disease_kpis, area_kpis=area_kpis,
            hospital_lab_unit_disease_kpis=hospital_lab_unit_disease_kpis,
            filter_date_from=f_date_from, filter_date_to=f_date_to,
            filter_lab_unit_id=f_lab_unit_id, filter_uploader_id=f_uploader_id,
            filter_hospital_id=f_hospital_id, filter_camera_id=f_camera_id,
            filter_disease_id=f_disease_id, filter_area_id=f_area_id
        )
