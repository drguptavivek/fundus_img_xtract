from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_, distinct, func
import random
import json

from auth.roles import roles_required
from models import Session, PatientEncounters, EncounterFile, ImageGrading, DirectImageUpload, Disease, DirectImageVerify, GradingTask, User
from utils.dualGradingUtils import get_all_pending_resident, get_all_pending_faculty, get_all_pending_arbitration
from utils.userGradingsDone import get_user_gradings_with_details


@roles_required("admin", "resident", "ophthalmologist")
def index():
    # TODO

    return render_template(
        "grading/index.html"
    )