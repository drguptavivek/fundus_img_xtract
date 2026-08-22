from flask import render_template, request, redirect, url_for, flash
from flask.typing import ResponseReturnValue
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from db_transaction_manager import transaction_scope, get_db_session
from models import Hospital, LabUnit
from auth.roles import roles_required

MODEL_NAME = "lab_unit"
TITLE = "Lab Unit"
LIST_ENDPOINT = "admin.list_lab_units"
EDIT_ENDPOINT = "admin.edit_lab_unit"
DELETE_ENDPOINT = "admin.delete_lab_unit"


@roles_required("admin")
def list_lab_units() -> ResponseReturnValue:
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hospital_id = request.form.get("hospital_id")
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(LIST_ENDPOINT))
        if not hospital_id:
            flash("Hospital is required for a Lab Unit.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        with transaction_scope() as db:
            hospital_id_int = int(hospital_id)
            exists = db.execute(
                select(LabUnit)
                .where(func.lower(LabUnit.name) == name.lower())
                .where(LabUnit.hospital_id == hospital_id_int)
            ).scalar_one_or_none()
            if exists:
                flash(f"{TITLE} '{name}' already exists for this hospital.", "warning")
            else:
                db.add(LabUnit(name=name, hospital_id=hospital_id_int))
                flash(f"{TITLE} '{name}' added successfully.", "success")

        return redirect(url_for(LIST_ENDPOINT))

    with get_db_session() as db:
        stmt = select(LabUnit).order_by(LabUnit.id).options(selectinload(LabUnit.hospital))
        items = db.scalars(stmt).all()
        hospitals = db.scalars(select(Hospital).order_by(Hospital.id)).all()
        return render_template(
            "admin/lookup_list.html",
            items=items,
            model_name=MODEL_NAME,
            title=TITLE,
            hospitals=hospitals,
            list_endpoint=LIST_ENDPOINT,
            edit_endpoint=EDIT_ENDPOINT,
            delete_endpoint=DELETE_ENDPOINT,
        )


@roles_required("admin")
def edit_lab_unit(item_id: int) -> ResponseReturnValue:
    with get_db_session() as db:
        item = db.get(LabUnit, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        if request.method == "GET":
            hospitals = db.scalars(select(Hospital).order_by(Hospital.name)).all()
            return render_template(
                "admin/lookup_edit.html",
                item=item,
                model_name=MODEL_NAME,
                title=f"Edit {TITLE}",
                hospitals=hospitals,
                list_endpoint=LIST_ENDPOINT,
                edit_endpoint=EDIT_ENDPOINT,
            )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        hospital_id = request.form.get("hospital_id")
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(EDIT_ENDPOINT, item_id=item_id))
        if not hospital_id:
            flash("Hospital is required for a Lab Unit.", "danger")
            return redirect(url_for(EDIT_ENDPOINT, item_id=item_id))

        with transaction_scope() as db:
            item = db.get(LabUnit, item_id)
            if not item:
                flash("Item not found.", "danger")
                return redirect(url_for(LIST_ENDPOINT))

            item.name = name
            item.hospital_id = int(hospital_id)
            flash(f"{TITLE} updated.", "success")
            return redirect(url_for(LIST_ENDPOINT))


@roles_required("admin")
def delete_lab_unit(item_id: int) -> ResponseReturnValue:
    from models import (
        DirectImageUpload,
        GradingTask,
        UserDiseaseUnitRole,
        PatientEncounters,
        EncounterFile,
    )

    with transaction_scope() as db:
        item = db.get(LabUnit, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        related_direct_uploads = db.execute(
            select(DirectImageUpload).where(DirectImageUpload.lab_unit_id == item_id)
        ).scalars().all()
        if related_direct_uploads:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it is used in direct image uploads. "
                "Remove all related uploads first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_tasks = db.execute(
            select(GradingTask).where(GradingTask.lab_unit_id == item_id)
        ).scalars().all()
        if related_tasks:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it has associated grading tasks. "
                "Remove all related tasks first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_user_roles = db.execute(
            select(UserDiseaseUnitRole).where(UserDiseaseUnitRole.lab_unit_id == item_id)
        ).scalars().all()
        if related_user_roles:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it is used in user disease unit roles. "
                "Remove all related user role assignments first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_encounters = db.execute(
            select(PatientEncounters).where(PatientEncounters.lab_unit_id == item_id)
        ).scalars().all()
        if related_encounters:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it is used in patient encounters. "
                "Remove all related encounters first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_files = db.execute(
            select(EncounterFile).where(EncounterFile.lab_unit_id == item_id)
        ).scalars().all()
        if related_files:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it is used in encounter files. "
                "Remove all related files first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        try:
            db.delete(item)
            db.commit()
            flash(f"{TITLE} '{item.name}' deleted successfully.", "success")
        except Exception as exc:
            db.rollback()
            flash(f"Error deleting {TITLE}: {str(exc)}", "danger")

    return redirect(url_for(LIST_ENDPOINT))
