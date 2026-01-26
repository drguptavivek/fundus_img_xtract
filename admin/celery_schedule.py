from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from auth.roles import roles_required

from db_transaction_manager import transaction_scope
from models import CeleryBeatSchedule, Hospital


def _parse_optional_int(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _list_hospitals():
    with transaction_scope() as db:
        hospitals = db.query(Hospital).order_by(Hospital.name.asc()).all()
        return hospitals


def _known_tasks() -> list[str]:
    return [
        "celery_tasks.tasks.maintenance_tasks.auto_rotate_peppers_task",
        "celery_tasks.tasks.maintenance_tasks.refresh_materialized_views_task",
        "celery_tasks.tasks.maintenance_tasks.run_thumbnail_maintenance_task",
        "celery_tasks.tasks.maintenance_tasks.cleanup_old_exports_task",
        "celery_tasks.tasks.maintenance_tasks.cleanup_old_pii_jobs_task",
        "celery_tasks.tasks.maintenance_tasks.cleanup_old_backfill_jobs_task",
    ]


@login_required
@roles_required("admin")
def celery_schedule_list():
    hospitals = _list_hospitals()
    known_tasks = _known_tasks()
    with transaction_scope() as db:
        schedules = db.query(CeleryBeatSchedule).order_by(CeleryBeatSchedule.name.asc()).all()
    return render_template(
        "admin/celery_schedules.html",
        schedules=schedules,
        hospitals=hospitals,
        known_tasks=known_tasks,
    )


@login_required
@roles_required("admin")
def celery_schedule_create():
    name = (request.form.get("name") or "").strip()
    task_name = (request.form.get("task_name") or "").strip()
    schedule_type = (request.form.get("schedule_type") or "interval").strip()
    queue = (request.form.get("queue") or "").strip() or None
    interval_seconds = _parse_optional_int(request.form.get("interval_seconds"))
    crontab_minute = (request.form.get("crontab_minute") or "").strip() or None
    crontab_hour = (request.form.get("crontab_hour") or "").strip() or None
    crontab_day_of_week = (request.form.get("crontab_day_of_week") or "").strip() or None
    crontab_day_of_month = (request.form.get("crontab_day_of_month") or "").strip() or None
    crontab_month_of_year = (request.form.get("crontab_month_of_year") or "").strip() or None
    enabled = request.form.get("enabled") == "on"
    hospital_id = _parse_optional_int(request.form.get("hospital_id"))
    user_id = _parse_optional_int(request.form.get("user_id")) or current_user.id

    if not name or not task_name:
        flash("Name and task name are required.", "danger")
        return redirect(url_for("admin.celery_schedule_list"))

    if schedule_type not in {"interval", "crontab"}:
        flash("Invalid schedule type.", "danger")
        return redirect(url_for("admin.celery_schedule_list"))

    if schedule_type == "interval" and not interval_seconds:
        flash("Interval seconds are required for interval schedules.", "danger")
        return redirect(url_for("admin.celery_schedule_list"))

    with transaction_scope() as db:
        existing = db.query(CeleryBeatSchedule).filter(CeleryBeatSchedule.name == name).first()
        if existing:
            flash("Schedule name already exists.", "danger")
            return redirect(url_for("admin.celery_schedule_list"))

        schedule = CeleryBeatSchedule(
            name=name,
            task_name=task_name,
            queue=queue,
            schedule_type=schedule_type,
            interval_seconds=interval_seconds if schedule_type == "interval" else None,
            crontab_minute=crontab_minute if schedule_type == "crontab" else None,
            crontab_hour=crontab_hour if schedule_type == "crontab" else None,
            crontab_day_of_week=crontab_day_of_week if schedule_type == "crontab" else None,
            crontab_day_of_month=crontab_day_of_month if schedule_type == "crontab" else None,
            crontab_month_of_year=crontab_month_of_year if schedule_type == "crontab" else None,
            enabled=enabled,
            hospital_id=hospital_id,
            user_id=user_id,
            created_by_id=current_user.id,
        )
        db.add(schedule)

    flash("Schedule created.", "success")
    return redirect(url_for("admin.celery_schedule_list"))


@login_required
@roles_required("admin")
def celery_schedule_update(schedule_id: int):
    with transaction_scope() as db:
        schedule = db.query(CeleryBeatSchedule).filter(CeleryBeatSchedule.id == schedule_id).first()
        if not schedule:
            flash("Schedule not found.", "danger")
            return redirect(url_for("admin.celery_schedule_list"))

        name = (request.form.get("name") or schedule.name).strip()
        task_name = (request.form.get("task_name") or schedule.task_name).strip()
        schedule_type = (request.form.get("schedule_type") or schedule.schedule_type).strip()
        queue = (request.form.get("queue") or "").strip() or None
        interval_seconds = _parse_optional_int(request.form.get("interval_seconds"))
        crontab_minute = (request.form.get("crontab_minute") or "").strip() or None
        crontab_hour = (request.form.get("crontab_hour") or "").strip() or None
        crontab_day_of_week = (request.form.get("crontab_day_of_week") or "").strip() or None
        crontab_day_of_month = (request.form.get("crontab_day_of_month") or "").strip() or None
        crontab_month_of_year = (request.form.get("crontab_month_of_year") or "").strip() or None
        enabled = request.form.get("enabled") == "on"
        hospital_id = _parse_optional_int(request.form.get("hospital_id"))
        user_id = _parse_optional_int(request.form.get("user_id")) or schedule.user_id or current_user.id

        if not name or not task_name:
            flash("Name and task name are required.", "danger")
            return redirect(url_for("admin.celery_schedule_list"))

        if schedule_type not in {"interval", "crontab"}:
            flash("Invalid schedule type.", "danger")
            return redirect(url_for("admin.celery_schedule_list"))

        if schedule_type == "interval" and not interval_seconds:
            flash("Interval seconds are required for interval schedules.", "danger")
            return redirect(url_for("admin.celery_schedule_list"))

        if name != schedule.name:
            existing = db.query(CeleryBeatSchedule).filter(CeleryBeatSchedule.name == name).first()
            if existing:
                flash("Schedule name already exists.", "danger")
                return redirect(url_for("admin.celery_schedule_list"))

        schedule.name = name
        schedule.task_name = task_name
        schedule.queue = queue
        schedule.schedule_type = schedule_type
        schedule.interval_seconds = interval_seconds if schedule_type == "interval" else None
        schedule.crontab_minute = crontab_minute if schedule_type == "crontab" else None
        schedule.crontab_hour = crontab_hour if schedule_type == "crontab" else None
        schedule.crontab_day_of_week = crontab_day_of_week if schedule_type == "crontab" else None
        schedule.crontab_day_of_month = crontab_day_of_month if schedule_type == "crontab" else None
        schedule.crontab_month_of_year = crontab_month_of_year if schedule_type == "crontab" else None
        schedule.enabled = enabled
        schedule.hospital_id = hospital_id
        schedule.user_id = user_id

    flash("Schedule updated.", "success")
    return redirect(url_for("admin.celery_schedule_list"))


@login_required
@roles_required("admin")
def celery_schedule_delete(schedule_id: int):
    with transaction_scope() as db:
        schedule = db.query(CeleryBeatSchedule).filter(CeleryBeatSchedule.id == schedule_id).first()
        if not schedule:
            flash("Schedule not found.", "danger")
            return redirect(url_for("admin.celery_schedule_list"))
        db.delete(schedule)

    flash("Schedule deleted.", "success")
    return redirect(url_for("admin.celery_schedule_list"))
