"""
Utilities for linked grading workflows.
"""

from typing import Iterable, List, Optional
from sqlalchemy import select

from models import LinkedDiseaseGrading


def get_linked_disease_ids(db, primary_disease_id: int) -> List[int]:
    rows = db.execute(
        select(LinkedDiseaseGrading.linked_disease_id)
        .where(LinkedDiseaseGrading.primary_disease_id == primary_disease_id)
        .where(LinkedDiseaseGrading.is_active == True)
        .order_by(LinkedDiseaseGrading.display_order, LinkedDiseaseGrading.id)
    ).all()
    return [row[0] for row in rows]


def get_primary_disease_id(db, disease_id: int) -> int:
    row = db.execute(
        select(LinkedDiseaseGrading.primary_disease_id)
        .where(LinkedDiseaseGrading.linked_disease_id == disease_id)
        .where(LinkedDiseaseGrading.is_active == True)
    ).first()
    return row[0] if row else disease_id


def is_primary_disease(db, disease_id: int) -> bool:
    row = db.execute(
        select(LinkedDiseaseGrading.id)
        .where(LinkedDiseaseGrading.primary_disease_id == disease_id)
        .where(LinkedDiseaseGrading.is_active == True)
        .limit(1)
    ).first()
    return row is not None


def expand_primary_disease_ids(db, disease_ids: Iterable[int]) -> List[int]:
    """
    Given a list of primary disease IDs, return a list including linked disease IDs.
    """
    expanded: List[int] = []
    for disease_id in disease_ids:
        if disease_id in expanded:
            continue
        expanded.append(disease_id)
        linked_ids = get_linked_disease_ids(db, disease_id)
        for linked_id in linked_ids:
            if linked_id not in expanded:
                expanded.append(linked_id)
    return expanded
