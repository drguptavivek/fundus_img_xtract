"""
Filename utilities for safe export generation.

This module provides functions to ensure that exported files have sanitized names
that do not contain PII or unsafe characters, adhering to the project's PII policy.

Reference: docs/PII_Exposure_Control_Policy.md Section 2.3
"""

import re
from datetime import datetime
import uuid
from typing import Optional
from werkzeug.utils import secure_filename

def _generate_timestamp() -> str:
    """Generate a sortable timestamp string (YYYYMMDD_HHMMSS)."""
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

def _generate_short_uuid() -> str:
    """Generate a short (8-char) UUID suffix."""
    return str(uuid.uuid4())[:8]

def sanitize_export_filename(base_name: str, extension: str, include_timestamp: bool = True) -> str:
    """
    Generate a sanitized, safe filename for exports.
    
    Args:
        base_name (str): The descriptive part of the filename (e.g., "users_table").
                         This will be sanitized to remove special characters.
        extension (str): The file extension (e.g., "xlsx", "csv"). 
                         Should not include the leading dot.
        include_timestamp (bool): Whether to append a timestamp and UUID. Default True.
        
    Returns:
        str: A safe filename, e.g., "users_table_20240101_120000_a1b2c3d4.xlsx"
    """
    # 1. Sanitize the base name using secure_filename (removes path traversal, special chars)
    safe_base = secure_filename(base_name)
    
    # 2. If secure_filename returns empty (e.g. input was "///"), use a default
    if not safe_base:
        safe_base = "export"
        
    # 3. Further strict sanitization: allow only alphanumeric, underscores, and hyphens
    #    This prevents any obscure PII leakage through creative naming if base_name was user-input.
    safe_base = re.sub(r'[^a-zA-Z0-9_\-]', '_', safe_base)
    
    # 4. Collapse multiple underscores
    safe_base = re.sub(r'_+', '_', safe_base).strip('_')

    # 5. Sanitize extension
    safe_ext = secure_filename(extension).strip('.')
    if not safe_ext:
        safe_ext = "dat" # Default fallback
        
    if include_timestamp:
        timestamp = _generate_timestamp()
        uid = _generate_short_uuid()
        return f"{safe_base}_{timestamp}_{uid}.{safe_ext}"
    else:
        return f"{safe_base}.{safe_ext}"
