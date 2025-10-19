from __future__ import annotations

from typing import Tuple


def check_suitability(image: dict, disease_id: int) -> Tuple[bool, str | None]:
    """Basic suitability rules by disease.

    This is a placeholder; replace with stricter logic as needed.
    Expects `image` to be a dict from search_images_strict, containing keys like
    `area`, `image_type`, or other metadata.
    """
    # Map simple assumptions by disease name/id; project may have mapping elsewhere
    # For now, allow all and return True. Extend as required.
    return True, None

