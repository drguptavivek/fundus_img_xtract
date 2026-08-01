"""Typed IITK integration errors."""


class IITKIntegrationError(RuntimeError):
    """Safe base error for configuration, remote, and contract failures."""


class IITKConfigError(IITKIntegrationError):
    """Invalid local configuration."""


class IITKRemoteError(IITKIntegrationError):
    """Non-successful upstream response."""

    def __init__(self, status_code: int, code: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(f"IITK API returned HTTP {status_code}{f' ({code})' if code else ''}.")


class IITKContractError(IITKIntegrationError):
    """Upstream response did not match the required shape."""
