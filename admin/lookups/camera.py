from flask import render_template, request, redirect, url_for, flash
from flask.typing import ResponseReturnValue
from sqlalchemy import select, func

from db_transaction_manager import transaction_scope, get_db_session
from models import Camera
from auth.roles import roles_required

MODEL_NAME = "camera"
TITLE = "Camera"
LIST_ENDPOINT = "admin.list_cameras"
EDIT_ENDPOINT = "admin.edit_camera"
DELETE_ENDPOINT = "admin.delete_camera"


@roles_required("admin")
def list_cameras() -> ResponseReturnValue:
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        is_zip_upload_enabled = request.form.get("is_zip_upload_enabled") == "on"
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        with transaction_scope() as db:
            exists = db.execute(
                select(Camera).where(func.lower(Camera.name) == name.lower())
            ).scalar_one_or_none()
            if exists:
                flash(f"{TITLE} '{name}' already exists.", "warning")
            else:
                db.add(Camera(name=name, is_zip_upload_enabled=is_zip_upload_enabled))
                flash(f"{TITLE} '{name}' added successfully.", "success")

        return redirect(url_for(LIST_ENDPOINT))

    with get_db_session() as db:
        items = db.scalars(select(Camera).order_by(Camera.id)).all()
        return render_template(
            "admin/lookup_list.html",
            items=items,
            model_name=MODEL_NAME,
            title=TITLE,
            hospitals=None,
            show_zip_upload_flag=True,
            list_endpoint=LIST_ENDPOINT,
            edit_endpoint=EDIT_ENDPOINT,
            delete_endpoint=DELETE_ENDPOINT,
        )


@roles_required("admin")
def edit_camera(item_id: int) -> ResponseReturnValue:
    with get_db_session() as db:
        item = db.get(Camera, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        if request.method == "GET":
            return render_template(
                "admin/lookup_edit.html",
                item=item,
                model_name=MODEL_NAME,
                title=f"Edit {TITLE}",
                hospitals=None,
                show_zip_upload_flag=True,
                list_endpoint=LIST_ENDPOINT,
                edit_endpoint=EDIT_ENDPOINT,
            )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        is_zip_upload_enabled = request.form.get("is_zip_upload_enabled") == "on"
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(EDIT_ENDPOINT, item_id=item_id))

        with transaction_scope() as db:
            item = db.get(Camera, item_id)
            if not item:
                flash("Item not found.", "danger")
                return redirect(url_for(LIST_ENDPOINT))

            item.name = name
            item.is_zip_upload_enabled = is_zip_upload_enabled
            flash(f"{TITLE} updated.", "success")
            return redirect(url_for(LIST_ENDPOINT))


@roles_required("admin")
def delete_camera(item_id: int) -> ResponseReturnValue:
    with transaction_scope() as db:
        item = db.get(Camera, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        try:
            db.delete(item)
            db.commit()
            flash(f"{TITLE} '{item.name}' deleted successfully.", "success")
        except Exception as exc:
            db.rollback()
            flash(f"Error deleting {TITLE}: {str(exc)}", "danger")

    return redirect(url_for(LIST_ENDPOINT))
