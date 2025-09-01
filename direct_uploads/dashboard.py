from datetime import datetime
import os
from flask import request, render_template, redirect, url_for, flash, current_app
from flask_login import current_user
from sqlalchemy import select, func
from . import bp
from .utils import with_session
from auth.roles import roles_required
from models import (
    User, LabUnit, Hospital, DirectImageUpload, Camera, Disease, Area
)

@bp.route("/direct/dashboard", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def dashboard():
    with with_session() as db_session:
        if request.method == "POST":
            selected_ids = request.form.getlist('selected_uploads')
            action = request.form.get('action')

            if len(selected_ids) > 30:
                flash("Maximum 30 files can be processed in a single operation.", "danger")
                return redirect(url_for("direct_uploads.dashboard"))

            if action == 'bulk_edit' and selected_ids:
                new_hospital_id = request.form.get('new_hospital_id')
                new_lab_unit_id = request.form.get('new_lab_unit_id')
                new_camera_id = request.form.get('new_camera_id')
                new_disease_id = request.form.get('new_disease_id')
                new_area_id = request.form.get('new_area_id')
                new_is_mydriatic = request.form.get('new_is_mydriatic')

                q = select(DirectImageUpload).where(DirectImageUpload.id.in_(list(map(int, selected_ids))))
                if not current_user.has_role('admin', 'data_manager'):
                    q = q.where(DirectImageUpload.uploader_id == current_user.id)

                rows = db_session.execute(q).scalars().all()
                updated = 0
                for u in rows:
                    if new_hospital_id: u.hospital_id = int(new_hospital_id)
                    if new_lab_unit_id: u.lab_unit_id = int(new_lab_unit_id)
                    if new_camera_id:   u.camera_id   = int(new_camera_id)
                    if new_disease_id:  u.disease_id  = int(new_disease_id)
                    if new_area_id:     u.area_id     = int(new_area_id)
                    if new_is_mydriatic is not None:
                        u.is_mydriatic = new_is_mydriatic == 'on'
                    updated += 1

                db_session.commit()
                flash(f"Successfully updated {updated} uploads.", "success")

            elif action == 'bulk_delete' and selected_ids:
                q = select(DirectImageUpload).where(DirectImageUpload.id.in_(list(map(int, selected_ids))))
                if not current_user.has_role('admin', 'data_manager'):
                    q = q.where(DirectImageUpload.uploader_id == current_user.id)

                rows = db_session.execute(q).scalars().all()
                deleted = 0
                for u in rows:
                    try:
                        if os.path.exists(u.absolute_filepath):
                            os.remove(u.absolute_filepath)
                    except Exception as e:
                        current_app.logger.warning("Failed to delete file %s: %s", u.absolute_filepath, e)
                    db_session.delete(u)
                    deleted += 1

                db_session.commit()
                flash(f"Successfully deleted {deleted} uploads.", "success")
            else:
                flash("No uploads selected for operation.", "warning")

            return redirect(url_for("direct_uploads.dashboard"))

        # GET (filters + pagination)
        page     = request.args.get('page', 1, type=int)
        per_page = 50

        f_date_from   = request.args.get('date_from')
        f_date_to     = request.args.get('date_to')
        f_lab_unit_id = request.args.get('lab_unit_id')
        f_uploader_id = request.args.get('uploader_id')
        f_hospital_id = request.args.get('hospital_id')
        f_camera_id   = request.args.get('camera_id')
        f_disease_id  = request.args.get('disease_id')
        f_area_id     = request.args.get('area_id')

        if page < 1: page = 1

        q = select(DirectImageUpload)

        if f_date_from:
            try:
                q = q.where(DirectImageUpload.created_at >= datetime.strptime(f_date_from, '%Y-%m-%d'))
            except ValueError:
                pass
        if f_date_to:
            try:
                dt = datetime.strptime(f_date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                q = q.where(DirectImageUpload.created_at <= dt)
            except ValueError:
                pass

        if f_lab_unit_id: q = q.where(DirectImageUpload.lab_unit_id == f_lab_unit_id)
        if f_hospital_id: q = q.where(DirectImageUpload.hospital_id == f_hospital_id)
        if f_camera_id:   q = q.where(DirectImageUpload.camera_id   == f_camera_id)
        if f_disease_id:  q = q.where(DirectImageUpload.disease_id  == f_disease_id)
        if f_area_id:     q = q.where(DirectImageUpload.area_id     == f_area_id)

        if not current_user.has_role('admin', 'data_manager'):
            q = q.where(DirectImageUpload.uploader_id == current_user.id)
            f_uploader_id = None
        elif f_uploader_id:
            q = q.where(DirectImageUpload.uploader_id == f_uploader_id)

        count_q = select(func.count()).select_from(q.subquery())
        total_count = db_session.execute(count_q).scalar_one()
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
        if page > total_pages: page = max(total_pages, 1)

        main_q = q.order_by(DirectImageUpload.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        uploads = db_session.execute(main_q).scalars().all()

        ids = lambda attr: {getattr(u, attr) for u in uploads}
        hospitals = {h.id: h for h in db_session.execute(select(Hospital).where(Hospital.id.in_(ids("hospital_id")))).scalars().all()} if uploads else {}
        lab_units = {l.id: l for l in db_session.execute(select(LabUnit).where(LabUnit.id.in_(ids("lab_unit_id")))).scalars().all()} if uploads else {}
        cameras   = {c.id: c for c in db_session.execute(select(Camera).where(Camera.id.in_(ids("camera_id")))).scalars().all()}   if uploads else {}
        diseases  = {d.id: d for d in db_session.execute(select(Disease).where(Disease.id.in_(ids("disease_id")))).scalars().all()} if uploads else {}
        areas     = {a.id: a for a in db_session.execute(select(Area).where(Area.id.in_(ids("area_id")))).scalars().all()}         if uploads else {}
        users     = {u.id: u for u in db_session.execute(select(User).where(User.id.in_({u.uploader_id for u in uploads}))).scalars().all()} if uploads else {}

        all_hospitals = db_session.execute(select(Hospital).order_by(Hospital.name)).scalars().all()
        all_lab_units = db_session.execute(select(LabUnit).order_by(LabUnit.name)).scalars().all()
        all_cameras   = db_session.execute(select(Camera).order_by(Camera.name)).scalars().all()
        all_diseases  = db_session.execute(select(Disease).order_by(Disease.name)).scalars().all()
        all_areas     = db_session.execute(select(Area).order_by(Area.name)).scalars().all()
        all_users     = db_session.execute(select(User).order_by(User.username)).scalars().all()

        # KPIs
        kpi_total_uploads = total_count
        camera_kpis  = {name: cnt for name, cnt in db_session.execute(
            select(Camera.name, func.count(DirectImageUpload.id)).join(DirectImageUpload, DirectImageUpload.camera_id == Camera.id).group_by(Camera.name)
        ).all()}
        disease_kpis = {name: cnt for name, cnt in db_session.execute(
            select(Disease.name, func.count(DirectImageUpload.id)).join(DirectImageUpload, DirectImageUpload.disease_id == Disease.id).group_by(Disease.name)
        ).all()}
        area_kpis    = {name: cnt for name, cnt in db_session.execute(
            select(Area.name, func.count(DirectImageUpload.id)).join(DirectImageUpload, DirectImageUpload.area_id == Area.id).group_by(Area.name)
        ).all()}

        current_app.logger.info("Dashboard accessed by %s (%s). Page:%s Total:%s",
                                current_user.username, current_user.id, page, total_count)

        return render_template("direct_uploads/dashboard.html",
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
                               filter_disease_id=f_disease_id, filter_area_id=f_area_id)
