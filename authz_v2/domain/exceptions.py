from enum import StrEnum


class DenialCode(StrEnum):
    NOT_AUTHORIZED = "not_authorized"
    UNKNOWN_ACTION = "unknown_action"
    UNKNOWN_RESOURCE = "unknown_resource"
    UNRESOLVED_RESOURCE = "unresolved_resource"
    INACTIVE_PRINCIPAL = "inactive_principal"
    MISSING_SCOPE = "missing_scope"
    INVALID_SCOPE = "invalid_scope"
    INVALID_FACTS = "invalid_facts"
    UNSUPPORTED_QUERY = "unsupported_query"
    EXPIRED_CREDENTIAL = "expired_credential"
    DOMAIN_CONSTRAINT = "domain_constraint"


class AuthorizationError(PermissionError):
    def __init__(
        self, code: DenialCode = DenialCode.NOT_AUTHORIZED, message: str | None = None
    ):
        self.code = code
        super().__init__(message or code.value)


class AuthorizationDataError(RuntimeError):
    """Stored authorization state cannot be interpreted safely."""
