"""Typed failures for device enrolment and device-gated login."""
from __future__ import annotations


class MobileDeviceError(ValueError):
    def __init__(self, message: str, *, code: str = "device_error", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class DeviceNotEnrolled(MobileDeviceError):
    def __init__(self, message: str = "This device is not enrolled.") -> None:
        super().__init__(message, code="device_not_enrolled", status_code=403)


class DevicePendingApproval(MobileDeviceError):
    def __init__(self, message: str = "This device is awaiting administrator approval.") -> None:
        super().__init__(message, code="device_pending_approval", status_code=403)


class DeviceBlocked(MobileDeviceError):
    def __init__(self, message: str = "This device has been blocked.") -> None:
        super().__init__(message, code="device_blocked", status_code=403)


class EnrolmentCodeInvalid(MobileDeviceError):
    def __init__(self, message: str = "Enrolment code is invalid, expired, or already used.") -> None:
        super().__init__(message, code="enrolment_code_invalid", status_code=400)
