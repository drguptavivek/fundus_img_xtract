"""Small, fail-closed boundaries for classical user administration."""

from models import User


PROTECTED_ROLE_NAMES = {"admin", "user_manager", "local_admin", "pii_exporter"}
PROTECTED_TARGET_ROLE_NAMES = {"admin", "user_manager", "local_admin"}


def can_manage_user(*, actor: User, target_user: User) -> bool:
    """Allow Admin, or a User Manager over an ordinary user in its hospital."""
    if actor.has_role("admin"):
        return True
    if not actor.has_role("user_manager"):
        return False
    if not actor.id or actor.id == target_user.id:
        return False
    if not actor.hospital_id or target_user.hospital_id != actor.hospital_id:
        return False
    target_roles = {role.name for role in (target_user.roles or [])}
    return not bool(target_roles & PROTECTED_TARGET_ROLE_NAMES)
