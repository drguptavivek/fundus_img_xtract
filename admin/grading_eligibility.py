from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user
from sqlalchemy import select
from models import User, Disease, LabUnit, UserDiseaseUnitRole
from db_transaction_manager import transaction_scope, get_db_session
from auth.roles import roles_required
from utils.linkedGradingUtils import get_primary_disease_id


def _validate_linked_primary_eligibility(db, items: list[dict]) -> list[str]:
    """
    Reject linked-disease eligibility when the primary disease is missing the
    corresponding slot in the same lab unit.
    """
    normalized_items: dict[tuple[int, int], dict] = {}
    for item in items:
        disease_id = int(item.get("disease_id"))
        lab_unit_id = int(item.get("lab_unit_id"))
        normalized_items[(disease_id, lab_unit_id)] = {
            "can_grade_resident": bool(item.get("can_grade_resident", False)),
            "can_grade_resident2": bool(item.get("can_grade_resident2", False)),
            "can_arbitrate": bool(item.get("can_arbitrate", False)),
            "active": bool(item.get("active", False)),
        }

    disease_names = {
        disease.id: disease.name
        for disease in db.execute(select(Disease)).scalars().all()
    }
    lab_unit_names = {
        lab_unit.id: lab_unit.name
        for lab_unit in db.execute(select(LabUnit)).scalars().all()
    }

    errors: list[str] = []
    for (disease_id, lab_unit_id), item in normalized_items.items():
        primary_disease_id = get_primary_disease_id(db, disease_id)
        if primary_disease_id == disease_id:
            continue

        primary_item = normalized_items.get((primary_disease_id, lab_unit_id))
        primary_disease_name = disease_names.get(primary_disease_id, f"Disease {primary_disease_id}")
        linked_disease_name = disease_names.get(disease_id, f"Disease {disease_id}")
        lab_unit_name = lab_unit_names.get(lab_unit_id, f"Lab Unit {lab_unit_id}")

        needs_resident = item["active"] and (item["can_grade_resident"] or item["can_grade_resident2"])
        needs_arbitrator = item["active"] and item["can_arbitrate"]

        if needs_resident and not (
            primary_item
            and primary_item["active"]
            and (primary_item["can_grade_resident"] or primary_item["can_grade_resident2"])
        ):
            errors.append(
                f"{lab_unit_name}: {linked_disease_name} resident grading requires active {primary_disease_name} resident eligibility."
            )

        if needs_arbitrator and not (
            primary_item
            and primary_item["active"]
            and primary_item["can_arbitrate"]
        ):
            errors.append(
                f"{lab_unit_name}: {linked_disease_name} arbitrator grading requires active {primary_disease_name} arbitrator eligibility."
            )

    return errors


@roles_required('admin', 'local_admin')
def manage_eligibility_users():
    """List all users to manage their grading eligibility."""
    with get_db_session() as db:
        query = select(User).order_by(User.username.asc())

        # Local admins can only manage users in their hospital
        if current_user.has_role("local_admin") and not current_user.has_role("admin") and not getattr(current_user, "is_master_admin", False):
            if not getattr(current_user, "hospital_id", None):
                users = []
            else:
                query = query.where(User.hospital_id == current_user.hospital_id)
                users = db.execute(query).scalars().all()
        else:
            users = db.execute(query).scalars().all()
        
        return render_template("admin/grading_eligibility_users.html", users=users)

@roles_required('admin', 'local_admin')
def edit_eligibility(user_id):
    """Display and manage grading eligibility for a single user."""
    # Handle GET request (display the form)
    with get_db_session() as db:
        user = db.get(User, user_id)
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.manage_eligibility_users"))

        # Local admins can only manage users in their hospital
        if current_user.has_role("local_admin") and not current_user.has_role("admin") and not getattr(current_user, "is_master_admin", False):
            if not getattr(current_user, "hospital_id", None) or user.hospital_id != current_user.hospital_id:
                flash("You do not have permission to manage grading eligibility for this user.", "danger")
                return redirect(url_for("admin.manage_eligibility_users"))
        
        if request.method == 'GET':
            diseases = db.execute(select(Disease).order_by(Disease.name.asc())).scalars().all()
            if current_user.has_role("local_admin") and not current_user.has_role("admin") and not getattr(current_user, "is_master_admin", False):
                lab_units = db.execute(
                    select(LabUnit)
                    .where(LabUnit.hospital_id == current_user.hospital_id)
                    .order_by(LabUnit.hospital_id.asc())
                ).scalars().all()
            else:
                lab_units = db.execute(select(LabUnit).order_by(LabUnit.hospital_id.asc())).scalars().all()
            
            if request.headers.get("HX-Request") or request.args.get("format") == "partial":
                return render_template(
                    "admin/partials/user_grading_edit.html",
                    user=user,
                    diseases=diseases,
                    lab_units=lab_units,
                )

            # Render template within the same session to avoid detached instance errors
            return render_template(
                "admin/edit_grading_eligibility.html",
                user=user,
                diseases=diseases,
                lab_units=lab_units
            )
    
    # Handle form submission (POST)
    if request.method == 'POST':
        with transaction_scope() as db:
            try:
                user = db.get(User, user_id)
                if not user:
                    flash("User not found.", "danger")
                    return redirect(url_for("admin.manage_eligibility_users"))

                # Local admins can only manage users in their hospital
                if current_user.has_role("local_admin") and not current_user.has_role("admin") and not getattr(current_user, "is_master_admin", False):
                    if not getattr(current_user, "hospital_id", None) or user.hospital_id != current_user.hospital_id:
                        flash("You do not have permission to manage grading eligibility for this user.", "danger")
                        return redirect(url_for("admin.manage_eligibility_users"))

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

                validation_errors = _validate_linked_primary_eligibility(db, items)
                if validation_errors:
                    for error in validation_errors:
                        flash(error, "danger")
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
                    can_grade_resident2 = bool(item.get('can_grade_resident2', False))
                    can_arbitrate = bool(item.get('can_arbitrate', False))
                    active = bool(item.get('active', False))

                    # Mirror resident eligibility to resident2 to keep slots in sync.
                    if can_grade_resident:
                        can_grade_resident2 = True
                    
                    # Create key for tracking
                    key = (disease_id, lab_unit_id)
                    submitted_keys.add(key)
                    
                    
                    # Validate FKs
                    lab_unit = db.get(LabUnit, lab_unit_id)
                    if not db.get(Disease, disease_id) or not lab_unit:
                        flash(f"Invalid disease or lab unit for item {item}.", "danger")
                        return redirect(url_for("admin.edit_eligibility", user_id=user_id))

                    # Local admins can only assign lab units in their hospital
                    if current_user.has_role("local_admin") and not current_user.has_role("admin") and not getattr(current_user, "is_master_admin", False):
                        if not getattr(current_user, "hospital_id", None) or lab_unit.hospital_id != current_user.hospital_id:
                            flash("You can only assign grading eligibility within your hospital.", "danger")
                            return redirect(url_for("admin.edit_eligibility", user_id=user_id))
                    
                    # Check if record exists
                    if key in existing_map:
                        # Update existing record
                        row = existing_map[key]
                        row.can_grade_resident = can_grade_resident
                        row.can_grade_resident2 = can_grade_resident2
                        row.can_arbitrate = can_arbitrate
                        row.active = active
                        updated.append(row.id)
                    else:
                        # Create new record only if at least one permission is set
                        if can_grade_resident or can_grade_resident2 or can_arbitrate:
                            row = UserDiseaseUnitRole(
                                user_id=user_id,
                                disease_id=disease_id,
                                lab_unit_id=lab_unit_id,
                                can_grade_resident=can_grade_resident,
                                can_grade_resident2=can_grade_resident2,
                                can_arbitrate=can_arbitrate,
                                active=active,
                            )
                            db.add(row)
                            db.flush()
                            created.append(row.id)
                
                # Handle records that were not submitted - delete them
                for key, row in existing_map.items():
                    if key not in submitted_keys:
                        # Delete the record entirely when all roles are removed
                        db.delete(row)
                        deleted.append(row.id)
                
                flash(f"Grading eligibility updated successfully. {len(created)} created, {len(updated)} updated, {len(deleted)} deleted.", "success")
                if request.headers.get("HX-Request") or request.args.get("format") == "partial":
                    return redirect(url_for("admin.user_detail", user_id=user_id, format="shell"))
                return redirect(url_for("admin.edit_eligibility", user_id=user_id))
                
            except json.JSONDecodeError as e:
                flash(f"Invalid JSON data: {str(e)}", "danger")
                return redirect(url_for("admin.edit_eligibility", user_id=user_id))
            # Exception handling is now automatic with transaction_scope
