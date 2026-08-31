from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .errors import invalid


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise invalid(f"{field} must be a positive integer.")
    if isinstance(value, str) and (not value.strip() or not value.strip().isdigit()):
        raise invalid(f"{field} must be a positive integer.")
    parsed = int(value)
    if parsed <= 0:
        raise invalid(f"{field} must be a positive integer.")
    return parsed


@dataclass(frozen=True)
class SourceReference:
    source: str
    source_id: int

    @classmethod
    def from_payload(cls, value: Any) -> SourceReference:
        if not isinstance(value, dict):
            raise invalid("Every selected image reference must be an object.")
        source = str(value.get("source") or "").strip().lower()
        if source not in {"direct", "zip"}:
            raise invalid("Selected image source must be direct or zip.")
        source_id = _positive_integer(value.get("id"), "Selected image ID")
        return cls(source=source, source_id=source_id)


@dataclass(frozen=True)
class CreateAdHocTasksCommand:
    disease_ids: tuple[int, ...]
    references: tuple[SourceReference, ...]
    max_images: int
    filters: dict[str, Any]
    randomize: bool
    remarks: str | None

    @classmethod
    def from_payload(
        cls,
        *,
        disease_ids: Any,
        references: Any,
        max_images: Any,
        filters: Any,
        randomize: Any,
        remarks: Any,
    ) -> CreateAdHocTasksCommand:
        if not isinstance(disease_ids, list) or not disease_ids:
            raise invalid("diseases must be a non-empty array of positive integers.")
        parsed_diseases: list[int] = []
        for value in disease_ids:
            parsed = _positive_integer(value, "Disease ID")
            if parsed in parsed_diseases:
                raise invalid("diseases must contain unique positive integers.")
            parsed_diseases.append(parsed)
        if not isinstance(references, list) or not references:
            raise invalid("selected_image_refs must be a non-empty array.")
        parsed_refs = tuple(SourceReference.from_payload(item) for item in references)
        keys = {(item.source, item.source_id) for item in parsed_refs}
        if len(keys) != len(parsed_refs):
            raise invalid("selected_image_refs contains duplicate sources.")
        parsed_max = _positive_integer(max_images, "max_images")
        if parsed_max <= 0 or len(parsed_refs) > parsed_max:
            raise invalid("Selected images exceed max_images.")
        if not isinstance(filters, dict):
            raise invalid("filters must be an object.")
        if not isinstance(randomize, bool):
            raise invalid("randomize must be a boolean.")
        clean_remarks = str(remarks).strip() if remarks not in (None, "") else None
        return cls(
            disease_ids=tuple(parsed_diseases),
            references=parsed_refs,
            max_images=parsed_max,
            filters=dict(filters),
            randomize=randomize,
            remarks=clean_remarks,
        )


@dataclass(frozen=True)
class AuthorizedSource:
    source: str
    source_id: int
    lab_unit_id: int
    hospital_id: int


@dataclass(frozen=True)
class CreateResult:
    batch_id: int
    created: int


def references_from_payload(values: Iterable[Any]) -> tuple[SourceReference, ...]:
    return tuple(SourceReference.from_payload(value) for value in values)
