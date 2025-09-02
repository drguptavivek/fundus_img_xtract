# /direct_uploads/process_image.py

import traceback
from pathlib import Path
from flask import render_template, redirect, url_for, flash, current_app, url_for as flask_url_for, jsonify
from flask_login import current_user
from werkzeug.exceptions import NotFound
from preprocess import bp
from auth.roles import roles_required
from models import DirectImageUpload, Hospital, LabUnit, Camera, Disease, Area, User
from direct_uploads.paths import abs_from_parts
from direct_uploads.utils import with_session, require_owner_or_roles


@bp.route("/dashboard", methods=["GET"])
@roles_required('contributor', 'data_manager', 'admin')
def anonymization_dashboard():
    """
    Shows Total Anonmized Images
    Shows Recent Anonmized Images my all users (admin, data_maanger), or self
    
    Allows starting Anonmization process by automactially selecting an image.
    Has a section to select filters of Hospital, Lab_unit, Image_type, Disease, Area
    Prefer New to old.
    Users who are Admin, data_managers can verify  any image
    Non-admins can only verify images of their asscociated lab_units only
    """
    # TODO
    return render_template("preprocess/anonymization_dashboard.html")   
     


@bp.route("/anonymize_image/<str:uuid>", methods=["GET", "POST"])
@roles_required('contributor', 'data_manager', 'admin')
def anonymize_image(upload_id: int):
    # TODO
    """
    Gets an image from the class DirectImageUpload(Base). 
    
    Image is served based on UUID. No other data about the image to be shown.
    The user edits the image and ensures any IDs  etc are deleted from the image.
    Ability to restore orginal image 
    Uses a toggle to mark Verify / Unverify. 
    Can give optional remarks
    Saves results in DirectImageVerify table. image UUID, Verified status, remarks, verified_by, verified_at, 
    Redirect to next image after 3 seconds
    """
    return render_template("preprocess/anonymize_image.html")   
