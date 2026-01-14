# auth/roles.py
from __future__ import annotations
from functools import wraps
from typing import Iterable, Dict, Any
from flask import abort, redirect, url_for, g
from flask_login import current_user, login_required
from sqlalchemy import select

from models import Role
from db_transaction_manager import get_db_session, transaction_scope

ROLE_ADMIN = "admin"
ROLE_LOCAL_ADMIN = "local_admin"  # Site Admin
ROLE_OPHTHALMOLOGIST = "ophthalmologist"
ROLE_RESIDENT = "resident"
ROLE_OPTOMETRIST = "optometrist"
ROLE_DATA_MANAGER = "data_manager"
ROLE_PREGARDED_UPLOADER = "pregarded_uploader"
ROLE_DATASET_CREATOR = "dataset_creator"
ROLE_ANALYTICS_VIEWER = "analytics_viewer"

DEFAULT_ROLES = [
    "admin",
    "local_admin",
    "fileUploader",
    "ophthalmologist",
    "data_manager",
    "resident",
    "optometrist",
    "discrepancy_reviewer",
    "data_exporter",
    "pregarded_uploader",
    ROLE_DATASET_CREATOR,
    ROLE_ANALYTICS_VIEWER,
]

def ensure_roles(db, names: Iterable[str] = DEFAULT_ROLES) -> None:
    """Ensure all specified roles exist in the database.
    
    Args:
        db: Database session (provided by context manager)
        names: Iterable of role names to ensure exist
    """
    existing = {r.name for r in db.scalars(select(Role)).all()}
    to_add = [Role(name=n) for n in names if n not in existing]
    if to_add:
        db.add_all(to_add)
        # Note: Commit is handled by the context manager

def roles_required(*required: str, require_all: bool = False):
    """
    Use on routes:
      @roles_required("admin")
      @roles_required("ophthalmologist", "data_manager")      # any of
      @roles_required("ophthalmologist", "data_manager", require_all=True)  # all of

    Can also use role constants:
      @roles_required(ROLE_ADMIN)
      @roles_required(ROLE_OPHTHALMOLOGIST, ROLE_DATA_MANAGER)

    Note: Master admins (is_master_admin=True) bypass all role checks.
    """
    def decorator(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            # Master admins bypass all role checks
            if current_user.is_master_admin:
                return fn(*args, **kwargs)
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
        with get_db_session() as db:
            roles = db.execute(select(Role)).scalars().all()
            return [role.name for role in roles]
    except Exception:
        # Fallback to DEFAULT_ROLES if database is not available
        return DEFAULT_ROLES[:]

def role_exists(role_name: str) -> bool:
    """Check if a role exists in the database."""
    try:
        with get_db_session() as db:
            role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
            return role is not None
    except Exception:
        return False
