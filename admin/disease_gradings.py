"""
Simplified Disease Gradings Management
Handles disease gradings and their features in a streamlined manner.
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import Disease, DiseaseGrading, Session
import json


def list_disease_gradings():
    """List all disease gradings and handle creation/update."""
    if request.method == "POST":
        with Session() as db:
            grading_id = request.form.get("grading_id")
            disease_id = request.form.get("disease_id")
            impression = request.form.get("impression", "").strip()
            display_order = request.form.get("display_order", 0)
            is_active = request.form.get("is_active") == "1"
            guidelines = request.form.get("guidelines", "").strip()
            
            # Process features from form data
            features = []
            feature_labels = request.form.getlist("feature_label")
            feature_sr_nos = request.form.getlist("feature_sr_no")
            
            # Handle both new features and existing features
            for i, label in enumerate(feature_labels):
                if label.strip():  # Only include non-empty labels
                    sr_no = int(feature_sr_nos[i]) if i < len(feature_sr_nos) and feature_sr_nos[i] else i + 1
                    features.append({
                        "sr_no": sr_no,
                        "label": label.strip()
                    })
            
            # If no new features were added but we have existing features, preserve them
            if not features and grading_id:
                # Preserve existing features when editing without adding new ones
                existing_grading = db.get(DiseaseGrading, int(grading_id))
                if existing_grading and existing_grading.features_json:
                    features_json = existing_grading.features_json
            else:
                # Renumber features sequentially
                for idx, feature in enumerate(features, 1):
                    feature["sr_no"] = idx
                
                features_json = json.dumps({"features": features}) if features else None
            
            # Validation
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
                        grading.guidelines = guidelines or None
                        grading.features_json = features_json
                        flash("Disease grading updated successfully.", "success")
                    else:
                        flash("Error: Disease grading not found for update.", "danger")
                else:
                    # Create new grading
                    grading = DiseaseGrading(
                        disease_id=disease_id,
                        impression=impression,
                        display_order=display_order,
                        is_active=is_active,
                        guidelines=guidelines or None,
                        features_json=features_json
                    )
                    db.add(grading)
                    flash("Disease grading created successfully.", "success")
                
                db.commit()
                return redirect(url_for('admin.list_disease_gradings'))
    
    # GET request - show the form and list
    with Session() as db:
        gradings = db.execute(
            select(DiseaseGrading)
            .join(Disease)
            .order_by(Disease.name, DiseaseGrading.display_order)
            .options(selectinload(DiseaseGrading.disease))
        ).scalars().all()
        
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()

    return render_template("admin/disease_gradings.html", gradings=gradings, diseases=diseases)


def edit_disease_grading(grading_id):
    """Edit a specific disease grading."""
    with Session() as db:
        grading = db.get(DiseaseGrading, grading_id)
        if not grading:
            flash("Disease grading not found.", "danger")
            return redirect(url_for('admin.list_disease_gradings'))
        
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        return render_template("admin/disease_gradings.html", grading=grading, diseases=diseases)


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
        
        return redirect(url_for('admin.list_disease_gradings'))
