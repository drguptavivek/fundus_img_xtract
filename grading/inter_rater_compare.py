from __future__ import annotations

from datetime import datetime, date as _date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flask import flash, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from app_cache import cache
from models import Consensus, Disease, DiseaseGrading, Grade, GradingTask, LabUnit, ImageMetadata
from authz import scope


def register_routes(bp):
    bp.add_url_rule("/my-inter-rater", view_func=inter_rater_compare, methods=["GET"])
    bp.add_url_rule("/my-inter-rater/viewer/<string:image_uuid>", view_func=inter_rater_viewer, methods=["GET"])


def _parse_date(value: str | None) -> Optional[_date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@roles_required("ophthalmologist", "admin")
def inter_rater_compare():
    """Compare user's own grades against other graders for the same tasks."""
    page = max(1, request.args.get("page", default=1, type=int) or 1)
    per_page = request.args.get("per_page", default=25, type=int)
    per_page = per_page if per_page and per_page > 0 else 25

    disease_id = request.args.get("disease_id", type=int)
    own_grades_filter = request.args.getlist("my_grade")
    resident_grades_filter = request.args.getlist("resident_grade")
    arbitrator_grades_filter = request.args.getlist("arbitrator_grade")
    final_grades_filter = request.args.getlist("final_grade")
    review_grades_filter = request.args.getlist("review_grade")
    date_after = _parse_date(request.args.get("date_after"))
    date_before = _parse_date(request.args.get("date_before"))

    with get_db_session() as db:
        diseases = db.query(Disease).order_by(Disease.name).all()
        if not diseases:
            flash("No diseases configured.", "warning")
            return render_template("grading/inter_rater_compare.html", rows=[], diseases=[], grade_options=[])

        # Get allowed lab units via scoping
        lu_query = db.query(LabUnit)
        lu_query = scope(db, lu_query, LabUnit, current_user, 'tasks.view')
        allowed_lab_unit_ids = [lu.id for lu in lu_query.all()]
        
        if not allowed_lab_unit_ids:
            flash("No lab unit access.", "warning")
            return render_template("grading/inter_rater_compare.html", rows=[], diseases=diseases, grade_options=[])

        grade_options: List[DiseaseGrading] = []
        disease_grade_map: Dict[int, List[str]] = {}

        # Build grade map for client-side hydration
        all_grades = (
            db.query(DiseaseGrading)
            .order_by(DiseaseGrading.disease_id, DiseaseGrading.display_order)
            .all()
        )
        for dg in all_grades:
            disease_grade_map.setdefault(dg.disease_id, []).append(dg.impression)

        if disease_id:
            grade_options = [dg for dg in all_grades if dg.disease_id == disease_id]

        if not disease_id:
            flash("Disease selection is required.", "info")
            return render_template(
                "grading/inter_rater_compare.html",
                rows=[],
                diseases=diseases,
                grade_options=grade_options,
                disease_grade_map=disease_grade_map,
    filters={
        "disease_id": disease_id,
        "my_grade": own_grades_filter,
        "resident_grade": resident_grades_filter,
        "arbitrator_grade": arbitrator_grades_filter,
        "final_grade": final_grades_filter,
        "review_grade": review_grades_filter,
        "date_after": request.args.get("date_after", ""),
        "date_before": request.args.get("date_before", ""),
        "per_page": per_page,
    },
)

        base_query = (
            db.query(Grade, GradingTask, LabUnit)
            .join(GradingTask, Grade.task_id == GradingTask.id)
            .join(LabUnit, GradingTask.lab_unit_id == LabUnit.id)
            .filter(
                Grade.grader_user_id == current_user.id,
                GradingTask.disease_id == disease_id,
                GradingTask.lab_unit_id.in_(allowed_lab_unit_ids),
            )
            .options(
                joinedload(GradingTask.lab_unit),
                joinedload(GradingTask.encounter_file),
                joinedload(GradingTask.direct_image),
            )
        )

        if own_grades_filter:
            base_query = base_query.filter(Grade.grade_name.in_(own_grades_filter))

        if date_after:
            base_query = base_query.filter(Grade.created_at >= datetime.combine(date_after, datetime.min.time()))
        if date_before:
            base_query = base_query.filter(Grade.created_at < datetime.combine(date_before, datetime.max.time()))

        cache_key = None
        if disease_id:
            key_parts = {
                "user_id": current_user.id,
                "disease_id": disease_id,
                "own": tuple(sorted(own_grades_filter)),
                "res": tuple(sorted(resident_grades_filter)),
                "arb": tuple(sorted(arbitrator_grades_filter)),
                "final": tuple(sorted(final_grades_filter)),
                "review": tuple(sorted(review_grades_filter)),
                "after": str(date_after) if date_after else "",
                "before": str(date_before) if date_before else "",
            }
            cache_key = f"inter_rater:{hash(frozenset(key_parts.items()))}"

        cached_rows = cache.get(cache_key) if cache_key else None

        filtered_rows: List[Dict[str, Any]] = []

        if cached_rows is not None:
            filtered_rows = cached_rows
            task_ids = [row["task_id"] for row in filtered_rows]
        else:
            self_rows: List[Tuple[Grade, GradingTask, LabUnit]] = base_query.order_by(Grade.created_at.desc()).all()
            task_ids = [row.GradingTask.id for row in self_rows]

        if cached_rows is None and task_ids:
            # Fetch other roles for these tasks
            other_grades_map: Dict[int, List[Grade]] = {}
            review_grades_map: Dict[int, List[Grade]] = {}
            other_roles = ["resident", "resident2", "arbitrator"]
            other_rows = (
                db.query(Grade)
                .filter(
                    Grade.task_id.in_(task_ids),
                    Grade.role_slot.in_(other_roles),
                    Grade.grader_user_id != current_user.id,
                )
                .all()
            )
            for grade in other_rows:
                other_grades_map.setdefault(grade.task_id, []).append(grade)

            review_rows = (
                db.query(Grade)
                .filter(Grade.task_id.in_(task_ids), Grade.role_slot == "review")
                .all()
            )
            for grade in review_rows:
                review_grades_map.setdefault(grade.task_id, []).append(grade)

            consensus_map: Dict[int, Consensus] = {}
            consensus_rows = db.query(Consensus).filter(Consensus.task_id.in_(task_ids)).all()
            consensus_map = {c.task_id: c for c in consensus_rows}

            # Apply secondary filters based on other graders/consensus
            filtered_rows = []
            for row in self_rows:
                task = row.GradingTask
                self_grade = row.Grade
                others = other_grades_map.get(task.id, [])
                reviews = review_grades_map.get(task.id, [])
                consensus = consensus_map.get(task.id)

                def _match_impressions(grades: Sequence[Grade], filters: List[str]) -> bool:
                    if not filters:
                        return True
                    return any(g.grade_name in filters for g in grades if g.grade_name)

                if not _match_impressions([g for g in others if g.role_slot in ("resident", "resident2")], resident_grades_filter):
                    continue
                if not _match_impressions([g for g in others if g.role_slot == "arbitrator"], arbitrator_grades_filter):
                    continue
                if final_grades_filter:
                    final_name = consensus.final_grade_name if consensus else None
                    if final_name not in final_grades_filter:
                        continue
                if not _match_impressions(reviews, review_grades_filter):
                    continue

                def _gdict(g: Grade) -> Dict[str, Any]:
                    return {
                        "grade_name": g.grade_name,
                        "role_slot": g.role_slot,
                    }

                filtered_rows.append(
                    {
                        "task_id": task.id,
                        "task_uuid": task.uuid,
                        "lab_unit_name": task.lab_unit.name if task.lab_unit else None,
                        "self_grade": _gdict(self_grade),
                        "resident_grades": [_gdict(g) for g in others if g.role_slot in ("resident", "resident2")],
                        "arbitrator_grades": [_gdict(g) for g in others if g.role_slot == "arbitrator"],
                        "review_grades": [_gdict(g) for g in reviews],
                        "consensus": {"final_grade_name": consensus.final_grade_name} if consensus else None,
                        "image_uuid": task.encounter_file.uuid if task.encounter_file else (task.direct_image.uuid if task.direct_image else None),
                        "self_role": self_grade.role_slot,
                    }
                )

            if cache_key:
                cache.set(cache_key, filtered_rows, timeout=600)  # 10 minutes

        total = len(filtered_rows)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        page_rows = filtered_rows[start:end]

        # Selected task for viewer
        selected_task_id = request.args.get("selected_task_id", type=int)
        if not selected_task_id and page_rows:
            selected_task_id = page_rows[0]["task_id"]

        selected_image_uuid = next((r["image_uuid"] for r in filtered_rows if r["task_id"] == selected_task_id), None)
        selected_task_obj = None

        base_args = request.args.to_dict(flat=True)
        base_args.pop("page", None)
        base_args.pop("per_page", None)

        prev_url = url_for(
            "grading.inter_rater_compare",
            page=page - 1,
            per_page=per_page,
            **base_args,
        ) if page > 1 else None
        next_url = url_for(
            "grading.inter_rater_compare",
            page=page + 1,
            per_page=per_page,
            **base_args,
        ) if page < total_pages else None

        base_filter_params = {
            "disease_id": disease_id,
            "per_page": per_page,
            "my_grade": own_grades_filter,
            "resident_grade": resident_grades_filter,
            "arbitrator_grade": arbitrator_grades_filter,
            "final_grade": final_grades_filter,
            "review_grade": review_grades_filter,
            "date_after": request.args.get("date_after", ""),
            "date_before": request.args.get("date_before", ""),
        }

        return render_template(
            "grading/inter_rater_compare.html",
            rows=page_rows,
            diseases=diseases,
            grade_options=grade_options,
            page=page,
            total=total,
            total_pages=total_pages,
            prev_url=prev_url,
            next_url=next_url,
            disease_grade_map=disease_grade_map,
            selected_task_id=selected_task_id,
            selected_image_uuid=selected_image_uuid,
            selected_task=selected_task_obj,
            filters={
                "disease_id": disease_id,
                "my_grade": own_grades_filter,
                "resident_grade": resident_grades_filter,
                "arbitrator_grade": arbitrator_grades_filter,
                "final_grade": final_grades_filter,
                "review_grade": review_grades_filter,
                "date_after": request.args.get("date_after", ""),
                "date_before": request.args.get("date_before", ""),
                "per_page": per_page,
            },
            base_filter_params=base_filter_params,
        )


@roles_required("ophthalmologist", "admin")
def inter_rater_viewer(image_uuid: str):
    """Serve just the viewer card for HTMX swaps."""
    with get_db_session() as db:
        # Get allowed lab units via scoping
        lu_query = db.query(LabUnit)
        lu_query = scope(db, lu_query, LabUnit, current_user, 'tasks.view')
        allowed_lab_unit_ids = [lu.id for lu in lu_query.all()]
        
        if not allowed_lab_unit_ids:
            return ("", 403)

        task = (
            db.query(GradingTask)
            .filter(
                and_(
                    GradingTask.lab_unit_id.in_(allowed_lab_unit_ids),
                    or_(
                        GradingTask.encounter_file.has(uuid=image_uuid),
                        GradingTask.direct_image.has(uuid=image_uuid),
                    ),
                )
            )
            .options(joinedload(GradingTask.encounter_file), joinedload(GradingTask.direct_image))
            .first()
        )
        if not task:
            return ("Not found", 404)

        image_obj = task.encounter_file or task.direct_image
        image_metadata = (
            db.query(ImageMetadata)
            .filter(
                ImageMetadata.image_uuid == image_uuid,
                ImageMetadata.image_variant == "orig",
            )
            .first()
        )
        return render_template(
            "partials/_grading_card.html",
            image=image_obj,
            image_uuid=image_uuid,
            image_metadata=image_metadata,
        )
