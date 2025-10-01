# auth/roles.py
from __future__ import annotations
from functools import wraps
from typing import Iterable, Dict, Any
from flask import abort, redirect, url_for, g
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Role

DEFAULT_ROLES = ["admin", "fileUploader", "ophthalmologist", "data_manager", "resident", "optometrist"]

# Role constants for use in decorators (these can be referenced in code)
ROLE_ADMIN = "admin"
ROLE_FILE_UPLOADER = "fileUploader"
ROLE_OPHTHALMOLOGIST = "ophthalmologist"
ROLE_DATA_MANAGER = "data_manager"
ROLE_RESIDENT = "resident"
ROLE_OPTOMETRIST = "optometrist"

def ensure_roles(db: Session, names: Iterable[str] = DEFAULT_ROLES) -> None:
    existing = {r.name for r in db.scalars(select(Role)).all()}
    to_add = [Role(name=n) for n in names if n not in existing]
    if to_add:
        db.add_all(to_add)
        db.commit()

def roles_required(*required: str, require_all: bool = False):
    """
    Use on routes:
      @roles_required("admin")
      @roles_required("ophthalmologist", "data_manager")      # any of
      @roles_required("ophthalmologist", "data_manager", require_all=True)  # all of
      
    Can also use role constants:
      @roles_required(ROLE_ADMIN)
      @roles_required(ROLE_OPHTHALMOLOGIST, ROLE_DATA_MANAGER)
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            ok = (current_user.has_all_roles(*required) if require_all
                  else current_user.has_role(*required))
            if not ok:
                return abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

# Aliases
def roles_any(*names: str):
    return roles_required(*names, require_all=False)

def roles_all(*names: str):
    return roles_required(*names, require_all=True)

# Dynamic role checking functions that can be used in templates or code
def get_all_roles() -> list[str]:
    """Get all roles from the database."""
    try:
        from models import Session
        with Session() as db:
            roles = db.execute(select(Role)).scalars().all()
            return [role.name for role in roles]
    except Exception:
        # Fallback to DEFAULT_ROLES if database is not available
        return DEFAULT_ROLES[:]

def role_exists(role_name: str) -> bool:
    """Check if a role exists in the database."""
    try:
        from models import Session
        with Session() as db:
            role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
            return role is not None
    except Exception:
        return False
