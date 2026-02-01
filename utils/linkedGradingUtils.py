"""
Utilities for linked grading workflows.
"""

from typing import Iterable, List, Optional
from sqlalchemy import select

from models import LinkedDiseaseGrading


def get_linked_disease_ids(db, primary_disease_id: int) -> List[int]:
    """
    Get all linked disease IDs recursively (e.g. A->B->C).
    Returns a flat list of all descendants.
    """
    all_linked = []
    queue = [primary_disease_id]
    visited = {primary_disease_id}
    
    while queue:
        current_id = queue.pop(0)
        rows = db.execute(
            select(LinkedDiseaseGrading.linked_disease_id)
            .where(LinkedDiseaseGrading.primary_disease_id == current_id)
            .where(LinkedDiseaseGrading.is_active == True)
            .order_by(LinkedDiseaseGrading.display_order, LinkedDiseaseGrading.id)
        ).all()
        
        children = [row[0] for row in rows]
        for child_id in children:
            if child_id not in visited:
                visited.add(child_id)
                all_linked.append(child_id)
                queue.append(child_id)
                
    return all_linked


def get_primary_disease_id(db, disease_id: int) -> int:
    """
    Get the root primary disease ID for any disease in a linked chain.
    Supports recursive chains: A->B->C returns A for any of B or C.
    """
    current_id = disease_id
    visited = {disease_id}

    while True:
        row = db.execute(
            select(LinkedDiseaseGrading.primary_disease_id)
            .where(LinkedDiseaseGrading.linked_disease_id == current_id)
            .where(LinkedDiseaseGrading.is_active == True)
        ).first()

        if not row:
            # No parent found, current_id is the primary
            return current_id

        parent_id = row[0]
        if parent_id in visited:
            # Cycle detected, return current
            return current_id

        visited.add(parent_id)
        current_id = parent_id


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
