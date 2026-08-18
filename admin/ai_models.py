import secrets
import logging

import requests
from flask import render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from auth.roles import roles_required
from auth.security import hash_password
from models import AIModel, AIModelDisease, AIModelIntegration, Disease, Grade, User
from db_transaction_manager import transaction_scope, get_db_session
from utils.log_sanitize import sanitize_log_value
from remote_inference import encounter_service

AI_MODEL_LIST_ROUTE = "admin.list_and_create_ai_model"
WADHWANI_PROVIDER = "wadhwani_glaucoma"
WADHWANI_HEALTH_URL = "https://api-glaucoma.wadhwaniai.org/api/health/live"

logger = logging.getLogger("admin.ai_models")


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


def _integration_form_payload() -> tuple[bool, str, str]:
    link_enabled = request.form.get("link_to_wadhwani_glaucoma_api") == "on"
    client_id = request.form.get("wadhwani_client_id", "").strip()
    bearer_token = request.form.get("wadhwani_bearer_token", "").strip()
    return link_enabled, client_id, bearer_token


def _disease_ids_from_request() -> list[int]:
    disease_ids: list[int] = []
    for value in request.form.getlist("disease_ids"):
        try:
            disease_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return disease_ids


def _sync_ai_model_diseases(db_session: Session, model: AIModel, disease_ids: list[int]) -> None:
    requested_ids = set(disease_ids)
    existing_links = {
        link.disease_id: link
        for link in db_session.execute(
            select(AIModelDisease).where(AIModelDisease.ai_model_id == model.id)
        ).scalars()
    }
    for disease_id, link in existing_links.items():
        link.active = disease_id in requested_ids
    for disease_id in requested_ids - set(existing_links):
        db_session.add(AIModelDisease(ai_model_id=model.id, disease_id=disease_id, active=True))


def _validate_wadhwani_binding(
    db_session: Session,
    *,
    item_id: int | None,
    link_enabled: bool,
    client_id: str,
    bearer_token: str,
) -> str | None:
    if not link_enabled:
        return None

    if not client_id or not bearer_token:
        return "Client ID and Bearer Token are required when linking to the Wadhwani Glaucoma API."

    existing_link = db_session.execute(
        select(AIModelIntegration).where(AIModelIntegration.provider == WADHWANI_PROVIDER)
    ).scalar_one_or_none()
    if existing_link and existing_link.ai_model_id != item_id:
        linked_model = db_session.get(AIModel, existing_link.ai_model_id)
        linked_name = linked_model.name if linked_model else f"ID {existing_link.ai_model_id}"
        return f"Only one AI Model can be linked to the Wadhwani Glaucoma API. Currently linked: {linked_name}."

    return None


def _validate_ai_model_diseases(
    db_session: Session,
    *,
    disease_ids: list[int],
    link_enabled: bool,
) -> str | None:
    if not disease_ids:
        return "Select at least one disease for this AI Model."
    valid_disease_ids = {
        row[0]
        for row in db_session.execute(select(Disease.id).where(Disease.id.in_(set(disease_ids)))).all()
    }
    if valid_disease_ids != set(disease_ids):
        return "Selected disease is invalid."
    if link_enabled:
        glaucoma_id = db_session.execute(
            select(Disease.id).where(func.lower(Disease.name) == "glaucoma")
        ).scalar_one_or_none()
        if not glaucoma_id or glaucoma_id not in set(disease_ids):
            return "Wadhwani Glaucoma API models must be linked to the Glaucoma disease."
    return None


def _sync_wadhwani_integration(
    db_session: Session,
    *,
    model: AIModel,
    link_enabled: bool,
    client_id: str,
    bearer_token: str,
) -> None:
    integration = db_session.execute(
        select(AIModelIntegration).where(AIModelIntegration.ai_model_id == model.id)
    ).scalar_one_or_none()

    if not link_enabled:
        if integration:
            db_session.delete(integration)
        return

    if integration is None:
        integration = AIModelIntegration(
            ai_model_id=model.id,
            provider=WADHWANI_PROVIDER,
            is_enabled=True,
            client_id=client_id,
            bearer_token=bearer_token,
        )
        db_session.add(integration)
        return

    integration.provider = WADHWANI_PROVIDER
    integration.is_enabled = True
    integration.client_id = client_id
    integration.bearer_token = bearer_token


@roles_required("admin")
def list_and_create_ai_model():
    """List all AI models and handle creation."""
    # --- Handle form submission ---
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        version = request.form.get("version", "").strip()
        description = request.form.get("description", "").strip()
        disease_ids = _disease_ids_from_request()
        link_enabled, client_id, bearer_token = _integration_form_payload()

        if not name or not version:
            flash("Name and version are required.", "danger")
        else:
            with transaction_scope() as db:
                validation_error = _validate_wadhwani_binding(
                    db,
                    item_id=None,
                    link_enabled=link_enabled,
                    client_id=client_id,
                    bearer_token=bearer_token,
                )
                if validation_error:
                    flash(validation_error, "danger")
                    return redirect(url_for(AI_MODEL_LIST_ROUTE))
                validation_error = _validate_ai_model_diseases(
                    db,
                    disease_ids=disease_ids,
                    link_enabled=link_enabled,
                )
                if validation_error:
                    flash(validation_error, "danger")
                    return redirect(url_for(AI_MODEL_LIST_ROUTE))

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
                    _sync_ai_model_diseases(db, model, disease_ids)
                    _create_ai_model_user(db, model)
                    _sync_wadhwani_integration(
                        db,
                        model=model,
                        link_enabled=link_enabled,
                        client_id=client_id,
                        bearer_token=bearer_token,
                    )
                    flash(f"AI Model '{name}' version '{version}' added successfully.", "success")

        return redirect(url_for(AI_MODEL_LIST_ROUTE))

    # --- Handle listing ---
    with get_db_session() as db:
        stmt = (
            select(AIModel)
            .options(
                selectinload(AIModel.integration),
                selectinload(AIModel.disease_links).selectinload(AIModelDisease.disease),
            )
            .order_by(AIModel.id)
        )
        items = db.scalars(stmt).all()
        diseases = db.scalars(select(Disease).order_by(Disease.name)).all()
        madhunetra_integration = encounter_service.integration_context(db)
        
        return render_template(
            "admin/ai_model_list.html",
            items=items,
            diseases=diseases,
            madhunetra_integration=madhunetra_integration,
            title="AI Models",
        )


@roles_required("admin")
def edit_ai_model(item_id):
    """Edit an existing AI model."""
    with get_db_session() as db:
        item = db.execute(
            select(AIModel)
            .options(
                selectinload(AIModel.integration),
                selectinload(AIModel.disease_links).selectinload(AIModelDisease.disease),
            )
            .where(AIModel.id == item_id)
        ).scalar_one_or_none()
        if not item:
            flash("AI Model not found.", "danger")
            return redirect(url_for(AI_MODEL_LIST_ROUTE))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            version = request.form.get("version", "").strip()
            description = request.form.get("description", "").strip()
            disease_ids = _disease_ids_from_request()
            link_enabled, client_id, bearer_token = _integration_form_payload()

            if not name or not version:
                flash("Name and version are required.", "danger")
            else:
                validation_error = _validate_wadhwani_binding(
                    db,
                    item_id=item_id,
                    link_enabled=link_enabled,
                    client_id=client_id,
                    bearer_token=bearer_token,
                )
                if validation_error:
                    flash(validation_error, "danger")
                    return render_template(
                        "admin/ai_model_edit.html",
                        item=item,
                        diseases=db.scalars(select(Disease).order_by(Disease.name)).all(),
                        title="Edit AI Model",
                    )
                validation_error = _validate_ai_model_diseases(
                    db,
                    disease_ids=disease_ids,
                    link_enabled=link_enabled,
                )
                if validation_error:
                    flash(validation_error, "danger")
                    return render_template(
                        "admin/ai_model_edit.html",
                        item=item,
                        diseases=db.scalars(select(Disease).order_by(Disease.name)).all(),
                        title="Edit AI Model",
                    )

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
                        item_to_update = write_db.execute(
                            select(AIModel)
                            .options(
                                selectinload(AIModel.integration),
                                selectinload(AIModel.disease_links),
                            )
                            .where(AIModel.id == item_id)
                        ).scalar_one()
                        item_to_update.name = name
                        item_to_update.version = version
                        item_to_update.description = description
                        _sync_ai_model_diseases(write_db, item_to_update, disease_ids)
                        _sync_wadhwani_integration(
                            write_db,
                            model=item_to_update,
                            link_enabled=link_enabled,
                            client_id=client_id,
                            bearer_token=bearer_token,
                        )
                    flash(f"AI Model '{name}' updated.", "success")
                    return redirect(url_for(AI_MODEL_LIST_ROUTE))

        # Render template within the same session to avoid detached instance errors
        return render_template(
            "admin/ai_model_edit.html",
            item=item,
            diseases=db.scalars(select(Disease).order_by(Disease.name)).all(),
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


@roles_required("admin")
def test_ai_model_health(item_id: int):
    """Check the health of the linked Wadhwani Glaucoma API."""
    with get_db_session() as db:
        item = db.execute(
            select(AIModel)
            .options(selectinload(AIModel.integration))
            .where(AIModel.id == item_id)
        ).scalar_one_or_none()
        if not item:
            return jsonify({"success": False, "message": "AI Model not found"}), 404

        integration = item.integration
        if not integration or integration.provider != WADHWANI_PROVIDER:
            return jsonify({"success": False, "message": "AI Model is not linked to the Wadhwani Glaucoma API"}), 400
        provider = integration.provider

    try:
        response = requests.get(WADHWANI_HEALTH_URL, timeout=10)
        payload = response.json() if response.content else {}
    except requests.RequestException as exc:
        logger.warning(
            "Wadhwani health check failed for ai_model_id=%s: %s",
            sanitize_log_value(item_id),
            sanitize_log_value(str(exc)),
        )
        return jsonify({"success": False, "message": f"Health check failed: {exc}"}), 502
    except ValueError:
        payload = {}

    success = response.ok
    message = "Health check succeeded" if success else f"Health check failed with status {response.status_code}"
    return jsonify(
        {
            "success": success,
            "message": message,
            "status_code": response.status_code,
            "provider": provider,
            "health_url": WADHWANI_HEALTH_URL,
            "payload": payload,
        }
    ), (200 if success else 502)
