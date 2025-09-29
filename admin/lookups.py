from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import Area, Camera, Disease, Hospital, LabUnit, Session, DiseaseGrading


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
            if item_id in [1,2,3]:
                core_disease_names = {v.lower(): k for k, v in Disease.items()}

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
        if item_id in [1,2,3]:
            flash("Core diseases (Glaucoma, DR, AMD) cannot be deleted.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
    
    with Session() as db:
        item = db.get(Model, item_id)
        if not item:
            flash("Item not found.", "danger")
            return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))

        try:
            # Check if the item has related records that would prevent deletion
            from models import (
                DiseaseGrading, LabUnit, DirectImageUpload, 
                GradingTask, Grade, Consensus, AIGrade,
                UserDiseaseUnitRole
            )
            
            if model_name == "disease":
                # Check if any DiseaseGrading records reference this disease
                related_gradings = db.execute(
                    select(DiseaseGrading).where(DiseaseGrading.disease_id == item_id)
                ).scalars().all()
                
                if related_gradings:
                    flash(f"Cannot delete disease '{item.name}' because it has associated disease gradings. Remove all associated gradings first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any DirectImageUpload records reference this disease
                related_direct_uploads = db.execute(
                    select(DirectImageUpload).where(DirectImageUpload.disease_id == item_id)
                ).scalars().all()
                
                if related_direct_uploads:
                    flash(f"Cannot delete disease '{item.name}' because it is used in direct image uploads. Remove all related uploads first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any GradingTask records reference this disease
                related_tasks = db.execute(
                    select(GradingTask).where(GradingTask.disease_id == item_id)
                ).scalars().all()
                
                if related_tasks:
                    flash(f"Cannot delete disease '{item.name}' because it has associated grading tasks. Remove all related tasks first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any Grade records reference this disease
                related_grades = db.execute(
                    select(Grade).where(Grade.disease_grading_id.in_(
                        select(DiseaseGrading.id).where(DiseaseGrading.disease_id == item_id)
                    ))
                ).scalars().all()
                
                if related_grades:
                    flash(f"Cannot delete disease '{item.name}' because it has associated grades. Remove all related grades first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any AIGrade records reference this disease
                related_ai_grades = db.execute(
                    select(AIGrade).where(AIGrade.disease_id == item_id)
                ).scalars().all()
                
                if related_ai_grades:
                    flash(f"Cannot delete disease '{item.name}' because it has associated AI grades. Remove all related AI grades first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any UserDiseaseUnitRole records reference this disease
                related_user_roles = db.execute(
                    select(UserDiseaseUnitRole).where(UserDiseaseUnitRole.disease_id == item_id)
                ).scalars().all()
                
                if related_user_roles:
                    flash(f"Cannot delete disease '{item.name}' because it is used in user disease unit roles. Remove all related user role assignments first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
            
            elif model_name == "hospital":
                # Check if any LabUnit records reference this hospital
                related_lab_units = db.execute(
                    select(LabUnit).where(LabUnit.hospital_id == item_id)
                ).scalars().all()
                
                if related_lab_units:
                    flash(f"Cannot delete hospital '{item.name}' because it has associated lab units. Remove all associated lab units first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
            
            elif model_name == "lab_unit":
                # Check if any DirectImageUpload records reference this lab unit
                related_direct_uploads = db.execute(
                    select(DirectImageUpload).where(DirectImageUpload.lab_unit_id == item_id)
                ).scalars().all()
                
                if related_direct_uploads:
                    flash(f"Cannot delete lab unit '{item.name}' because it is used in direct image uploads. Remove all related uploads first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any GradingTask records reference this lab unit
                related_tasks = db.execute(
                    select(GradingTask).where(GradingTask.lab_unit_id == item_id)
                ).scalars().all()
                
                if related_tasks:
                    flash(f"Cannot delete lab unit '{item.name}' because it has associated grading tasks. Remove all related tasks first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any UserDiseaseUnitRole records reference this lab unit
                related_user_roles = db.execute(
                    select(UserDiseaseUnitRole).where(UserDiseaseUnitRole.lab_unit_id == item_id)
                ).scalars().all()
                
                if related_user_roles:
                    flash(f"Cannot delete lab unit '{item.name}' because it is used in user disease unit roles. Remove all related user role assignments first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any PatientEncounters records reference this lab unit
                from models import PatientEncounters
                related_encounters = db.execute(
                    select(PatientEncounters).where(PatientEncounters.lab_unit_id == item_id)
                ).scalars().all()
                
                if related_encounters:
                    flash(f"Cannot delete lab unit '{item.name}' because it is used in patient encounters. Remove all related encounters first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
                
                # Check if any EncounterFile records reference this lab unit
                from models import EncounterFile
                related_files = db.execute(
                    select(EncounterFile).where(EncounterFile.lab_unit_id == item_id)
                ).scalars().all()
                
                if related_files:
                    flash(f"Cannot delete lab unit '{item.name}' because it is used in encounter files. Remove all related files first.", "danger")
                    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))
            
            # Try to delete the item
            db.delete(item)
            db.commit()
            flash(f"{model_name.replace('_', ' ').title()} '{item.name}' deleted successfully.", "success")
        except Exception as e:
            # Handle any database errors gracefully and show a user-friendly message
            db.rollback()
            flash(f"Error deleting {model_name.replace('_', ' ').title()}: {str(e)}", "danger")
    
    return redirect(url_for("admin.list_and_create_lookup", model_name=model_name))