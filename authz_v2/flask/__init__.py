"""Flask endpoint classification and default-deny integration."""

from .contracts import EndpointMode, EndpointPolicy
from .decorators import authorization_endpoint
from .hooks import install_default_deny, unclassified_endpoints

__all__ = [
    "EndpointMode",
    "EndpointPolicy",
    "authorization_endpoint",
    "install_default_deny",
    "unclassified_endpoints",
]
