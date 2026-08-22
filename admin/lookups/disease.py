from flask import render_template, request, redirect, url_for, flash
from flask.typing import ResponseReturnValue
from sqlalchemy import select, func

from db_transaction_manager import transaction_scope, get_db_session
from models import Disease, DiseaseGrading
from auth.roles import roles_required

MODEL_NAME = "disease"
TITLE = "Disease"
LIST_ENDPOINT = "admin.list_diseases"
EDIT_ENDPOINT = "admin.edit_disease"
DELETE_ENDPOINT = "admin.delete_disease"
CORE_DISEASE_IDS = {1, 2, 3}


def _is_core_disease(item_id: int) -> bool:
    return item_id in CORE_DISEASE_IDS


@roles_required("admin")
def list_diseases() -> ResponseReturnValue:
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        with transaction_scope() as db:
            exists = db.execute(
                select(Disease).where(func.lower(Disease.name) == name.lower())
            ).scalar_one_or_none()
            if exists:
                flash(f"{TITLE} '{name}' already exists.", "warning")
            else:
                db.add(Disease(name=name))
                flash(f"{TITLE} '{name}' added successfully.", "success")

        return redirect(url_for(LIST_ENDPOINT))

    with get_db_session() as db:
        items = db.scalars(select(Disease).order_by(Disease.id)).all()
        return render_template(
            "admin/lookup_list.html",
            items=items,
            model_name=MODEL_NAME,
            title=TITLE,
            hospitals=None,
            list_endpoint=LIST_ENDPOINT,
            edit_endpoint=EDIT_ENDPOINT,
            delete_endpoint=DELETE_ENDPOINT,
            core_disease_ids=CORE_DISEASE_IDS,
        )


@roles_required("admin")
def edit_disease(item_id: int) -> ResponseReturnValue:
    with get_db_session() as db:
        item = db.get(Disease, item_id)
        if not item:
            flash("Disease not found.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        if request.method == "GET":
            return render_template(
                "admin/lookup_edit.html",
                item=item,
                model_name=MODEL_NAME,
                title=f"Edit {TITLE}",
                hospitals=None,
                list_endpoint=LIST_ENDPOINT,
                edit_endpoint=EDIT_ENDPOINT,
                core_disease_ids=CORE_DISEASE_IDS,
            )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(EDIT_ENDPOINT, item_id=item_id))

        with transaction_scope() as db:
            item = db.get(Disease, item_id)
            if not item:
                flash("Item not found.", "danger")
                return redirect(url_for(LIST_ENDPOINT))

            if _is_core_disease(item_id) and item.name.lower() != name.lower():
                flash(
                    f"Core disease '{item.name}' cannot be renamed. The name must remain '{item.name}'.",
                    "danger",
                )
                return redirect(url_for(EDIT_ENDPOINT, item_id=item_id))

            item.name = name
            flash(f"{TITLE} updated.", "success")
            return redirect(url_for(LIST_ENDPOINT))


@roles_required("admin")
def delete_disease(item_id: int) -> ResponseReturnValue:
    from models import (
        DirectImageUpload,
        GradingTask,
        Grade,
        UserDiseaseUnitRole,
    )

    if _is_core_disease(item_id):
        flash("Core diseases (Glaucoma, DR, AMD) cannot be deleted.", "danger")
        return redirect(url_for(LIST_ENDPOINT))

    with transaction_scope() as db:
        item = db.get(Disease, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        related_gradings = db.execute(
            select(DiseaseGrading).where(DiseaseGrading.disease_id == item_id)
        ).scalars().all()
        if related_gradings:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it has associated disease gradings. "
                "Remove all associated gradings first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_direct_uploads = db.execute(
            select(DirectImageUpload).where(DirectImageUpload.disease_id == item_id)
        ).scalars().all()
        if related_direct_uploads:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it is used in direct image uploads. "
                "Remove all related uploads first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_tasks = db.execute(
            select(GradingTask).where(GradingTask.disease_id == item_id)
        ).scalars().all()
        if related_tasks:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it has associated grading tasks. "
                "Remove all related tasks first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_grades = db.execute(
            select(Grade).where(Grade.disease_grading_id.in_(
                select(DiseaseGrading.id).where(DiseaseGrading.disease_id == item_id)
            ))
        ).scalars().all()
        if related_grades:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it has associated grades. "
                "Remove all related grades first.",
                "danger",
            )
            return redirect(url_for(LIST_ENDPOINT))

        related_user_roles = db.execute(
            select(UserDiseaseUnitRole).where(UserDiseaseUnitRole.disease_id == item_id)
        ).scalars().all()
        if related_user_roles:
            flash(
                f"Cannot delete {TITLE.lower()} '{item.name}' because it is used in user disease unit roles. "
                "Remove all related user role assignments first.",
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
