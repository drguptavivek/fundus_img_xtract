# direct_uploads/dashboard.py

from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select, func
from datetime import datetime, timezone
from models import (
    User, LabUnit, Hospital, DirectImageUpload, Camera, Disease, Area
)

from . import bp
from .utils import with_session
from auth.roles import roles_required
from direct_uploads.paths import abs_from_parts



# --- helpers ---
def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

@bp.route("/direct/dashboard", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def dashboard():
    with with_session() as db_session:
        if request.method == "POST":
            selected_ids = request.form.getlist('selected_uploads')
            action = request.form.get('action')

            if len(selected_ids) > 30:
                flash("Maximum 30 files can be processed in a single operation.", "danger")
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

                # Non-admins can only delete their own uploads
                if not current_user.has_role("admin", "data_manager"):
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

        # RBAC
        if not current_user.has_role('admin', 'data_manager'):
            q = q.where(DirectImageUpload.uploader_id == current_user.id)
            f_uploader_id = None
        elif f_uploader_id is not None:
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

        # Side lookups for the current page
        ids = lambda attr: {getattr(u, attr) for u in uploads}
        hospitals = {h.id: h for h in db_session.execute(select(Hospital).where(Hospital.id.in_(ids("hospital_id")))).scalars().all()} if uploads else {}
        lab_units = {l.id: l for l in db_session.execute(select(LabUnit).where(LabUnit.id.in_(ids("lab_unit_id")))).scalars().all()} if uploads else {}
        cameras   = {c.id: c for c in db_session.execute(select(Camera).where(Camera.id.in_(ids("camera_id")))).scalars().all()} if uploads else {}
        diseases  = {d.id: d for d in db_session.execute(select(Disease).where(Disease.id.in_(ids("disease_id")))).scalars().all()} if uploads else {}
        areas     = {a.id: a for a in db_session.execute(select(Area).where(Area.id.in_(ids("area_id")))).scalars().all()} if uploads else {}
        users     = {u.id: u for u in db_session.execute(select(User).where(User.id.in_({u.uploader_id for u in uploads}))).scalars().all()} if uploads else {}

        # Full lists for filters
        all_hospitals = db_session.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        all_lab_units = db_session.execute(select(LabUnit).order_by(LabUnit.name)).scalars().all()
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

        current_app.logger.info(
            "Dashboard accessed by %s (%s). Page:%s Total:%s",
            current_user.username, current_user.id, page, total_count
        )

        return render_template(
            "direct_uploads/dashboard.html",
            uploads=uploads,
            hospitals=hospitals, lab_units=lab_units, cameras=cameras,
            diseases=diseases, areas=areas, users=users,
            all_hospitals=all_hospitals, all_lab_units=all_lab_units,
            all_cameras=all_cameras, all_diseases=all_diseases, all_areas=all_areas, all_users=all_users,
            current_page=page, total_pages=total_pages,
            total_count=total_count, per_page=per_page,
            kpi_total_uploads=kpi_total_uploads,
            camera_kpis=camera_kpis, disease_kpis=disease_kpis, area_kpis=area_kpis,
            filter_date_from=f_date_from, filter_date_to=f_date_to,
            filter_lab_unit_id=f_lab_unit_id, filter_uploader_id=f_uploader_id,
            filter_hospital_id=f_hospital_id, filter_camera_id=f_camera_id,
            filter_disease_id=f_disease_id, filter_area_id=f_area_id
        )
