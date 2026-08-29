from __future__ import annotations

from dataclasses import dataclass

from .errors import invalid


def _positive(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise invalid(f"{name} must be a positive integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise invalid(f"{name} must be a positive integer.") from exc
    if parsed <= 0:
        raise invalid(f"{name} must be a positive integer.")
    return parsed


@dataclass(frozen=True)
class PregradedImageSelection:
    project_id: int
    hospital_id: int
    lab_unit_id: int
    disease_id: int
    camera_id: int
    area_id: int
    is_mydriatic: bool
    profile_id: int | None = None

    @classmethod
    def from_values(
        cls,
        *,
        project_id: object,
        hospital_id: object,
        lab_unit_id: object,
        disease_id: object,
        camera_id: object,
        area_id: object,
        is_mydriatic: bool,
        profile_id: object | None = None,
    ) -> PregradedImageSelection:
        if not isinstance(is_mydriatic, bool):
            raise invalid("is_mydriatic must be a boolean.")
        return cls(
            project_id=_positive(project_id, "project_id"),
            hospital_id=_positive(hospital_id, "hospital_id"),
            lab_unit_id=_positive(lab_unit_id, "lab_unit_id"),
            disease_id=_positive(disease_id, "disease_id"),
            camera_id=_positive(camera_id, "camera_id"),
            area_id=_positive(area_id, "area_id"),
            is_mydriatic=is_mydriatic,
            profile_id=(
                _positive(profile_id, "profile_id") if profile_id not in (None, "") else None
            ),
        )


@dataclass(frozen=True)
class AuthorizedGradeTarget:
    normalized_image_name: str
    upload_id: int


@dataclass(frozen=True)
class AuthorizedGradeImport:
    project_id: int
    lab_unit_id: int
    disease_id: int
    upload_ids: tuple[int, ...]
    profile_ids: tuple[int, ...]
    targets: tuple[AuthorizedGradeTarget, ...]
