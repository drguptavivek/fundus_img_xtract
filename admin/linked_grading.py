import logging

from flask import render_template, request, redirect, url_for, flash
from flask.typing import ResponseReturnValue
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import transaction_scope, get_db_session
from models import Disease, LinkedDiseaseGrading
from utils.log_sanitize import sanitize_log_value

logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("admin.audit")


@roles_required("admin")
def linked_disease_gradings_list() -> ResponseReturnValue:
    if request.method == "POST":
        primary_id_raw = request.form.get("primary_disease_id", "").strip()
        linked_id_raw = request.form.get("linked_disease_id", "").strip()
        display_order_raw = request.form.get("display_order", "0").strip()
        is_active = request.form.get("is_active") == "1"

        error = None
        if not primary_id_raw or not linked_id_raw:
            error = "Primary and linked disease are required."

        try:
            primary_id = int(primary_id_raw)
            linked_id = int(linked_id_raw)
        except ValueError:
            error = "Disease selection is invalid."
            primary_id = None
            linked_id = None

        try:
            display_order = int(display_order_raw)
        except ValueError:
            display_order = 0
            if not error:
                error = "Display order must be a number."

        if not error and primary_id == linked_id:
            error = "Primary and linked disease must be different."

        if error:
            flash(error, "danger")
            return redirect(url_for("admin.linked_disease_gradings_list"))

        with transaction_scope() as db:
            primary = db.get(Disease, primary_id)
            linked = db.get(Disease, linked_id)

            if not primary or not linked:
                flash("Selected disease not found.", "danger")
                return redirect(url_for("admin.linked_disease_gradings_list"))

            existing_pair = db.execute(
                select(LinkedDiseaseGrading)
                .where(LinkedDiseaseGrading.primary_disease_id == primary_id)
                .where(LinkedDiseaseGrading.linked_disease_id == linked_id)
            ).scalar_one_or_none()
            if existing_pair:
                flash("This link already exists.", "warning")
                return redirect(url_for("admin.linked_disease_gradings_list"))

            existing_linked = db.execute(
                select(LinkedDiseaseGrading)
                .options(selectinload(LinkedDiseaseGrading.primary_disease))
                .where(LinkedDiseaseGrading.linked_disease_id == linked_id)
            ).scalar_one_or_none()
            if existing_linked:
                primary_name = (
                    existing_linked.primary_disease.name
                    if existing_linked.primary_disease
                    else "Unknown"
                )
                flash(
                    f"'{linked.name}' is already linked to '{primary_name}'. Delink first before relinking.",
                    "danger",
                )
                return redirect(url_for("admin.linked_disease_gradings_list"))

            link = LinkedDiseaseGrading(
                primary_disease_id=primary_id,
                linked_disease_id=linked_id,
                display_order=display_order,
                is_active=is_active,
            )
            db.add(link)

            try:
                audit_logger.info(
                    "Linked grading created by '%s': primary='%s' linked='%s' order='%s' active='%s'",
                    sanitize_log_value(getattr(current_user, "username", "unknown")),
                    sanitize_log_value(primary.name),
                    sanitize_log_value(linked.name),
                    sanitize_log_value(display_order),
                    sanitize_log_value(is_active),
                )
            except Exception as exc:
                logger.warning("Failed to audit linked grading create: %s", sanitize_log_value(exc))

            flash("Linked grading created successfully.", "success")

        return redirect(url_for("admin.linked_disease_gradings_list"))

    with get_db_session() as db:
        links = db.execute(
            select(LinkedDiseaseGrading)
            .options(
                selectinload(LinkedDiseaseGrading.primary_disease),
                selectinload(LinkedDiseaseGrading.linked_disease),
            )
            .order_by(
                LinkedDiseaseGrading.primary_disease_id,
                LinkedDiseaseGrading.display_order,
                LinkedDiseaseGrading.id,
            )
        ).scalars().all()

        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()

        return render_template(
            "admin/linked_disease_gradings.html",
            links=links,
            diseases=diseases,
        )


@roles_required("admin")
def edit_linked_disease_grading(link_id: int) -> ResponseReturnValue:
    with get_db_session() as db:
        link = db.execute(
            select(LinkedDiseaseGrading)
            .options(
                selectinload(LinkedDiseaseGrading.primary_disease),
                selectinload(LinkedDiseaseGrading.linked_disease),
            )
            .where(LinkedDiseaseGrading.id == link_id)
        ).scalar_one_or_none()

        if not link:
            flash("Linked grading not found.", "danger")
            return redirect(url_for("admin.linked_disease_gradings_list"))

        if request.method == "GET":
            diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
            return render_template(
                "admin/linked_disease_grading_edit.html",
                link=link,
                diseases=diseases,
            )

    if request.method == "POST":
        primary_id_raw = request.form.get("primary_disease_id", str(link.primary_disease_id)).strip()
        linked_id_raw = request.form.get("linked_disease_id", str(link.linked_disease_id)).strip()
        display_order_raw = request.form.get("display_order", "0").strip()
        is_active = request.form.get("is_active") == "1"

        try:
            primary_id = int(primary_id_raw)
            linked_id = int(linked_id_raw)
        except ValueError:
            flash("Disease selection is invalid.", "danger")
            return redirect(url_for("admin.edit_linked_disease_grading", link_id=link_id))

        if primary_id != link.primary_disease_id or linked_id != link.linked_disease_id:
            flash("Delink first before relinking to a different disease.", "danger")
            return redirect(url_for("admin.edit_linked_disease_grading", link_id=link_id))

        try:
            display_order = int(display_order_raw)
        except ValueError:
            flash("Display order must be a number.", "danger")
            return redirect(url_for("admin.edit_linked_disease_grading", link_id=link_id))

        with transaction_scope() as db:
            link = db.get(LinkedDiseaseGrading, link_id)
            if not link:
                flash("Linked grading not found.", "danger")
                return redirect(url_for("admin.linked_disease_gradings_list"))

            link.display_order = display_order
            link.is_active = is_active

            primary = db.get(Disease, link.primary_disease_id)
            linked = db.get(Disease, link.linked_disease_id)

            try:
                audit_logger.info(
                    "Linked grading updated by '%s': primary='%s' linked='%s' order='%s' active='%s'",
                    sanitize_log_value(getattr(current_user, "username", "unknown")),
                    sanitize_log_value(primary.name if primary else link.primary_disease_id),
                    sanitize_log_value(linked.name if linked else link.linked_disease_id),
                    sanitize_log_value(display_order),
                    sanitize_log_value(is_active),
                )
            except Exception as exc:
                logger.warning("Failed to audit linked grading update: %s", sanitize_log_value(exc))

            flash("Linked grading updated successfully.", "success")
            return redirect(url_for("admin.linked_disease_gradings_list"))


@roles_required("admin")
def delete_linked_disease_grading(link_id: int) -> ResponseReturnValue:
    with transaction_scope() as db:
        link = db.execute(
            select(LinkedDiseaseGrading)
            .options(
                selectinload(LinkedDiseaseGrading.primary_disease),
                selectinload(LinkedDiseaseGrading.linked_disease),
            )
            .where(LinkedDiseaseGrading.id == link_id)
        ).scalar_one_or_none()

        if not link:
            flash("Linked grading not found.", "danger")
            return redirect(url_for("admin.linked_disease_gradings_list"))

        primary_name = link.primary_disease.name if link.primary_disease else link.primary_disease_id
        linked_name = link.linked_disease.name if link.linked_disease else link.linked_disease_id

        db.delete(link)

        try:
            audit_logger.info(
                "Linked grading deleted by '%s': primary='%s' linked='%s'",
                sanitize_log_value(getattr(current_user, "username", "unknown")),
                sanitize_log_value(primary_name),
                sanitize_log_value(linked_name),
            )
        except Exception as exc:
            logger.warning("Failed to audit linked grading delete: %s", sanitize_log_value(exc))

        flash("Linked grading deleted successfully.", "success")

        return redirect(url_for("admin.linked_disease_gradings_list"))
