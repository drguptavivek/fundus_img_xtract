from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from flask import render_template, request
from flask_login import current_user
from auth.roles import roles_required
from sqlalchemy import text

from . import bp
from models import AIModel, Camera, Disease, DiseaseGrading, LabUnit
from utils.upload_eligibility import get_user_lab_unit_ids_no_admin_override
from db_transaction_manager import get_db_session

import json
import random
import re


@dataclass(frozen=True)
class LabelMetrics:
    """Per-class metrics for a disease grading label."""

    label: str
    support: int
    tp: int
    fp: int
    tn: int
    fn: int
    precision: Optional[float]
    recall: Optional[float]
    sensitivity: Optional[float]
    specificity: Optional[float]
    ppv: Optional[float]
    npv: Optional[float]
    f1: Optional[float]


@dataclass(frozen=True)
class ModelPerformance:
    """Aggregated performance details for an AI model."""

    labels: List[str]
    cross_tab: Dict[str, Dict[str, int]]
    label_metrics: List[LabelMetrics]
    overall: Dict[str, Optional[float]]
    total: int
    correct: int
    binary_metrics: Optional[Dict[str, Optional[float]]]
    binary_ci: Optional[Dict[str, Tuple[Optional[float], Optional[float]]]]
    auc: Optional[float]
    auc_ci: Optional[Tuple[Optional[float], Optional[float]]]
    roc_points: List[Dict[str, float]]


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    """Guard division against zero."""
    if denominator == 0:
        return None
    return numerator / denominator


def _cohens_kappa(pairs: Sequence[Tuple[str, str]], labels: Sequence[str]) -> Optional[float]:
    """Calculate Cohen's kappa for the provided label pairs."""
    n = len(pairs)
    if n == 0:
        return None

    label_to_idx = {label: idx for idx, label in enumerate(labels)}
    size = len(labels)
    matrix = [[0 for _ in range(size)] for _ in range(size)]

    for actual, predicted in pairs:
        i = label_to_idx.get(actual)
        j = label_to_idx.get(predicted)
        if i is None or j is None:
            continue
        matrix[i][j] += 1

    observed_agreement = sum(matrix[i][i] for i in range(size)) / n

    row_totals = [sum(row) for row in matrix]
    col_totals = [sum(matrix[i][j] for i in range(size)) for j in range(size)]

    expected_agreement = sum(
        (row_totals[i] / n) * (col_totals[i] / n) for i in range(size)
    )

    if expected_agreement == 1:
        return 1.0

    return round((observed_agreement - expected_agreement) / (1 - expected_agreement), 3)


def _calculate_label_metrics(
    label: str,
    pairs: Sequence[Tuple[str, str]],
    total: int,
) -> LabelMetrics:
    """Compute binary-style metrics for one label vs all others."""
    tp = sum(1 for actual, pred in pairs if actual == label and pred == label)
    fp = sum(1 for actual, pred in pairs if actual != label and pred == label)
    fn = sum(1 for actual, pred in pairs if actual == label and pred != label)
    tn = total - tp - fp - fn

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    npv = _safe_div(tn, tn + fn)
    f1 = _safe_div(2 * tp, 2 * tp + fp + fn)

    def _round(val: Optional[float]) -> Optional[float]:
        return round(val, 3) if val is not None else None

    return LabelMetrics(
        label=label,
        support=tp + fn,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        precision=_round(precision),
        recall=_round(recall),
        sensitivity=_round(recall),
        specificity=_round(specificity),
        ppv=_round(precision),
        npv=_round(npv),
        f1=_round(f1),
    )


def _build_cross_tab(labels: Sequence[str], pairs: Sequence[Tuple[str, str]]) -> Dict[str, Dict[str, int]]:
    """Build a cross-tabulation matrix keyed by actual then predicted label."""
    cross_tab: Dict[str, Dict[str, int]] = {label: {p: 0 for p in labels} for label in labels}
    for actual, predicted in pairs:
        if actual not in cross_tab:
            cross_tab[actual] = {p: 0 for p in labels}
        if predicted not in cross_tab[actual]:
            for row in cross_tab.values():
                row.setdefault(predicted, 0)
        cross_tab[actual][predicted] = cross_tab[actual].get(predicted, 0) + 1
    return cross_tab


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Compute percentile on a sorted list."""
    if not values:
        return float("nan")
    k = (len(values) - 1) * percentile
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def _bootstrap_ci(samples: Sequence[float], lower: float = 0.025, upper: float = 0.975) -> Tuple[Optional[float], Optional[float]]:
    """Return lower/upper percentile if samples present."""
    if not samples:
        return None, None
    sorted_vals = sorted(samples)
    return round(_percentile(sorted_vals, lower), 3), round(_percentile(sorted_vals, upper), 3)


def _parse_ai_probability(comment: Optional[str]) -> Optional[float]:
    """Extract the first probability float from the Grade.comment field."""
    if not comment:
        return None
    match = re.search(r"AI probability:\s*([0-9]*\.?[0-9]+)", comment)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _compute_roc(cases: Sequence[Dict[str, object]]) -> Tuple[List[Dict[str, float]], Optional[float]]:
    """Compute ROC points and AUC."""
    scored = [(c["score"], c["y_true"]) for c in cases if c.get("score") is not None]
    if not scored:
        return [], None
    pos = sum(1 for _, y in scored if y)
    neg = sum(1 for _, y in scored if not y)
    if pos == 0 or neg == 0:
        return [], None

    unique_thresholds = sorted({s for s, _ in scored}, reverse=True)
    points: List[Tuple[float, float, float]] = []
    for t in unique_thresholds:
        tp = sum(1 for s, y in scored if s >= t and y)
        fp = sum(1 for s, y in scored if s >= t and not y)
        fn = pos - tp
        tn = neg - fp
        tpr = tp / pos if pos else 0.0
        fpr = fp / neg if neg else 0.0
        points.append((fpr, tpr, t))

    points.sort(key=lambda p: p[0])
    roc_points = [{"fpr": 0.0, "tpr": 0.0, "threshold": unique_thresholds[0] if unique_thresholds else 0.0}]
    roc_points.extend({"fpr": fpr, "tpr": tpr, "threshold": thr} for fpr, tpr, thr in points)
    roc_points.append({"fpr": 1.0, "tpr": 1.0, "threshold": 0.0})

    auc = 0.0
    for i in range(1, len(roc_points)):
        x1, y1 = roc_points[i - 1]["fpr"], roc_points[i - 1]["tpr"]
        x2, y2 = roc_points[i]["fpr"], roc_points[i]["tpr"]
        auc += (x2 - x1) * (y1 + y2) / 2

    return roc_points, round(auc, 3)


def _compute_binary_metrics(
    cases: Sequence[Dict[str, object]],
    threshold: float,
) -> Dict[str, Optional[float]]:
    """Compute binary classification metrics from prepared cases."""
    tp = sum(1 for c in cases if c["y_true"] and c["y_pred"])
    tn = sum(1 for c in cases if not c["y_true"] and not c["y_pred"])
    fp = sum(1 for c in cases if not c["y_true"] and c["y_pred"])
    fn = sum(1 for c in cases if c["y_true"] and not c["y_pred"])
    total = len(cases)

    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    npv = _safe_div(tn, tn + fn)
    f1 = _safe_div(2 * tp, 2 * tp + fp + fn)
    accuracy = _safe_div(tp + tn, total)

    expected_agreement = _safe_div(((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)), total * total) if total else None
    kappa = None
    if expected_agreement is not None and expected_agreement != 1 and accuracy is not None:
        kappa = (accuracy - expected_agreement) / (1 - expected_agreement)

    def _round(val: Optional[float]) -> Optional[float]:
        return round(val, 3) if val is not None else None

    return {
        "support": total,
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "precision": _round(precision),
        "recall": _round(recall),
        "sensitivity": _round(recall),
        "specificity": _round(specificity),
        "ppv": _round(precision),
        "npv": _round(npv),
        "f1": _round(f1),
        "accuracy": _round(accuracy),
        "kappa": _round(kappa),
        "threshold": threshold,
    }


def _build_binary_with_ci(
    cases: Sequence[Dict[str, object]],
    threshold: float,
    bootstrap_samples: int,
) -> Tuple[Dict[str, Optional[float]], Dict[str, Tuple[Optional[float], Optional[float]]], Optional[float], Optional[Tuple[Optional[float], Optional[float]]], List[Dict[str, float]]]:
    """Compute binary metrics and bootstrap confidence intervals."""
    if len(cases) < 20:
        return {}, {}, None, None, []

    point_metrics = _compute_binary_metrics(cases, threshold)
    roc_points, auc = _compute_roc(cases)

    metric_samples: Dict[str, List[float]] = {k: [] for k in ("precision", "recall", "specificity", "ppv", "npv", "f1", "accuracy", "kappa")}
    auc_samples: List[float] = []

    bootstrap_samples = max(100, min(bootstrap_samples, 10000))

    for _ in range(bootstrap_samples):
        resampled = [cases[random.randrange(len(cases))] for _ in range(len(cases))]
        sample_metrics = _compute_binary_metrics(resampled, threshold)
        for key in metric_samples:
            if sample_metrics.get(key) is not None:
                metric_samples[key].append(sample_metrics[key])
        _, sample_auc = _compute_roc(resampled)
        if sample_auc is not None:
            auc_samples.append(sample_auc)

    ci_map: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for key, values in metric_samples.items():
        ci_map[key] = _bootstrap_ci(values)

    auc_ci = _bootstrap_ci(auc_samples) if auc_samples else (None, None)

    return point_metrics, ci_map, auc, auc_ci, roc_points


@bp.route("/model-performance", methods=["GET"])
@roles_required("admin", "data_manager")
def model_performance() -> str:
    """Show AI model performance against human reference grades using mvw_grading_data_all."""
    disease_id = request.args.get("disease_id", type=int)
    ai_model_id = request.args.get("ai_model_id", type=int)
    selected_lab_units = request.args.getlist("lab_unit_id", type=int)
    reference_source = request.args.get("reference_source", default="consensus")
    threshold = request.args.get("threshold", default=0.5, type=float)
    bootstrap_samples = request.args.get("bootstrap_samples", default=2000, type=int)
    upload_type = (request.args.get("upload_type") or "").strip().lower() or None
    positive_labels = request.args.getlist("positive_label")
    exclude_labels = set(request.args.getlist("exclude_label"))
    camera_id = request.args.get("camera_id", type=int)

    performance: Optional[ModelPerformance] = None
    selected_disease: Optional[Disease] = None
    selected_model: Optional[AIModel] = None
    error_message: Optional[str] = None
    labels_for_disease: List[str] = []
    lab_units_payload: List[Dict[str, object]] = []
    cameras_payload: List[Dict[str, object]] = []
    diseases_payload: List[Dict[str, object]] = []
    ai_models_payload: List[Dict[str, object]] = []
    selected_disease_name: Optional[str] = None
    selected_model_name: Optional[str] = None
    selected_model_version: Optional[str] = None

    with get_db_session() as db:
        diseases = db.query(Disease).order_by(Disease.name).all()
        ai_models = db.query(AIModel).order_by(AIModel.name, AIModel.version).all()
        cameras = db.query(Camera).order_by(Camera.name).all()

        diseases_payload = [{"id": d.id, "name": d.name} for d in diseases]
        ai_models_payload = [{"id": m.id, "name": m.name, "version": m.version} for m in ai_models]
        cameras_payload = [{"id": c.id, "name": c.name} for c in cameras]

        if disease_id:
            selected_disease = next((d for d in diseases if d.id == disease_id), None)
            if selected_disease:
                selected_disease_name = selected_disease.name
        if ai_model_id:
            selected_model = next((m for m in ai_models if m.id == ai_model_id), None)
            if selected_model:
                selected_model_name = selected_model.name
                selected_model_version = selected_model.version

        # Lab unit options respecting access
        user_lab_unit_ids = get_user_lab_unit_ids_no_admin_override(current_user.id)
        is_admin_like = current_user.has_role("admin", "data_manager")
        if is_admin_like:
            lab_units = db.query(LabUnit).order_by(LabUnit.name).all()
        else:
            lab_units = db.query(LabUnit).filter(LabUnit.id.in_(list(user_lab_unit_ids))).order_by(LabUnit.name).all()
        lab_units_payload = [{"id": lu.id, "name": lu.name} for lu in lab_units]

        if disease_id and ai_model_id:
            dg_rows = (
                db.query(DiseaseGrading)
                .filter(DiseaseGrading.disease_id == disease_id)
                .order_by(DiseaseGrading.display_order, DiseaseGrading.id)
                .all()
            )
            labels_for_disease = [dg.impression for dg in dg_rows]
            available_label_names = labels_for_disease
            if positive_labels:
                unknown_positive = [lbl for lbl in positive_labels if lbl not in available_label_names]
                if unknown_positive:
                    error_message = f"Unknown positive labels: {', '.join(unknown_positive)}"

            if not error_message:
                # Build base query from materialized view
                sql_parts = [
                    """
                    SELECT
                        task_id,
                        task_created_at,
                        image_uuid,
                        image_source,
                        camera_id,
                        lab_unit_id,
                        lab_unit_name,
                        hospital_name,
                        disease_id,
                        disease_name,
                        task_state,
                        grade_role_slot,
                        grade_name,
                        grade_comment,
                        grade_created_at,
                        ai_model_id,
                        ai_model_name,
                        ai_model_version,
                        consensus_final_grade_name
                    FROM mvw_grading_data_all
                    WHERE disease_id = :disease_id
                    """
                ]
                params: Dict[str, object] = {"disease_id": disease_id}

                if upload_type in {"zip", "direct"}:
                    params["image_source"] = "encounter_file" if upload_type == "zip" else "direct_upload"
                    sql_parts.append("AND image_source = :image_source")

                if camera_id:
                    params["camera_id"] = camera_id
                    sql_parts.append("AND camera_id = :camera_id")

                # Lab unit filter respecting access
                if selected_lab_units:
                    requested = set(selected_lab_units)
                    if not is_admin_like:
                        requested = requested & set(user_lab_unit_ids or [])
                    if requested:
                        placeholders = []
                        for idx, val in enumerate(requested):
                            key = f"lab_unit_id_{idx}"
                            params[key] = val
                            placeholders.append(f":{key}")
                        sql_parts.append(f"AND lab_unit_id IN ({', '.join(placeholders)})")
                    else:
                        sql_parts.append("AND 1=0")
                elif not is_admin_like and user_lab_unit_ids:
                    placeholders = []
                    for idx, val in enumerate(user_lab_unit_ids):
                        key = f"lab_unit_id_{idx}"
                        params[key] = val
                        placeholders.append(f":{key}")
                    if placeholders:
                        sql_parts.append(f"AND lab_unit_id IN ({', '.join(placeholders)})")

                sql_parts.append("ORDER BY task_created_at DESC, grade_created_at DESC")
                query = text("\n".join(sql_parts))

                rows = db.execute(query, params).mappings().all()

                # Organize by task_id
                tasks: Dict[int, Dict[str, object]] = {}
                for row in rows:
                    task_id = row["task_id"]
                    if task_id not in tasks:
                        tasks[task_id] = {
                            "task_created_at": row["task_created_at"],
                            "image_uuid": row["image_uuid"],
                            "image_source": row["image_source"],
                            "camera_id": row["camera_id"],
                            "lab_unit_id": row["lab_unit_id"],
                            "lab_unit_name": row["lab_unit_name"],
                            "hospital_name": row["hospital_name"],
                            "disease_id": row["disease_id"],
                            "disease_name": row["disease_name"],
                            "task_state": row["task_state"],
                            "consensus_label": row["consensus_final_grade_name"],
                            "ai_grades": [],
                            "ref_grades": {
                                "resident": None,
                                "resident2": None,
                                "arbitrator": None,
                            },
                        }

                    # Capture AI grades for selected model
                    if row["grade_role_slot"] == "ai" and row["ai_model_id"] == ai_model_id:
                        tasks[task_id]["ai_grades"].append(
                            {
                                "label": row["grade_name"],
                                "comment": row["grade_comment"],
                                "created_at": row["grade_created_at"],
                            }
                        )

                    # Capture reference grades
                    if row["grade_role_slot"] in {"resident", "resident2", "arbitrator"} and row["grade_name"]:
                        current = tasks[task_id]["ref_grades"].get(row["grade_role_slot"])
                        # Keep latest by grade_created_at
                        if current is None or (row["grade_created_at"] and row["grade_created_at"] > current["created_at"]):
                            tasks[task_id]["ref_grades"][row["grade_role_slot"]] = {
                                "label": row["grade_name"],
                                "created_at": row["grade_created_at"],
                            }

                # Keep only tasks that have an AI grade for this model
                tasks = {tid: data for tid, data in tasks.items() if data["ai_grades"]}

                # Group by image_uuid + disease to choose the latest task per image
                grouped: Dict[Tuple[str, int], List[Tuple[int, Dict[str, object]]]] = {}
                for tid, data in tasks.items():
                    key = (data["image_uuid"], data["disease_id"])
                    grouped.setdefault(key, []).append((tid, data))

                pairs: List[Tuple[str, str]] = []
                cases: List[Dict[str, object]] = []

                for _key, task_entries in grouped.items():
                    # Choose latest task by task_created_at
                    task_entries.sort(key=lambda item: item[1]["task_created_at"] or item[1]["ai_grades"][0]["created_at"], reverse=True)
                    _, data = task_entries[0]

                    # Reference label selection
                    ref_label = None
                    if reference_source == "consensus":
                        ref_label = data["consensus_label"]
                    else:
                        ref_obj = data["ref_grades"].get(reference_source)
                        ref_label = ref_obj["label"] if ref_obj else None

                    if not ref_label:
                        continue

                    # Latest AI grade for the task
                    ai_grades = sorted(data["ai_grades"], key=lambda g: g["created_at"] or 0, reverse=True)
                    ai_grade = ai_grades[0]
                    pred_label = ai_grade["label"]

                    if not pred_label:
                        continue

                    # Apply exclusions
                    if ref_label in exclude_labels or pred_label in exclude_labels:
                        continue

                    pairs.append((ref_label, pred_label))

                    positive_set = set(positive_labels)
                    if positive_set:
                        is_positive_true = ref_label in positive_set
                        score_raw = _parse_ai_probability(ai_grade["comment"])
                        if score_raw is not None:
                            positive_score = score_raw if pred_label in positive_set else 1 - score_raw
                            predicted_positive = positive_score >= threshold
                        else:
                            positive_score = None
                            predicted_positive = pred_label in positive_set

                        cases.append(
                            {
                                "y_true": is_positive_true,
                                "y_pred": predicted_positive,
                                "score": positive_score,
                                "reference": ref_label,
                                "predicted": pred_label,
                            }
                        )

                if pairs:
                    # Build label list (disease ordering first, then encountered)
                    label_order = labels_for_disease
                    all_labels: List[str] = list(label_order)
                    for actual, predicted in pairs:
                        if actual not in all_labels:
                            all_labels.append(actual)
                        if predicted not in all_labels:
                            all_labels.append(predicted)

                    total = len(pairs)
                    correct = sum(1 for a, p in pairs if a == p)
                    cross_tab = _build_cross_tab(all_labels, pairs)
                    label_metrics = [_calculate_label_metrics(label, pairs, total) for label in all_labels]

                    def _avg(values: Sequence[Optional[float]]) -> Optional[float]:
                        filtered = [v for v in values if v is not None]
                        if not filtered:
                            return None
                        return round(sum(filtered) / len(filtered), 3)

                    overall = {
                        "accuracy": round(correct / total, 3) if total else None,
                        "macro_precision": _avg([m.precision for m in label_metrics]),
                        "macro_recall": _avg([m.recall for m in label_metrics]),
                        "macro_specificity": _avg([m.specificity for m in label_metrics]),
                        "macro_f1": _avg([m.f1 for m in label_metrics]),
                        "cohens_kappa": _cohens_kappa(pairs, all_labels),
                    }

                    binary_metrics = None
                    binary_ci = None
                    auc = None
                    auc_ci = None
                    roc_points: List[Dict[str, float]] = []

                    if positive_labels:
                        point_metrics, ci_map, auc_val, auc_ci_val, roc_pts = _build_binary_with_ci(
                            cases,
                            threshold,
                            bootstrap_samples,
                        )
                        binary_metrics = point_metrics if point_metrics else None
                        binary_ci = ci_map if ci_map else None
                        auc = auc_val
                        auc_ci = auc_ci_val
                        roc_points = roc_pts

                    performance = ModelPerformance(
                        labels=all_labels,
                        cross_tab=cross_tab,
                        label_metrics=label_metrics,
                        overall=overall,
                        total=total,
                        correct=correct,
                        binary_metrics=binary_metrics,
                        binary_ci=binary_ci,
                        auc=auc,
                        auc_ci=auc_ci,
                        roc_points=roc_points,
                    )

    return render_template(
        "analytics/model_performance.html",
        diseases=diseases_payload,
        ai_models=ai_models_payload,
        selected_disease_id=disease_id,
        selected_model_id=ai_model_id,
        selected_disease_name=selected_disease_name,
        selected_model_name=selected_model_name,
        selected_model_version=selected_model_version,
        performance=performance,
        error_message=error_message,
        labels_for_disease=labels_for_disease or [],
        reference_source=reference_source,
        positive_labels=positive_labels,
        exclude_labels=exclude_labels,
        threshold=threshold,
        bootstrap_samples=bootstrap_samples,
        lab_units=lab_units_payload,
        selected_lab_units=selected_lab_units,
        upload_type=upload_type,
        cameras=cameras_payload,
        selected_camera_id=camera_id,
        roc_points_json=json.dumps(performance.roc_points) if performance and performance.roc_points else "[]",
    )
