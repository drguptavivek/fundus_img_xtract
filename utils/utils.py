from contextlib import contextmanager
from flask_login import current_user
from db_transaction_manager import get_db_session

def with_session():
    """Alias for get_db_session to maintain backward compatibility.
    
    Note: This function is deprecated. Use get_db_session() or transaction_scope()
    from db_transaction_manager instead.
    """
    return get_db_session()

def require_owner_or_roles(upload, *roles):
    if current_user.has_role(*roles):
        return True
    return upload and upload.uploader_id == current_user.id
