"""
Simplified Disease Gradings Management
Handles disease gradings and their features in a streamlined manner.
"""

from flask import render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import select, func, delete
from sqlalchemy.orm import selectinload
from auth.roles import roles_required
from models import Disease, DiseaseGrading, GradingsFeatures
from db_transaction_manager import transaction_scope, get_db_session
import json

@roles_required('admin')
def list_disease_gradings():
    """List all disease gradings and handle creation/update."""
    if request.method == "POST":
        with transaction_scope() as db:
            grading_id = request.form.get("grading_id")
            disease_id = request.form.get("disease_id")
            impression = request.form.get("impression", "").strip()
            display_order = request.form.get("display_order", 0)
            is_active = request.form.get("is_active") == "1"
            guidelines = request.form.get("guidelines", "").strip()
            
            # Process features from form data
            feature_labels = request.form.getlist("feature_label")
            feature_sr_nos = request.form.getlist("feature_sr_no")
            
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
                # Get disease name for more informative messages
                disease = db.get(Disease, int(disease_id))
                disease_name = disease.name if disease else "Unknown"
                
                if grading_id:
                    # Update existing grading
                    grading = db.get(DiseaseGrading, int(grading_id))
                    if grading:
                        grading.disease_id = disease_id
                        grading.impression = impression
                        grading.display_order = display_order
                        grading.is_active = is_active
                        grading.guidelines = guidelines or None
                        
                        # Update features - delete existing and create new ones
                        db.execute(
                            delete(GradingsFeatures).where(GradingsFeatures.disease_grading_id == grading.id)
                        )
                        
                        # Add new features
                        for i, label in enumerate(feature_labels):
                            if label.strip():  # Only include non-empty labels
                                sr_no = int(feature_sr_nos[i]) if i < len(feature_sr_nos) and feature_sr_nos[i] else i + 1
                                feature = GradingsFeatures(
                                    disease_grading_id=grading.id,
                                    sr_no=sr_no,
                                    label=label.strip()
                                )
                                db.add(feature)
                        
                        flash(f"'{disease_name}': '{impression}' - Updated successfully.", "success")
                    else:
                        flash("Error: Disease grading not found for update.", "danger")
                else:
                    # Create new grading
                    grading = DiseaseGrading(
                        disease_id=disease_id,
                        impression=impression,
                        display_order=display_order,
                        is_active=is_active,
                        guidelines=guidelines or None
                    )
                    db.add(grading)
                    db.flush()  # Get the ID of the new grading
                    
                    # Add features
                    for i, label in enumerate(feature_labels):
                        if label.strip():  # Only include non-empty labels
                            sr_no = int(feature_sr_nos[i]) if i < len(feature_sr_nos) and feature_sr_nos[i] else i + 1
                            feature = GradingsFeatures(
                                disease_grading_id=grading.id,
                                sr_no=sr_no,
                                label=label.strip()
                            )
                            db.add(feature)
                    
                    flash(f"{disease_name}': '{impression}' - Created successfully.", "success")
                
                return redirect(url_for('admin.list_disease_gradings'))
    
    # GET request - show the form and list
    with get_db_session() as db:
        gradings = db.execute(
            select(DiseaseGrading)
            .join(Disease)
            .order_by(Disease.name, DiseaseGrading.display_order)
            .options(selectinload(DiseaseGrading.disease), selectinload(DiseaseGrading.features))
        ).scalars().all()
        
        diseases = db.execute(select(Disease).order_by(Disease.name)).scalars().all()
        
        return render_template("admin/disease_gradings.html", gradings=gradings, diseases=diseases)


@roles_required('admin')
def get_grading_features(grading_id):
    """Get features for a specific grading as JSON."""
    with get_db_session() as db:
        grading = db.execute(
            select(DiseaseGrading)
            .options(selectinload(DiseaseGrading.features))
            .where(DiseaseGrading.id == grading_id)
        ).scalar_one_or_none()
        
        if not grading:
            return jsonify({"error": "Grading not found"}), 404
        
        features = [
            {"sr_no": feature.sr_no, "label": feature.label}
            for feature in sorted(grading.features, key=lambda x: x.sr_no)
        ]
        
        return jsonify({"features": features})

@roles_required('admin')
def delete_disease_grading(grading_id):
    """Delete a disease grading."""
    with transaction_scope() as db:
        grading = db.execute(
            select(DiseaseGrading)
            .options(selectinload(DiseaseGrading.disease))
            .where(DiseaseGrading.id == grading_id)
        ).scalar_one_or_none()
        
        if not grading:
            flash("Disease grading not found.", "danger")
        else:
            disease_name = grading.disease.name if grading.disease else "Unknown"
            impression = grading.impression
            db.delete(grading)
            flash(f"{disease_name}': '{impression}' - Deleted successfully.", "success")
        
        return redirect(url_for('admin.list_disease_gradings'))
