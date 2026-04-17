from __future__ import annotations

from typing import Any


FINAL_GRADE_BASIS_PREFERENCE = "preference"
FINAL_GRADE_BASIS_DOUBLE_MATCH = "double_match"
FINAL_GRADE_BASIS_VALUES = {
    FINAL_GRADE_BASIS_PREFERENCE,
    FINAL_GRADE_BASIS_DOUBLE_MATCH,
}
FINAL_GRADE_UNRESOLVED = "Unresolved"


def normalize_final_grade_basis(value: Any) -> str:
    basis = str(value or "").strip().lower()
    if basis in FINAL_GRADE_BASIS_VALUES:
        return basis
    return FINAL_GRADE_BASIS_PREFERENCE


def final_grade_basis_label(value: Any) -> str:
    basis = normalize_final_grade_basis(value)
    if basis == FINAL_GRADE_BASIS_DOUBLE_MATCH:
        return "Double-Match Based"
    return "Preference Based"


def basis_uses_unresolved(value: Any) -> bool:
    return normalize_final_grade_basis(value) == FINAL_GRADE_BASIS_DOUBLE_MATCH


def final_grade_candidates(
    basis: Any,
    *,
    resident_grade: Any,
    resident2_grade: Any,
    arbitrator_grade: Any,
    regrade_adj_grade: Any,
) -> list[str]:
    normalized_basis = normalize_final_grade_basis(basis)
    if normalized_basis == FINAL_GRADE_BASIS_DOUBLE_MATCH:
        if regrade_adj_grade:
            grades = [resident_grade, resident2_grade, regrade_adj_grade]
        else:
            grades = [resident_grade, resident2_grade, arbitrator_grade]
        return [str(grade) for grade in grades if grade]

    if regrade_adj_grade:
        return [str(regrade_adj_grade)]
    if arbitrator_grade:
        return [str(arbitrator_grade)]
    if resident_grade and resident_grade == resident2_grade:
        return [str(resident_grade)]
    return []


def derive_final_grade_value(
    basis: Any,
    *,
    resident_grade: Any,
    resident2_grade: Any,
    arbitrator_grade: Any,
    regrade_adj_grade: Any,
) -> str | None:
    normalized_basis = normalize_final_grade_basis(basis)
    if normalized_basis == FINAL_GRADE_BASIS_DOUBLE_MATCH:
        candidates = final_grade_candidates(
            normalized_basis,
            resident_grade=resident_grade,
            resident2_grade=resident2_grade,
            arbitrator_grade=arbitrator_grade,
            regrade_adj_grade=regrade_adj_grade,
        )
        if len(candidates) < 2:
            return FINAL_GRADE_UNRESOLVED

        counts: dict[str, int] = {}
        for candidate in candidates:
            counts[candidate] = counts.get(candidate, 0) + 1
            if counts[candidate] >= 2:
                return candidate
        return FINAL_GRADE_UNRESOLVED

    candidates = final_grade_candidates(
        normalized_basis,
        resident_grade=resident_grade,
        resident2_grade=resident2_grade,
        arbitrator_grade=arbitrator_grade,
        regrade_adj_grade=regrade_adj_grade,
    )
    return candidates[0] if candidates else None


def derive_final_grade_source(
    basis: Any,
    *,
    resident_grade: Any,
    resident2_grade: Any,
    arbitrator_grade: Any,
    regrade_adj_grade: Any,
) -> str:
    normalized_basis = normalize_final_grade_basis(basis)
    final_value = derive_final_grade_value(
        normalized_basis,
        resident_grade=resident_grade,
        resident2_grade=resident2_grade,
        arbitrator_grade=arbitrator_grade,
        regrade_adj_grade=regrade_adj_grade,
    )
    if normalized_basis == FINAL_GRADE_BASIS_DOUBLE_MATCH:
        if final_value == FINAL_GRADE_UNRESOLVED:
            return "No majority"
        if regrade_adj_grade:
            if resident_grade and resident2_grade and resident_grade == resident2_grade == final_value:
                return "Resident + Resident2"
            if resident_grade == regrade_adj_grade == final_value:
                return "Resident + Regrade"
            if resident2_grade == regrade_adj_grade == final_value:
                return "Resident2 + Regrade"
            return "Regrade set"
        if resident_grade and resident2_grade and resident_grade == resident2_grade == final_value:
            return "Resident + Resident2"
        if resident_grade == arbitrator_grade == final_value:
            return "Resident + Arbitrator"
        if resident2_grade == arbitrator_grade == final_value:
            return "Resident2 + Arbitrator"
        return "No majority"

    if regrade_adj_grade and final_value == regrade_adj_grade:
        return "Regrade Adj"
    if arbitrator_grade and final_value == arbitrator_grade:
        return "Arbitrator"
    if resident_grade and resident2_grade and resident_grade == resident2_grade == final_value:
        return "Resident + Resident2"
    return "No final"


def sql_grade_column(column: str, alias: str | None = "v") -> str:
    prefix = f"{alias}." if alias else ""
    return f"{prefix}{column}"


def sql_preference_final_grade(alias: str | None = "v") -> str:
    resident = sql_grade_column("resident_grade_name", alias)
    resident2 = sql_grade_column("resident2_grade_name", alias)
    arbitrator = sql_grade_column("arbitrator_grade_name", alias)
    regrade = sql_grade_column("regrade_adj_grade_name", alias)
    return (
        "COALESCE("
        f"{regrade}, "
        f"{arbitrator}, "
        f"CASE WHEN {resident} = {resident2} THEN {resident} ELSE NULL END"
        ")"
    )


def sql_double_match_final_grade(alias: str | None = "v") -> str:
    resident = sql_grade_column("resident_grade_name", alias)
    resident2 = sql_grade_column("resident2_grade_name", alias)
    arbitrator = sql_grade_column("arbitrator_grade_name", alias)
    regrade = sql_grade_column("regrade_adj_grade_name", alias)
    unresolved = FINAL_GRADE_UNRESOLVED.replace("'", "''")
    return f"""
        CASE
            WHEN {regrade} IS NOT NULL THEN
                CASE
                    WHEN {resident} IS NULL AND {resident2} IS NULL THEN '{unresolved}'
                    WHEN {resident} = {resident2} AND {resident} IS NOT NULL THEN {resident}
                    WHEN {resident} = {regrade} AND {resident} IS NOT NULL THEN {resident}
                    WHEN {resident2} = {regrade} AND {resident2} IS NOT NULL THEN {resident2}
                    ELSE '{unresolved}'
                END
            ELSE
                CASE
                    WHEN ({resident} IS NOT NULL)::int + ({resident2} IS NOT NULL)::int + ({arbitrator} IS NOT NULL)::int < 2 THEN '{unresolved}'
                    WHEN {resident} = {resident2} AND {resident} IS NOT NULL THEN {resident}
                    WHEN {resident} = {arbitrator} AND {resident} IS NOT NULL THEN {resident}
                    WHEN {resident2} = {arbitrator} AND {resident2} IS NOT NULL THEN {resident2}
                    ELSE '{unresolved}'
                END
        END
    """


def sql_final_grade_expression(basis: Any, alias: str | None = "v") -> str:
    normalized_basis = normalize_final_grade_basis(basis)
    if normalized_basis == FINAL_GRADE_BASIS_DOUBLE_MATCH:
        return sql_double_match_final_grade(alias)
    return sql_preference_final_grade(alias)


def sql_final_plus_review_expression(basis: Any, alias: str | None = "v") -> str:
    review = sql_grade_column("review_grade_name", alias)
    return f"COALESCE({review}, {sql_final_grade_expression(basis, alias)})"


def sql_json_role_grade(detail_column: str, role_slot: str) -> str:
    escaped_role = role_slot.replace("'", "''")
    return (
        f"(SELECT elem->>'grade_name' "
        f"FROM jsonb_array_elements({detail_column}::jsonb) elem "
        f"WHERE elem->>'role_slot' = '{escaped_role}' "
        "LIMIT 1)"
    )


def sql_json_final_grade_expression(basis: Any, detail_column: str) -> str:
    resident = sql_json_role_grade(detail_column, "resident")
    resident2 = sql_json_role_grade(detail_column, "resident2")
    arbitrator = sql_json_role_grade(detail_column, "arbitrator")
    regrade = sql_json_role_grade(detail_column, "regrade_adj")
    review = sql_json_role_grade(detail_column, "review")
    normalized_basis = normalize_final_grade_basis(basis)
    if normalized_basis == FINAL_GRADE_BASIS_DOUBLE_MATCH:
        unresolved = FINAL_GRADE_UNRESOLVED.replace("'", "''")
        return f"""
            CASE
                WHEN {regrade} IS NOT NULL THEN
                    CASE
                        WHEN {resident} IS NULL AND {resident2} IS NULL THEN '{unresolved}'
                        WHEN {resident} = {resident2} AND {resident} IS NOT NULL THEN {resident}
                        WHEN {resident} = {regrade} AND {resident} IS NOT NULL THEN {resident}
                        WHEN {resident2} = {regrade} AND {resident2} IS NOT NULL THEN {resident2}
                        ELSE '{unresolved}'
                    END
                ELSE
                    CASE
                        WHEN ({resident} IS NOT NULL)::int + ({resident2} IS NOT NULL)::int + ({arbitrator} IS NOT NULL)::int < 2 THEN '{unresolved}'
                        WHEN {resident} = {resident2} AND {resident} IS NOT NULL THEN {resident}
                        WHEN {resident} = {arbitrator} AND {resident} IS NOT NULL THEN {resident}
                        WHEN {resident2} = {arbitrator} AND {resident2} IS NOT NULL THEN {resident2}
                        ELSE '{unresolved}'
                    END
            END
        """
    return (
        "COALESCE("
        f"{regrade}, "
        f"{arbitrator}, "
        f"CASE WHEN {resident} = {resident2} THEN {resident} ELSE NULL END"
        ")"
    )


def sql_json_final_plus_review_expression(basis: Any, detail_column: str) -> str:
    review = sql_json_role_grade(detail_column, "review")
    return f"COALESCE({review}, {sql_json_final_grade_expression(basis, detail_column)})"
