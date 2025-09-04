from flask import render_template, request, redirect, url_for, flash
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import Disease, DiseaseGrading, Session


def list_disease_gradings():
    """List all disease gradings with their associated diseases."""
    # Handle POST request for creating a new disease grading via HTMX
    if request.method == "POST":
        with Session() as db:
            disease_id = request.form.get("disease_id")
            impression = request.form.get("impression", "").strip()
            display_order = request.form.get("display_order", 0)
            is_active = bool(request.form.get("is_active"))
            
            error = None
            if not disease_id or not impression:
                error = "Disease and impression are required."
            else:
                try:
                    display_order = int(display_order)
                except ValueError:
                    error = "Display order must be a number."
            
            if not error:
                # Check for duplicate impression for this disease
                existing = db.execute(
                    select(DiseaseGrading)
                    .where(DiseaseGrading.disease_id == disease_id)
                    .where(func.lower(DiseaseGrading.impression) == func.lower(impression))
                ).scalar_one_or_none()
                
                if existing:
                    error = "This impression already exists for the selected disease."
            
            if error:
                flash(error, "danger")
            else:
                grading = DiseaseGrading(
                    disease_id=disease_id,
                    impression=impression,
                    display_order=display_order,
                    is_active=is_active
                )
                
                db.add(grading)
                db.commit()
                flash("Disease grading created successfully.", "success")
    
    # Get all disease gradings and diseases for display
    with Session() as db:
        gradings = db.execute(
            select(DiseaseGrading)
            .join(Disease)
            .order_by(Disease.name, DiseaseGrading.display_order)
            .options(selectinload(DiseaseGrading.disease))  # Eager load the disease relationship
        ).scalars().all()
        
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()

    # If this is an HTMX request, return only the list partial
    if request.headers.get('HX-Request'):
        return render_template("admin/partials/disease_gradings_list.html", gradings=gradings)
    
    # Otherwise return the full page
    return render_template("admin/disease_gradings.html", gradings=gradings, diseases=diseases)


def create_disease_grading():
    """Create a new disease grading."""
    with Session() as db:
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        
        if request.method == "POST":
            disease_id = request.form.get("disease_id")
            impression = request.form.get("impression", "").strip()
            display_order = request.form.get("display_order", 0)
            is_active = bool(request.form.get("is_active"))
            
            if not disease_id or not impression:
                flash("Disease and impression are required.", "danger")
                return render_template("admin/disease_grading_form.html", diseases=diseases, 
                                     disease_id=disease_id, impression=impression, 
                                     display_order=display_order, is_active=is_active)
            
            try:
                display_order = int(display_order)
            except ValueError:
                flash("Display order must be a number.", "danger")
                return render_template("admin/disease_grading_form.html", diseases=diseases, 
                                     disease_id=disease_id, impression=impression, 
                                     display_order=display_order, is_active=is_active)
            
            # Check for duplicate impression for this disease
            existing = db.execute(
                select(DiseaseGrading)
                .where(DiseaseGrading.disease_id == disease_id)
                .where(func.lower(DiseaseGrading.impression) == func.lower(impression))
            ).scalar_one_or_none()
            
            if existing:
                flash("This impression already exists for the selected disease.", "danger")
                return render_template("admin/disease_grading_form.html", diseases=diseases, 
                                     disease_id=disease_id, impression=impression, 
                                     display_order=display_order, is_active=is_active)
            
            grading = DiseaseGrading(
                disease_id=disease_id,
                impression=impression,
                display_order=display_order,
                is_active=is_active
            )
            
            db.add(grading)
            db.commit()
            
            flash("Disease grading created successfully.", "success")
            return redirect(url_for("admin.list_disease_gradings"))
        
        return render_template("admin/disease_grading_form.html", diseases=diseases)


def edit_disease_grading(grading_id):
    """Edit an existing disease grading."""
    with Session() as db:
        grading = db.get(DiseaseGrading, grading_id)
        if not grading:
            flash("Disease grading not found.", "danger")
            return redirect(url_for("admin.list_disease_gradings"))
        
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        
        if request.method == "POST":
            disease_id = request.form.get("disease_id")
            impression = request.form.get("impression", "").strip()
            display_order = request.form.get("display_order", 0)
            is_active = bool(request.form.get("is_active"))
            
            if not disease_id or not impression:
                flash("Disease and impression are required.", "danger")
                return render_template("admin/disease_grading_form.html", grading=grading, diseases=diseases, 
                                     disease_id=disease_id, impression=impression, 
                                     display_order=display_order, is_active=is_active)
            
            try:
                display_order = int(display_order)
            except ValueError:
                flash("Display order must be a number.", "danger")
                return render_template("admin/disease_grading_form.html", grading=grading, diseases=diseases, 
                                     disease_id=disease_id, impression=impression, 
                                     display_order=display_order, is_active=is_active)
            
            # Check for duplicate impression for this disease (excluding current record)
            existing = db.execute(
                select(DiseaseGrading)
                .where(DiseaseGrading.disease_id == disease_id)
                .where(func.lower(DiseaseGrading.impression) == func.lower(impression))
                .where(DiseaseGrading.id != grading_id)
            ).scalar_one_or_none()
            
            if existing:
                flash("This impression already exists for the selected disease.", "danger")
                return render_template("admin/disease_grading_form.html", grading=grading, diseases=diseases, 
                                     disease_id=disease_id, impression=impression, 
                                     display_order=display_order, is_active=is_active)
            
            grading.disease_id = disease_id
            grading.impression = impression
            grading.display_order = display_order
            grading.is_active = is_active
            
            db.commit()
            
            flash("Disease grading updated successfully.", "success")
            return redirect(url_for("admin.list_disease_gradings"))
        
        return render_template("admin/disease_grading_form.html", grading=grading, diseases=diseases)


def delete_disease_grading(grading_id):
    """Delete a disease grading."""
    with Session() as db:
        grading = db.get(DiseaseGrading, grading_id)
        if not grading:
            flash("Disease grading not found.", "danger")
            return redirect(url_for("admin.list_disease_gradings"))
        
        db.delete(grading)
        db.commit()
        
        flash("Disease grading deleted successfully.", "success")
        return redirect(url_for("admin.list_disease_gradings"))