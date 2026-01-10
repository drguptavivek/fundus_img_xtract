import secrets

from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from auth.roles import roles_required
from auth.security import hash_password
from models import AIModel, User
from db_transaction_manager import transaction_scope, get_db_session

AI_MODEL_LIST_ROUTE = "admin.list_and_create_ai_model"


def _create_ai_model_user(db_session: Session, model: AIModel) -> User:
    username = f"aimodel_{model.id}"
    existing = db_session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing:
        return existing

    display_parts = [part for part in [model.name, model.version] if part]
    display_name = "AI Model"
    if display_parts:
        display_name = f"AI Model: {' '.join(display_parts)}"

    user = User(
        username=username,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        is_active=False,
        full_name=display_name,
        designation="AI Model",
    )
    db_session.add(user)
    return user


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
            with transaction_scope() as db:
                # Check for duplicate name and version
                exists = db.execute(
                    select(AIModel)
                    .where(func.lower(AIModel.name) == name.lower())
                    .where(func.lower(AIModel.version) == version.lower())
                ).scalar_one_or_none()

                if exists:
                    flash(f"AI Model '{name}' version '{version}' already exists.", "warning")
                else:
                    model = AIModel(name=name, version=version, description=description)
                    db.add(model)
                    db.flush()
                    _create_ai_model_user(db, model)
                    flash(f"AI Model '{name}' version '{version}' added successfully.", "success")

        return redirect(url_for(AI_MODEL_LIST_ROUTE))

    # --- Handle listing ---
    with get_db_session() as db:
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
    with get_db_session() as db:
        item = db.get(AIModel, item_id)
        if not item:
            flash("AI Model not found.", "danger")
            return redirect(url_for(AI_MODEL_LIST_ROUTE))

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
                    # Use transaction_scope for write operations
                    with transaction_scope() as write_db:
                        item_to_update = write_db.get(AIModel, item_id)
                        item_to_update.name = name
                        item_to_update.version = version
                        item_to_update.description = description
                    flash(f"AI Model '{name}' updated.", "success")
                    return redirect(url_for(AI_MODEL_LIST_ROUTE))

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "admin/ai_model_edit.html",
            item=item,
            title="Edit AI Model",
        )


@roles_required("admin")
def delete_ai_model(item_id):
    """Delete an AI model."""
    with get_db_session() as db:
        item = db.get(AIModel, item_id)
        if not item:
            flash("AI Model not found.", "danger")
            return redirect(url_for(AI_MODEL_LIST_ROUTE))

        # Check if the item has related records that would prevent deletion
        # (Example: Check if any Grade records reference this AI model)
        from models import Grade
        related_grades = db.execute(
            select(Grade).where(Grade.ai_model_id == item_id)
        ).scalars().all()

        if related_grades:
            flash(f"Cannot delete AI Model '{item.name}' because it has associated grades. Remove all related grades first.", "danger")
            return redirect(url_for(AI_MODEL_LIST_ROUTE))

        try:
            # Use transaction_scope for delete operations
            with transaction_scope() as write_db:
                item_to_delete = write_db.get(AIModel, item_id)
                write_db.delete(item_to_delete)
            flash(f"AI Model '{item.name}' deleted successfully.", "success")
        except Exception as e:
            # Handle any database errors gracefully and show a user-friendly message
            flash(f"Error deleting AI Model: {str(e)}", "danger")

    return redirect(url_for(AI_MODEL_LIST_ROUTE))
