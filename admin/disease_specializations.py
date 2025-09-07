from flask import render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy.orm import selectinload
from disease_specialzation_utils import get_all_diseases, get_all_ophthalmologists, get_user_disease_specializations, set_user_disease_specializations
from models import Session, User, Disease
from auth.roles import roles_required


@roles_required("admin")
def index():
    """Show list of all ophthalmologists and their disease specializations."""
    ophthalmologists = get_all_ophthalmologists()
    diseases = get_all_diseases()
    
    # Get specializations for each ophthalmologist
    ophth_specializations = {}
    for ophth in ophthalmologists:
        ophth_specializations[ophth.id] = get_user_disease_specializations(ophth.id)
    
    return render_template(
        "admin/disease_specializations/index.html",
        ophthalmologists=ophthalmologists,
        diseases=diseases,
        ophth_specializations=ophth_specializations
    )


@roles_required("admin")
def manage_specializations(user_id):
    """Manage disease specializations for a specific ophthalmologist."""
    with Session() as db:
        # Get the user
        user = db.query(User).options(selectinload(User.disease_specializations)).filter(User.id == user_id).first()
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.index"))
        
        # Check if user is an ophthalmologist
        if not user.has_role("ophthalmologist"):
            flash("User is not an ophthalmologist.", "danger")
            return redirect(url_for("admin.index"))
        
        if request.method == "POST":
            # Get selected disease IDs from form
            disease_ids = [int(did) for did in request.form.getlist("diseases")]
            
            # Set the specializations
            if set_user_disease_specializations(user_id, disease_ids):
                flash(f"Updated disease specializations for {user.username}.", "success")
            else:
                flash("Failed to update disease specializations.", "danger")
            
            return redirect(url_for("admin.index"))
        
        # GET request - show the form
        diseases = get_all_diseases()
        user_specializations = get_user_disease_specializations(user_id)
        user_specialization_ids = [d.id for d in user_specializations]
        
        return render_template(
            "admin/disease_specializations/manage.html",
            user=user,
            diseases=diseases,
            user_specialization_ids=user_specialization_ids
        )


@roles_required("admin")
def api_get_user_diseases(user_id):
    """API endpoint to get user's disease specializations."""
    try:
        specializations = get_user_disease_specializations(user_id)
        return jsonify({
            "success": True,
            "diseases": [{"id": d.id, "name": d.name} for d in specializations]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@roles_required("admin")
def api_set_user_diseases(user_id):
    """API endpoint to set user's disease specializations."""
    try:
        disease_ids = request.json.get("disease_ids", [])
        # Validate that all IDs are integers
        disease_ids = [int(did) for did in disease_ids]
        
        if set_user_disease_specializations(user_id, disease_ids):
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update specializations"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500