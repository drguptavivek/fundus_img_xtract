"""
PII Masking Utility

This module provides centralized functions for masking Personally Identifiable
Information (PII) across the Fundus Image Manager application.

Reference: docs/PII_Exposure_Control_Policy.md Section 4.1
Bead: 5O (fundus_img_xtract-r4o)

Usage:
    from utils.pii_masking import mask_patient_id, mask_patient_name, mask_phone, mask_email
    
    # In API responses or templates
    patient_display_id = mask_patient_id(patient.patient_id)
    patient_display_name = mask_patient_name()  # Always returns "Anonymous"
"""

from typing import Optional


def mask_patient_id(patient_id: Optional[str], show_last: int = 3) -> str:
    """
    Mask patient ID showing only the last N characters.
    
    Args:
        patient_id: The patient identifier to mask
        show_last: Number of characters to show at the end (default: 3)
    
    Returns:
        Masked patient ID in format "P****XXX" where XXX is last 3 chars
    
    Examples:
        >>> mask_patient_id("12345678")
        'P****678'
        >>> mask_patient_id("AB")
        'P***'
        >>> mask_patient_id(None)
        'P***'
    """
    if not patient_id:
        return "P***"
    
    patient_id = str(patient_id).strip()
    
    if len(patient_id) <= show_last:
        return "P***"
    
    return f"P****{patient_id[-show_last:]}"


def mask_patient_name(patient_name: Optional[str] = None) -> str:
    """
    Always return "Anonymous" for patient names.
    
    This function always returns "Anonymous" regardless of input,
    as patient names should never be displayed in cross-hospital
    grading workflows.
    
    Args:
        patient_name: Unused, kept for API compatibility
    
    Returns:
        Always returns "Anonymous"
    
    Examples:
        >>> mask_patient_name("John Doe")
        'Anonymous'
        >>> mask_patient_name(None)
        'Anonymous'
    """
    return "Anonymous"


def mask_phone(phone: Optional[str], show_last: int = 4) -> str:
    """
    Mask phone number showing only the last N digits.
    
    Args:
        phone: The phone number to mask
        show_last: Number of digits to show at the end (default: 4)
    
    Returns:
        Masked phone in format "***-***-XXXX" where XXXX is last 4 digits
    
    Examples:
        >>> mask_phone("1234567890")
        '***-***-7890'
        >>> mask_phone("+1-555-123-4567")
        '***-***-4567'
        >>> mask_phone("123")
        '***-****'
    """
    if not phone:
        return "***-****"
    
    # Extract only digits
    digits = ''.join(c for c in str(phone) if c.isdigit())
    
    if len(digits) < show_last + 1:
        return "***-****"
    
    return f"***-***-{digits[-show_last:]}"


def mask_email(email: Optional[str]) -> str:
    """
    Mask email showing only the domain.
    
    Args:
        email: The email address to mask
    
    Returns:
        Masked email in format "***@domain.com"
    
    Examples:
        >>> mask_email("john.doe@hospital.org")
        '***@hospital.org'
        >>> mask_email("admin@example.com")
        '***@example.com'
        >>> mask_email("invalid")
        '***@***.com'
    """
    if not email or "@" not in str(email):
        return "***@***.com"
    
    email = str(email).strip()
    parts = email.split("@")
    
    if len(parts) != 2 or not parts[1]:
        return "***@***.com"
    
    return f"***@{parts[1]}"


def mask_username(username: Optional[str], show_first: int = 2) -> str:
    """
    Partially mask username showing only first N characters.
    
    Args:
        username: The username to mask
        show_first: Number of characters to show at the start (default: 2)
    
    Returns:
        Masked username in format "XX***"
    
    Examples:
        >>> mask_username("johndoe")
        'jo***'
        >>> mask_username("ab")
        'ab***'
        >>> mask_username("a")
        'a***'
    """
    if not username:
        return "***"
    
    username = str(username).strip()
    
    if len(username) <= show_first:
        return f"{username}***"
    
    return f"{username[:show_first]}***"


def should_mask_pii(
    current_user_hospital_id: Optional[int],
    data_hospital_id: Optional[int],
    current_user_role: Optional[str] = None,
    always_mask_roles: Optional[list] = None
) -> bool:
    """
    Determine if PII should be masked based on hospital context.
    
    PII should be masked when:
    1. User is accessing data from a different hospital
    2. User has a role that always requires masking
    3. Data hospital_id is None (system-level data)
    
    Args:
        current_user_hospital_id: The hospital ID of the current user
        data_hospital_id: The hospital ID associated with the data
        current_user_role: Optional role of the current user
        always_mask_roles: List of roles that always see masked PII
    
    Returns:
        True if PII should be masked, False otherwise
    
    Examples:
        >>> should_mask_pii(1, 2)  # Different hospitals
        True
        >>> should_mask_pii(1, 1)  # Same hospital
        False
        >>> should_mask_pii(1, 1, 'resident', ['resident', 'resident2'])
        True
    """
    if always_mask_roles is None:
        always_mask_roles = ['resident', 'resident2', 'ophthalmologist', 'analytics_viewer']
    
    # Always mask for roles in the always_mask list
    if current_user_role and current_user_role in always_mask_roles:
        return True
    
    # No hospital context - mask by default
    if current_user_hospital_id is None or data_hospital_id is None:
        return True
    
    # Different hospitals - mask
    if current_user_hospital_id != data_hospital_id:
        return True
    
    return False


def mask_dict_pii(
    data: dict,
    fields_to_mask: Optional[dict] = None,
    mask_all_patient: bool = True
) -> dict:
    """
    Mask PII fields in a dictionary.
    
    Args:
        data: Dictionary containing data with potential PII
        fields_to_mask: Optional custom mapping of field names to mask functions
        mask_all_patient: If True, mask all standard patient PII fields
    
    Returns:
        New dictionary with PII fields masked
    
    Examples:
        >>> data = {'patient_name': 'John', 'patient_id': '12345', 'uuid': 'abc'}
        >>> mask_dict_pii(data)
        {'patient_name': 'Anonymous', 'patient_id': 'P****345', 'uuid': 'abc'}
    """
    if not data:
        return data
    
    result = data.copy()
    
    # Default field mappings
    default_mappings = {
        'patient_name': mask_patient_name,
        'patient_id': mask_patient_id,
        'phone': mask_phone,
        'email': mask_email,
        'mrn': mask_patient_id,
        'medical_record_number': mask_patient_id,
    }
    
    # Use custom mappings if provided, otherwise use defaults
    mappings = fields_to_mask if fields_to_mask else default_mappings
    
    for field, mask_func in mappings.items():
        if field in result:
            result[field] = mask_func(result[field])
    
    return result


def strip_pii_from_dict(data: dict, pii_fields: Optional[list] = None) -> dict:
    """
    Remove PII fields entirely from a dictionary.
    
    Args:
        data: Dictionary containing data with potential PII
        pii_fields: List of field names to remove
    
    Returns:
        New dictionary with PII fields removed
    
    Examples:
        >>> data = {'patient_name': 'John', 'uuid': 'abc-123'}
        >>> strip_pii_from_dict(data)
        {'uuid': 'abc-123'}
    """
    if not data:
        return data
    
    if pii_fields is None:
        pii_fields = [
            'patient_name', 'patient_id', 'mrn', 'medical_record_number',
            'phone', 'email', 'address', 'date_of_birth', 'dob',
            'full_name', 'first_name', 'last_name'
        ]
    
    return {k: v for k, v in data.items() if k not in pii_fields}
