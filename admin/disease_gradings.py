from flask import render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import Disease, DiseaseGrading, Session


def list_disease_gradings():
    """List all disease gradings and handle creation/updates."""
    if request.method == "POST":
        with Session() as db:
            grading_id = request.form.get("grading_id")
            disease_id = request.form.get("disease_id")
            impression = request.form.get("impression", "").strip()
            display_order = request.form.get("display_order", 0)
            is_active = request.form.get("is_active") == "1"
            
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
                query = (
                    select(DiseaseGrading)
                    .where(DiseaseGrading.disease_id == disease_id)
                    .where(func.lower(DiseaseGrading.impression) == func.lower(impression))
                )
                if grading_id:
                    query = query.where(DiseaseGrading.id != int(grading_id))
                
                existing = db.execute(query).scalar_one_or_none()
                if existing:
                    error = "This impression already exists for the selected disease."

            if error:
                flash(error, "danger")
            else:
                if grading_id:
                    # Update existing grading
                    grading = db.get(DiseaseGrading, int(grading_id))
                    if grading:
                        grading.disease_id = disease_id
                        grading.impression = impression
                        grading.display_order = display_order
                        grading.is_active = is_active
                        flash("Disease grading updated successfully.", "success")
                    else:
                        flash("Error: Disease grading not found for update.", "danger")
                else:
                    # Create new grading
                    grading = DiseaseGrading(
                        disease_id=disease_id,
                        impression=impression,
                        display_order=display_order,
                        is_active=is_active
                    )
                    db.add(grading)
                    flash("Disease grading created successfully.", "success")
                
                db.commit()

            # After a POST, always re-query and return the partial for HTMX
            gradings = db.execute(
                select(DiseaseGrading)
                .join(Disease)
                .order_by(Disease.name, DiseaseGrading.display_order)
                .options(selectinload(DiseaseGrading.disease))
            ).scalars().all()
            return render_template("admin/partials/disease_gradings_list.html", gradings=gradings)
    
    # This part now only handles GET requests for the full page
    with Session() as db:
        gradings = db.execute(
            select(DiseaseGrading)
            .join(Disease)
            .order_by(Disease.name, DiseaseGrading.display_order)
            .options(selectinload(DiseaseGrading.disease))
        ).scalars().all()
        
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()

    return render_template("admin/disease_gradings.html", gradings=gradings, diseases=diseases)


def get_disease_grading_json(grading_id):
    """Get a single disease grading as JSON."""
    with Session() as db:
        grading = db.get(DiseaseGrading, grading_id)
        if not grading:
            return jsonify({"error": "Not found"}), 404
        return jsonify({
            "id": grading.id,
            "disease_id": grading.disease_id,
            "impression": grading.impression,
            "display_order": grading.display_order,
            "is_active": grading.is_active,
        })


def delete_disease_grading(grading_id):
    """Delete a disease grading."""
    with Session() as db:
        grading = db.get(DiseaseGrading, grading_id)
        if not grading:
            flash("Disease grading not found.", "danger")
        else:
            db.delete(grading)
            db.commit()
            flash("Disease grading deleted successfully.", "success")
        
        # After deleting, re-query and return the list partial
        gradings = db.execute(
            select(DiseaseGrading)
            .join(Disease)
            .order_by(Disease.name, DiseaseGrading.display_order)
            .options(selectinload(DiseaseGrading.disease))
        ).scalars().all()
        return render_template("admin/partials/disease_gradings_list.html", gradings=gradings)
