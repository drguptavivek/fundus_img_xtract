from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import AIModel, Session


@roles_required("admin")
def list_and_create_ai_model():
    """List all AI models and handle creation."""
    # --- Handle form submission ---
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        version = request.form.get("version", "").strip()
        description = request.form.get("description", "").strip()

        if not name or not version:
            flash("Name and version are required.", "danger")
        else:
            with Session() as db:
                # Check for duplicate name and version
                exists = db.execute(
                    select(AIModel)
                    .where(func.lower(AIModel.name) == name.lower())
                    .where(func.lower(AIModel.version) == version.lower())
                ).scalar_one_or_none()

                if exists:
                    flash(f"AI Model '{name}' version '{version}' already exists.", "warning")
                else:
                    db.add(AIModel(name=name, version=version, description=description))
                    db.commit()
                    flash(f"AI Model '{name}' version '{version}' added successfully.", "success")

        return redirect(url_for("admin.list_and_create_ai_model"))

    # --- Handle listing ---
    with Session() as db:
        stmt = select(AIModel).order_by(AIModel.id)
        items = db.scalars(stmt).all()

    return render_template(
        "admin/ai_model_list.html",
        items=items,
        title="AI Models",
    )


@roles_required("admin")
def edit_ai_model(item_id):
    """Edit an existing AI model."""
    with Session() as db:
        item = db.get(AIModel, item_id)
        if not item:
            flash("AI Model not found.", "danger")
            return redirect(url_for("admin.list_and_create_ai_model"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            version = request.form.get("version", "").strip()
            description = request.form.get("description", "").strip()

            if not name or not version:
                flash("Name and version are required.", "danger")
            else:
                # Check for duplicate name and version (excluding current item)
                exists = db.execute(
                    select(AIModel)
                    .where(func.lower(AIModel.name) == name.lower())
                    .where(func.lower(AIModel.version) == version.lower())
                    .where(AIModel.id != item_id)
                ).scalar_one_or_none()

                if exists:
                    flash(f"AI Model '{name}' version '{version}' already exists.", "warning")
                else:
                    item.name = name
                    item.version = version
                    item.description = description
                    db.commit()
                    flash(f"AI Model '{name}' updated.", "success")
                    return redirect(url_for("admin.list_and_create_ai_model"))

        return render_template(
            "admin/ai_model_edit.html",
            item=item,
            title="Edit AI Model",
        )


@roles_required("admin")
def delete_ai_model(item_id):
    """Delete an AI model."""
    with Session() as db:
        item = db.get(AIModel, item_id)
        if not item:
            flash("AI Model not found.", "danger")
            return redirect(url_for("admin.list_and_create_ai_model"))

        # Check if the item has related records that would prevent deletion
        # (Example: Check if any Grade records reference this AI model)
        from models import Grade
        related_grades = db.execute(
            select(Grade).where(Grade.ai_model_id == item_id)
        ).scalars().all()

        if related_grades:
            flash(f"Cannot delete AI Model '{item.name}' because it has associated grades. Remove all related grades first.", "danger")
            return redirect(url_for("admin.list_and_create_ai_model"))

        try:
            # Try to delete the item
            db.delete(item)
            db.commit()
            flash(f"AI Model '{item.name}' deleted successfully.", "success")
        except Exception as e:
            # Handle any database errors gracefully and show a user-friendly message
            db.rollback()
            flash(f"Error deleting AI Model: {str(e)}", "danger")

    return redirect(url_for("admin.list_and_create_ai_model"))