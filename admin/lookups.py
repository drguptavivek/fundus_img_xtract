from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import Area, Camera, Disease, Hospital, LabUnit, Session


def _get_model_by_name(name):
    return {
        "hospital": Hospital,
        "lab_unit": LabUnit,
        "camera": Camera,
        "disease": Disease,
        "area": Area
    }.get(name)


def list_and_create_lookup(model_name):
    Model = _get_model_by_name(model_name)
    if not Model:
        flash(f"Invalid master list: {model_name}", "danger")
        return redirect(url_for("admin.users_list"))

    # --- Handle form submission ---
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Name is required.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        with Session() as db:
            if model_name == "lab_unit":
                hospital_id = request.form.get("hospital_id")
                if not hospital_id:
                    flash("Hospital is required for a Lab Unit.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

                hospital_id = int(hospital_id)

                # Check for duplicate LabUnit for this hospital
                exists = db.execute(
                    select(LabUnit)
                    .where(func.lower(LabUnit.name) == name.lower())
                    .where(LabUnit.hospital_id == hospital_id)
                ).scalar_one_or_none()

                if exists:
                    flash(f"Lab Unit '{name}' already exists for this hospital.", "warning")
                else:
                    db.add(LabUnit(name=name, hospital_id=hospital_id))
                    db.commit()
                    flash(f"Lab Unit '{name}' added successfully.", "success")

            else:
                # Check for duplicate name globally
                exists = db.execute(
                    select(Model)
                    .where(func.lower(Model.name) == name.lower())
                ).scalar_one_or_none()

                if exists:
                    flash(f"{model_name.replace('_', ' ').title()} '{name}' already exists.", "warning")
                else:
                    db.add(Model(name=name))
                    db.commit()
                    flash(f"{model_name.replace('_', ' ').title()} '{name}' added successfully.", "success")

        return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

    # --- Handle listing ---
    with Session() as db:
        stmt = select(Model).order_by(Model.id)

        # Eager-load hospital relationship if model is LabUnit
        if model_name == "lab_unit":
            stmt = stmt.options(selectinload(LabUnit.hospital))

        items = db.scalars(stmt).all()
        hospitals = db.scalars(select(Hospital).order_by(Hospital.id)).all() if model_name == "lab_unit" else None

    return render_template(
        "admin/lookup_list.html",
        items=items,
        model_name=model_name,
        title=model_name.replace("_", " ").title(),
        hospitals=hospitals
    )


def edit_lookup(model_name, item_id):
    Model = _get_model_by_name(model_name)
    if not Model:
        flash(f"Invalid master list: {model_name}", "danger")
        return redirect(url_for("admin.users_list"))

    with Session() as db:
        item = db.get(Model, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        # Prevent editing of core diseases to change their names
        core_disease_names = None
        if model_name == "disease":
            from ensure_core_diseases import is_core_disease, CORE_DISEASES
            if is_core_disease(item_id):
                core_disease_names = {v.lower(): k for k, v in CORE_DISEASES.items()}

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Name is required.", "danger")
            else:
                # Check if trying to change a core disease name
                if model_name == "disease" and core_disease_names is not None:
                    original_name = item.name
                    if original_name.lower() in core_disease_names and name.lower() != original_name.lower():
                        flash(f"Core disease '{original_name}' cannot be renamed. The name must remain '{original_name}'.", "danger")
                        return render_template(
                            "admin/lookup_edit.html",
                            item=item,
                            model_name=model_name,
                            title=f"Edit {model_name.replace('_', ' ').title()}",
                            hospitals=None
                        )

                item.name = name
                if model_name == "lab_unit":
                    hospital_id = request.form.get("hospital_id")
                    if not hospital_id:
                        flash("Hospital is required for a Lab Unit.", "danger")
                        return redirect(url_for("admin.edit_lookup", model_name=model_name, item_id=item_id))
                    item.hospital_id = int(hospital_id)

                db.commit()
                flash(f"{model_name.replace('_', ' ').title()} updated.", "success")
                return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        hospitals = db.scalars(select(Hospital).order_by(Hospital.name)).all() if model_name == "lab_unit" else None

    return render_template(
        "admin/lookup_edit.html",
        item=item,
        model_name=model_name,
        title=f"Edit {model_name.replace('_', ' ').title()}",
        hospitals=hospitals
    )


def delete_lookup(model_name, item_id):
    Model = _get_model_by_name(model_name)
    if not Model:
        flash(f"Invalid master list: {model_name}", "danger")
        return redirect(url_for("admin.users_list"))
    
    # Prevent deletion of core diseases
    if model_name == "disease":
        from ensure_core_diseases import is_core_disease
        if is_core_disease(item_id):
            flash("Core diseases (Glaucoma, DR, AMD) cannot be deleted.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
    
    with Session() as db:
        item = db.get(Model, item_id)
        if item:
            db.delete(item)
            db.commit()
            flash(f"{model_name.replace('_', ' ').title()} deleted.", "success")
    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))