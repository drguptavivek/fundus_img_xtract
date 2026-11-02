"""Transaction boundary for deliberate authentication rejection side effects."""
from contextlib import contextmanager

from db_transaction_manager import transaction_scope


@contextmanager
def authentication_transaction():
    from .auth_sessions import MobileAuthError

    rejection = None
    with transaction_scope() as db:
        try:
            yield db
        except MobileAuthError as exc:
            if exc.code not in {"invalid_credentials", "user_locked", "ip_locked"}:
                raise
            rejection = exc
    # Lockouts and failure audit records must commit before returning a denial.
    if rejection is not None:
        raise rejection
