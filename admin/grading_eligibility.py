from flask import render_template, request, flash, redirect, url_for, jsonify
from sqlalchemy import select
from models import User, Disease, LabUnit, UserDiseaseUnitRole, Session
from auth.roles import roles_required

@roles_required('admin')
def manage_eligibility_users():
    """List all users to manage their grading eligibility."""
    with Session() as db:
        users = db.execute(
            select(User).order_by(User.username.asc())
        ).scalars().all()
    return render_template("admin/grading_eligibility_users.html", users=users)

@roles_required('admin')
def edit_eligibility(user_id):
    """Display and manage grading eligibility for a single user."""
    with Session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_eligibility_users"))
        
        # Handle form submission
        if request.method == 'POST':
            try:
                # Get the items from form data
                items_data = request.form.get('items')
                if not items_data:
                    flash("No data received.", "danger")
                    return redirect(url_for("admin.edit_eligibility", user_id=user_id))
                
                # Parse the JSON data
                import json
                items = json.loads(items_data)
                
                if not isinstance(items, list):
                    flash("Invalid data format.", "danger")
                    return redirect(url_for("admin.edit_eligibility", user_id=user_id))
                
                updated = []
                created = []
                deleted = []
                
                # Get existing records for this user
                existing_records = db.execute(
                    select(UserDiseaseUnitRole).where(
                        UserDiseaseUnitRole.user_id == user_id
                    )
                ).scalars().all()
                
                # Create a map of existing records for quick lookup
                existing_map = {
                    (r.disease_id, r.lab_unit_id): r 
                    for r in existing_records
                }
                
                # Process submitted items
                submitted_keys = set()
                for item in items:
                    disease_id = int(item.get('disease_id'))
                    lab_unit_id = int(item.get('lab_unit_id'))
                    can_grade_resident = bool(item.get('can_grade_resident', False))
                    can_grade_faculty = bool(item.get('can_grade_faculty', False))
                    can_arbitrate = bool(item.get('can_arbitrate', False))
                    active = bool(item.get('active', True))
                    
                    # Create key for tracking
                    key = (disease_id, lab_unit_id)
                    submitted_keys.add(key)
                    
                    # Validate FKs
                    if not db.get(Disease, disease_id) or not db.get(LabUnit, lab_unit_id):
                        flash(f"Invalid disease or lab unit for item {item}.", "danger")
                        return redirect(url_for("admin.edit_eligibility", user_id=user_id))
                    
                    # Check if record exists
                    if key in existing_map:
                        # Update existing record
                        row = existing_map[key]
                        row.can_grade_resident = can_grade_resident
                        row.can_grade_faculty = can_grade_faculty
                        row.can_arbitrate = can_arbitrate
                        row.active = active
                        updated.append(row.id)
                    else:
                        # Create new record only if at least one permission is set
                        if can_grade_resident or can_grade_faculty or can_arbitrate:
                            row = UserDiseaseUnitRole(
                                user_id=user_id,
                                disease_id=disease_id,
                                lab_unit_id=lab_unit_id,
                                can_grade_resident=can_grade_resident,
                                can_grade_faculty=can_grade_faculty,
                                can_arbitrate=can_arbitrate,
                                active=active,
                            )
                            db.add(row)
                            db.flush()
                            created.append(row.id)
                
                # Delete records that were not submitted (if they exist and are active)
                for key, row in existing_map.items():
                    if key not in submitted_keys and row.active:
                        # Instead of deleting, mark as inactive
                        row.active = False
                        updated.append(row.id)
                        deleted.append(row.id)
                
                db.commit()
                flash(f"Grading eligibility updated successfully. {len(created)} created, {len(updated)} updated, {len(deleted)} deactivated.", "success")
                return redirect(url_for("admin.edit_eligibility", user_id=user_id))
                
            except json.JSONDecodeError as e:
                flash(f"Invalid JSON data: {str(e)}", "danger")
                return redirect(url_for("admin.edit_eligibility", user_id=user_id))
            except Exception as e:
                db.rollback()
                flash(f"Error updating eligibility: {str(e)}", "danger")
                return redirect(url_for("admin.edit_eligibility", user_id=user_id))
        
        # Handle GET request (display the form)
        diseases = db.execute(select(Disease).order_by(Disease.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).order_by(LabUnit.hospital_id.asc())).scalars().all()

    return render_template(
        "admin/edit_grading_eligibility.html",
        user=user,
        diseases=diseases,
        lab_units=lab_units
    )
