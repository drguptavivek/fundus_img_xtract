from flask import render_template, request, flash, redirect, url_for
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
        
        diseases = db.execute(select(Disease).order_by(Disease.name.asc())).scalars().all()
        lab_units = db.execute(select(LabUnit).order_by(LabUnit.name.asc())).scalars().all()

    return render_template(
        "admin/edit_grading_eligibility.html",
        user=user,
        diseases=diseases,
        lab_units=lab_units
    )
