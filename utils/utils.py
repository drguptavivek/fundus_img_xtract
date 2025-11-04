from contextlib import contextmanager
from flask_login import current_user
from models import Session

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
