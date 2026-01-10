from flask import render_template, request, redirect, url_for, flash
from flask.typing import ResponseReturnValue
from sqlalchemy import select, func

from db_transaction_manager import transaction_scope, get_db_session
from models import Area

MODEL_NAME = "area"
TITLE = "Area"
LIST_ENDPOINT = "admin.list_areas"
EDIT_ENDPOINT = "admin.edit_area"
DELETE_ENDPOINT = "admin.delete_area"


def list_areas() -> ResponseReturnValue:
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(LIST_ENDPOINT))

        with transaction_scope() as db:
            exists = db.execute(
                select(Area).where(func.lower(Area.name) == name.lower())
            ).scalar_one_or_none()
            if exists:
                flash(f"{TITLE} '{name}' already exists.", "warning")
            else:
                db.add(Area(name=name))
                flash(f"{TITLE} '{name}' added successfully.", "success")

        return redirect(url_for(LIST_ENDPOINT))

    with get_db_session() as db:
        items = db.scalars(select(Area).order_by(Area.id)).all()
        return render_template(
            "admin/lookup_list.html",
            items=items,
            model_name=MODEL_NAME,
            title=TITLE,
            hospitals=None,
            list_endpoint=LIST_ENDPOINT,
            edit_endpoint=EDIT_ENDPOINT,
            delete_endpoint=DELETE_ENDPOINT,
        )


def edit_area(item_id: int) -> ResponseReturnValue:
    with get_db_session() as db:
        item = db.get(Area, item_id)
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
                list_endpoint=LIST_ENDPOINT,
                edit_endpoint=EDIT_ENDPOINT,
            )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for(EDIT_ENDPOINT, item_id=item_id))

        with transaction_scope() as db:
            item = db.get(Area, item_id)
            if not item:
                flash("Item not found.", "danger")
                return redirect(url_for(LIST_ENDPOINT))

            item.name = name
            flash(f"{TITLE} updated.", "success")
            return redirect(url_for(LIST_ENDPOINT))


def delete_area(item_id: int) -> ResponseReturnValue:
    with transaction_scope() as db:
        item = db.get(Area, item_id)
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
