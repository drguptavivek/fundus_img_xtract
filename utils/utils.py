from contextlib import contextmanager
from pathlib import Path
from flask import current_app, flash, redirect, url_for
from flask_login import current_user
from werkzeug.exceptions import NotFound
from models import Session, DIRECT_UPLOAD_DIR

@contextmanager
def with_session():
    db = Session()
    try:
        yield db
        db.close()
    except Exception:
        db.rollback()
        db.close()
        raise

def require_owner_or_roles(upload, *roles):
    if current_user.has_role(*roles):
        return True
    return upload and upload.uploader_id == current_user.id
