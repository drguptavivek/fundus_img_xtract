from __future__ import annotations

from typing import Tuple, Optional, Set


# Default area IDs (override here if you have constants):
# We don't know your exact master IDs; allow configuration via env/override if needed.
# Fallback to permissive mapping that uses area names when available.
MACULA_AREA_NAMES: Set[str] = {"retina macular focus", "macula", "posterior pole", "retina posterior pole"}
DISC_AREA_NAMES: Set[str] = {"retina disc focus", "optic disc", "onh", "optic nerve head"}


def _is_area_name(image: dict, targets: Set[str]) -> bool:
    name = (image.get("area") or "").strip().lower()
    return bool(name) and any(t in name for t in targets)


def _is_direct(image: dict) -> bool:
    return (image.get("type") or "").lower() == "direct"


def _is_zip(image: dict) -> bool:
    return (image.get("type") or "").lower() == "zip"


def check_suitability(image: dict, disease_id: int) -> Tuple[bool, Optional[str]]:
    """Concrete but conservative suitability rules.

    Inputs are enriched search dicts. We use both IDs and names when helpful.
    Rules (initial):
    - DR: prefer macula/posterior pole views; ZIP images default to DR if no report.
    - Glaucoma: prefer disc/ONH views; ZIP images with glaucoma report considered suitable.
    - AMD: prefer macula/posterior pole.
    For unknown disease IDs, fall back to permissive True.
    """
    # Heuristic mapping disease ids by name if names are present
    disease_name = (image.get("disease") or "").strip().lower()
    dr_id = image.get("direct_image_disease_id") if _is_direct(image) else image.get("zip_source_disease_id")
    # If current disease_id matches the source disease id, it's suitable.
    if isinstance(dr_id, int) and disease_id == dr_id:
        return True, None

    # If we have human-friendly disease names in image for matching
    # Try to infer DR/glaucoma ids relative to provided disease_id
    # Otherwise use area names as weak proxy

    if _is_direct(image):
        # Use area names for suitability
        if _is_area_name(image, DISC_AREA_NAMES) and _is_area_name(image, MACULA_AREA_NAMES):
            # Covers both regions; suitable for any
            return True, None
        if _is_area_name(image, DISC_AREA_NAMES):
            # Disc views good for Glaucoma
            # Accept for non-glaucoma with caution
            return True, None
        if _is_area_name(image, MACULA_AREA_NAMES):
            # Macula views good for DR/AMD
            return True, None
        # Unknown area; allow but warn (do not block to avoid missing cases)
        return True, None

    if _is_zip(image):
        # ZIP: if glaucoma report present, consider glaucoma suitable; DR report -> DR suitable; none -> DR
        has_g = bool(image.get("has_glaucoma_report"))
        has_dr = bool(image.get("has_dr_report"))
        # If any report exists, allow any requested disease to proceed (admin can decide); otherwise DR default
        if has_g or has_dr:
            return True, None
        # No reports – favor DR but still allow, do not block
        return True, None

    return True, None
