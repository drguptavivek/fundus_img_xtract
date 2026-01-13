from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from flask import jsonify, render_template, request, send_file
from flask_login import current_user
from auth.roles import roles_required
from sqlalchemy import text
from sqlalchemy.orm import Session
from app_cache import cache

from . import bp
from models import AIModel, Camera, Disease, DiseaseGrading, LabUnit
from utils.hospital_scoping import apply_scoping
from db_transaction_manager import get_db_session

import json
import hashlib
import random
import re
import math
import base64
import io

SKLEARN_AVAILABLE = False
MATPLOTLIB_AVAILABLE = False
OPENPYXL_AVAILABLE = False


def _ensure_sklearn() -> bool:
    """Lazy-load scikit-learn metrics to avoid import errors when missing."""
    global SKLEARN_AVAILABLE
    if SKLEARN_AVAILABLE:
        return True
    try:
        from sklearn.metrics import (
            accuracy_score,
            balanced_accuracy_score,
            cohen_kappa_score,
            confusion_matrix,
            precision_recall_fscore_support,
            roc_auc_score,
            roc_curve,
        )
        globals().update(
            accuracy_score=accuracy_score,
            balanced_accuracy_score=balanced_accuracy_score,
            cohen_kappa_score=cohen_kappa_score,
            confusion_matrix=confusion_matrix,
            precision_recall_fscore_support=precision_recall_fscore_support,
            roc_auc_score=roc_auc_score,
            roc_curve=roc_curve,
        )
        SKLEARN_AVAILABLE = True
        return True
    except ModuleNotFoundError:
        SKLEARN_AVAILABLE = False
        return False


def _ensure_matplotlib() -> bool:
    """Lazy-load matplotlib for confusion matrix rendering."""
    global MATPLOTLIB_AVAILABLE
    if MATPLOTLIB_AVAILABLE:
        return True
    try:
        import os
        import pathlib
        base_dir = pathlib.Path(__file__).resolve().parent.parent
        mpl_dir = base_dir / "tmp" / "matplotlib"
        mpl_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(mpl_dir)

        import matplotlib

        matplotlib.use("Agg")  # headless backend
        import matplotlib.pyplot as plt  # noqa: F401

        MATPLOTLIB_AVAILABLE = True
        return True
    except ModuleNotFoundError:
        MATPLOTLIB_AVAILABLE = False
        return False


def _ensure_openpyxl() -> bool:
    """Lazy-load openpyxl for Excel export."""
    global OPENPYXL_AVAILABLE
    if OPENPYXL_AVAILABLE:
        return True
    try:
        import openpyxl  # noqa: F401

        OPENPYXL_AVAILABLE = True
        return True
    except ModuleNotFoundError:
        OPENPYXL_AVAILABLE = False
        return False


def _render_confusion_image(cm: List[List[int]], labels: List[str]) -> Optional[str]:
    """Render confusion matrix as base64 PNG."""
    if not cm or not labels:
        return None
    if not (_ensure_matplotlib() and _ensure_sklearn()):
        return None
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # type: ignore
    from sklearn.metrics import ConfusionMatrixDisplay  # type: ignore

    try:
        cm_array = np.array(cm)
        fig, ax = plt.subplots(figsize=(6, 5))
        disp = ConfusionMatrixDisplay(confusion_matrix=cm_array, display_labels=labels)
        disp.plot(ax=ax, cmap="YlGnBu", values_format="d", colorbar=True)
        ax.set_title("Confusion Matrix", fontsize=12)
        ax.set_xlabel("Reference")
        ax.set_ylabel("Prediction")
        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        encoded = base64.b64encode(buf.read()).decode("ascii")
        return encoded
    except Exception:
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def _render_excel(rows: List[Dict[str, object]]) -> Optional[io.BytesIO]:
    """Render analyzed rows to an Excel file."""
    if not rows:
        return None
    if not _ensure_openpyxl():
        return None
    import openpyxl  # type: ignore

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "model_performance"

    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h) for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _parse_class_map(raw: str) -> Dict[str, List[str]]:
    """Parse JSON-style class map submitted from the UI."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    out: Dict[str, List[str]] = {}
    if isinstance(parsed, dict):
        for k, v in parsed.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, list):
                sources = [str(s) for s in v if isinstance(s, str) and s.strip()]
                if sources:
                    out[k.strip()] = sources
    return out


def _resolve_class_mapping(
    db: Session,
    disease_id: int,
    class_map: Dict[str, List[str]],
    positive_class: Optional[str],
) -> Tuple[Dict[str, List[str]], Dict[str, str], Optional[str], List[str], Optional[str]]:
    """
    Build a validated class definition map for a disease and return mappings plus any error.

    Returns (class_definitions, label_to_class, resolved_positive_class, labels_for_disease, error_message)
    """
    dg_rows = (
        db.query(DiseaseGrading)
        .filter(DiseaseGrading.disease_id == disease_id)
        .order_by(DiseaseGrading.display_order, DiseaseGrading.id)
        .all()
    )
    raw_labels = [dg.impression for dg in dg_rows]
    labels_for_disease = sorted({lbl for lbl in raw_labels})

    available_label_set = set(labels_for_disease)
    if not class_map:
        class_map = {lbl: [lbl] for lbl in labels_for_disease}

    cleaned_class_map: Dict[str, List[str]] = {}
    label_to_class: Dict[str, str] = {}
    duplicate_sources: List[str] = []

    for class_name, sources in class_map.items():
        if not class_name or not isinstance(sources, list):
            continue
        filtered_sources: List[str] = []
        for src in sources:
            if src not in available_label_set:
                continue
            if src in label_to_class:
                duplicate_sources.append(src)
                continue
            label_to_class[src] = class_name
            filtered_sources.append(src)
        if filtered_sources:
            cleaned_class_map[class_name] = filtered_sources

    error_message = None
    if duplicate_sources:
        error_message = (
            "Each label can belong to only one class. Duplicated labels: "
            + ", ".join(sorted(set(duplicate_sources)))
        )

    class_definitions = cleaned_class_map if cleaned_class_map else {lbl: [lbl] for lbl in labels_for_disease}
    if not cleaned_class_map:
        label_to_class = {lbl: lbl for lbl in labels_for_disease}
    else:
        label_to_class = {src: cls for cls, sources in class_definitions.items() for src in sources}

    if positive_class and positive_class not in class_definitions:
        error_message = f"Selected positive class '{positive_class}' is not defined."

    if not positive_class:
        class_names = list(class_definitions.keys())
        positive_class = class_names[0] if class_names else None

    return class_definitions, label_to_class, positive_class, labels_for_disease, error_message


def _build_threshold_range(
    min_threshold: float,
    max_threshold: float,
    delta: float,
    max_points: int = 25,
) -> Tuple[List[float], Optional[str]]:
    """Generate a threshold list bounded by max_points."""
    if delta <= 0:
        return [], "Threshold delta must be greater than 0."
    if min_threshold < 0 or max_threshold > 1:
        return [], "Thresholds must be within [0, 1]."
    if min_threshold > max_threshold:
        return [], "Minimum threshold cannot exceed maximum threshold."

    estimated_points = int(math.floor((max_threshold - min_threshold) / delta)) + 1
    if estimated_points > max_points:
        return [], f"Too many thresholds requested ({estimated_points}); reduce the range or increase delta to <= {max_points} points."

    thresholds: List[float] = []
    current = min_threshold
    while current <= max_threshold + 1e-9 and len(thresholds) < max_points:
        thresholds.append(round(current, 3))
        current += delta
    if not thresholds:
        thresholds = [round(min_threshold, 3)]
    return thresholds, None


def _build_threshold_cache_key(
    disease_id: int,
    ai_model_id: int,
    reference_source: str,
    upload_type: Optional[str],
    camera_id: Optional[int],
    class_definitions: Dict[str, List[str]],
    positive_class: Optional[str],
    lab_units: Sequence[int],
    thresholds: Sequence[float],
    sample_size: int,
) -> str:
    """Create a deterministic cache key for threshold explorer results."""
    payload = {
        "disease_id": disease_id,
        "ai_model_id": ai_model_id,
        "reference_source": reference_source,
        "upload_type": upload_type,
        "camera_id": camera_id,
        "class_definitions": class_definitions,
        "positive_class": positive_class,
        "lab_units": sorted(set(lab_units)),
        "thresholds": [round(t, 3) for t in thresholds],
        "sample_size": sample_size,
    }
    serialized = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"analytics:threshold-explorer:{digest}"


def _build_performance_cache_key(
    disease_id: int,
    ai_model_id: int,
    reference_source: str,
    upload_type: Optional[str],
    camera_id: Optional[int],
    class_definitions: Dict[str, List[str]],
    positive_class: Optional[str],
    threshold: float,
    bootstrap_samples: int,
    selected_lab_units: Sequence[int],
    allowed_lab_units: Sequence[int],
) -> str:
    """Create a deterministic cache key for the main model performance analysis."""
    normalized_classes = {cls: sorted(members) for cls, members in sorted(class_definitions.items())}
    payload = {
        "disease_id": disease_id,
        "ai_model_id": ai_model_id,
        "reference_source": reference_source,
        "upload_type": upload_type,
        "camera_id": camera_id,
        "class_definitions": normalized_classes,
        "positive_class": positive_class,
        "threshold": round(threshold, 3),
        "bootstrap_samples": bootstrap_samples,
        "selected_lab_units": sorted(set(selected_lab_units)),
        "allowed_lab_units": sorted(set(allowed_lab_units)),
    }
    serialized = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"analytics:model-performance:{digest}"


def _apply_threshold_to_cases(
    cases: Sequence[Dict[str, object]],
    positive_class: Optional[str],
    threshold: float,
) -> List[Dict[str, object]]:
    """Return case records with y_pred set according to the provided threshold."""
    if not positive_class:
        return []

    evaluated: List[Dict[str, object]] = []
    for case in cases:
        score = case.get("positive_score")
        predicted_class = case.get("predicted_class")
        is_positive_true = bool(case.get("y_true"))
        if score is None:
            predicted_positive = predicted_class == positive_class
            positive_score: Optional[float] = None
        else:
            positive_score = float(score)
            predicted_positive = positive_score >= threshold
        evaluated.append(
            {
                "y_true": is_positive_true,
                "y_pred": predicted_positive,
                "score": positive_score,
            }
        )
    return evaluated


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
    class_definitions: Dict[str, List[str]]
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
    binary_sample_size: int
    binary_ci_computed: bool
    roc_available: bool
    confusion_matrix: Optional[List[List[int]]]
    confusion_image_base64: Optional[str]
    row_totals: Optional[List[int]]
    col_totals: Optional[List[int]]
    percent_matrix: Optional[List[List[float]]]
    mismatches: List[Dict[str, object]]
    fp_count: int
    fn_count: int
    multi_class: bool


def _safe_div(numerator: float, denominator: float) -> Optional[float]:
    """Guard division against zero."""
    if denominator == 0:
        return None
    return numerator / denominator


def _cohens_kappa(pairs: Sequence[Tuple[str, str]], labels: Sequence[str]) -> Optional[float]:
    """Calculate Cohen's kappa using scikit-learn."""
    if not pairs:
        return None
    y_true = [a for a, _ in pairs]
    y_pred = [p for _, p in pairs]
    try:
        return round(cohen_kappa_score(y_true, y_pred, labels=list(labels)), 3)
    except Exception:
        return None


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
    """Compute ROC points and AUC using scikit-learn."""
    scored = [(c["score"], c["y_true"]) for c in cases if c.get("score") is not None]
    if not scored:
        return [], None
    y_scores = [s for s, _ in scored]
    y_true = [1 if y else 0 for _, y in scored]
    if len(set(y_true)) < 2:
        return [], None
    fpr, tpr, thresholds = roc_curve(y_true, y_scores)
    roc_points: List[Dict[str, float]] = []
    for f, t, th in zip(fpr, tpr, thresholds):
        if not (math.isfinite(f) and math.isfinite(t)):
            continue
        thr_val: Optional[float] = th if math.isfinite(th) else None
        roc_points.append({"fpr": float(f), "tpr": float(t), "threshold": thr_val})
    try:
        auc = round(roc_auc_score(y_true, y_scores), 3)
    except Exception:
        auc = None
    return roc_points, auc


def _compute_binary_metrics(
    cases: Sequence[Dict[str, object]],
    threshold: float,
) -> Dict[str, Optional[float]]:
    """Compute binary classification metrics using scikit-learn."""
    y_true = [bool(c["y_true"]) for c in cases]
    y_pred = [bool(c["y_pred"]) for c in cases]
    if not y_true:
        return {}

    cm = confusion_matrix(y_true, y_pred, labels=[False, True])
    tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    accuracy = accuracy_score(y_true, y_pred)
    balanced_acc = balanced_accuracy_score(y_true, y_pred)
    specificity = _safe_div(tn, tn + fp)
    npv = _safe_div(tn, tn + fn)
    kappa = cohen_kappa_score(y_true, y_pred) if len(set(y_true)) > 1 else 1.0
    weighted_kappa = cohen_kappa_score(y_true, y_pred, weights="quadratic") if len(set(y_true)) > 1 else 1.0

    def _round(val: Optional[float]) -> Optional[float]:
        return round(val, 3) if val is not None else None

    return {
        "support": len(y_true),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "precision": _round(precision),
        "recall": _round(recall),
        "sensitivity": _round(recall),
        "specificity": _round(specificity),
        "ppv": _round(precision),
        "npv": _round(npv),
        "f1": _round(f1),
        "accuracy": _round(accuracy),
        "balanced_accuracy": _round(balanced_acc),
        "kappa": _round(kappa),
        "weighted_kappa": _round(weighted_kappa),
        "threshold": threshold,
    }


def _build_binary_with_ci(
    cases: Sequence[Dict[str, object]],
    threshold: float,
    bootstrap_samples: int,
) -> Tuple[
    Dict[str, Optional[float]],
    Dict[str, Tuple[Optional[float], Optional[float]]],
    Optional[float],
    Optional[Tuple[Optional[float], Optional[float]]],
    List[Dict[str, float]],
    int,
    bool,
    bool,
]:
    """Compute binary metrics and bootstrap confidence intervals."""
    if not cases:
        return {}, {}, None, None, [], 0, False, False

    point_metrics = _compute_binary_metrics(cases, threshold)
    roc_points, auc = _compute_roc(cases)

    metric_samples: Dict[str, List[float]] = {k: [] for k in ("precision", "recall", "specificity", "ppv", "npv", "f1", "accuracy", "balanced_accuracy", "kappa", "weighted_kappa")}
    auc_samples: List[float] = []

    ci_computed = False
    if len(cases) >= 20:
        ci_computed = True
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
    if ci_computed:
        for key, values in metric_samples.items():
            ci_map[key] = _bootstrap_ci(values)
        # aliases for display consistency
        ci_map["sensitivity"] = ci_map.get("recall")
    auc_ci = _bootstrap_ci(auc_samples) if ci_computed and auc_samples else (None, None)

    roc_available = bool(roc_points)

    return point_metrics, ci_map, auc, auc_ci, roc_points, len(cases), ci_computed, roc_available


@bp.route("/model-performance", methods=["GET"])
@roles_required("admin", "local_admin", "data_manager", "analytics_viewer")
def model_performance() -> str:
    """Show AI model performance against human reference grades using mvw_grading_data_all."""
    if not _ensure_sklearn():
        return render_template(
            "analytics/model_performance.html",
            diseases=[],
            ai_models=[],
            selected_disease_id=None,
            selected_model_id=None,
            selected_disease_name=None,
            selected_model_name=None,
            selected_model_version=None,
            performance=None,
            error_message="scikit-learn is required for this page. Please install scikit-learn in the environment.",
            labels_for_disease=[],
            reference_source="consensus",
            positive_class=None,
            threshold=0.5,
            bootstrap_samples=2000,
            lab_units=[],
            selected_lab_units=[],
            upload_type=None,
            cameras=[],
            selected_camera_id=None,
            roc_points_json="[]",
            class_map_json="{}",
        )
    disease_id = request.args.get("disease_id", type=int)
    ai_model_id = request.args.get("ai_model_id", type=int)
    selected_lab_units = request.args.getlist("lab_unit_id", type=int)
    reference_source = request.args.get("reference_source", default="consensus")
    threshold = request.args.get("threshold", default=0.5, type=float)
    bootstrap_samples = request.args.get("bootstrap_samples", default=2000, type=int)
    upload_type = (request.args.get("upload_type") or "").strip().lower() or None
    camera_id = request.args.get("camera_id", type=int)
    class_map_raw = request.args.get("class_map", default="") or ""
    class_map = _parse_class_map(class_map_raw)
    positive_class = request.args.get("positive_class") or None

    performance: Optional[ModelPerformance] = None
    selected_disease: Optional[Disease] = None
    selected_model: Optional[AIModel] = None
    error_message: Optional[str] = None
    labels_for_disease: List[str] = []
    class_definitions: Dict[str, List[str]] = {}
    lab_units_payload: List[Dict[str, object]] = []
    cameras_payload: List[Dict[str, object]] = []
    diseases_payload: List[Dict[str, object]] = []
    ai_models_payload: List[Dict[str, object]] = []
    selected_disease_name: Optional[str] = None
    selected_model_name: Optional[str] = None
    selected_model_version: Optional[str] = None

    download = request.args.get("download") == "xlsx"

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

        # Lab unit options respecting hospital access
        lu_query = db.query(LabUnit).order_by(LabUnit.name)
        # Apply hospital scoping for analytics context
        lu_query = apply_scoping(lu_query, LabUnit, current_user, "analytics")
        lab_units = lu_query.all()
        user_lab_unit_ids = [lu.id for lu in lab_units]
        lab_units_payload = [{"id": lu.id, "name": lu.name} for lu in lab_units]

        if disease_id and ai_model_id:
            class_definitions, label_to_class, positive_class, labels_for_disease, map_error = _resolve_class_mapping(
                db,
                disease_id,
                class_map,
                positive_class,
            )
            if map_error:
                error_message = map_error
            class_names = list(class_definitions.keys())

            if not error_message:
                cache_key: Optional[str] = None
                if not download:
                    cache_key = _build_performance_cache_key(
                        disease_id=disease_id,
                        ai_model_id=ai_model_id,
                        reference_source=reference_source,
                        upload_type=upload_type,
                        camera_id=camera_id,
                        class_definitions=class_definitions,
                        positive_class=positive_class,
                        threshold=threshold,
                        bootstrap_samples=bootstrap_samples,
                        selected_lab_units=selected_lab_units,
                        allowed_lab_units=user_lab_unit_ids or [],
                    )
                    cached_performance = cache.get(cache_key) if cache_key else None
                    if cached_performance:
                        performance = cached_performance
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
                            positive_class=positive_class,
                            threshold=threshold,
                            bootstrap_samples=bootstrap_samples,
                            lab_units=lab_units_payload,
                            selected_lab_units=selected_lab_units,
                            upload_type=upload_type,
                            cameras=cameras_payload,
                            selected_camera_id=camera_id,
                            roc_points_json=json.dumps(performance.roc_points) if performance and performance.roc_points else "[]",
                            class_map_json=json.dumps(class_definitions),
                        )
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
                    # Only allow lab units that the user actually has access to
                    requested = set(selected_lab_units) & set(user_lab_unit_ids)
                    if requested:
                        sql_parts.append("AND lab_unit_id = ANY(:selected_lab_unit_ids)")
                        params["selected_lab_unit_ids"] = list(requested)
                    else:
                        sql_parts.append("AND 1=0")
                elif user_lab_unit_ids:
                    # Default: restrict to ALL lab units the user has access to
                    sql_parts.append("AND lab_unit_id = ANY(:allowed_lab_unit_ids)")
                    params["allowed_lab_unit_ids"] = user_lab_unit_ids
                elif not current_user.is_master_admin:
                    # No lab units and not master admin = no access
                    sql_parts.append("AND 1=0")

                sql_parts.append("ORDER BY task_created_at DESC, grade_created_at DESC")
                query = text("\n".join(sql_parts))

                rows = db.execute(query, params).mappings().all()

                # Organize by task_id
                tasks: Dict[int, Dict[str, object]] = {}
                for row in rows:
                    task_id = row["task_id"]
                    if task_id not in tasks:
                        tasks[task_id] = {
                            "task_id": task_id,
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
                analyzed_rows: List[Dict[str, object]] = []
                mismatches: List[Dict[str, object]] = []
                fp_count = 0
                fn_count = 0

                for _key, task_entries in grouped.items():
                    # Choose latest task by task_created_at
                    task_entries.sort(
                        key=lambda item: item[1]["task_created_at"] or item[1]["ai_grades"][0]["created_at"],
                        reverse=True,
                    )
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

                    # Map to classes; drop if not assigned
                    ref_class = label_to_class.get(ref_label)
                    if not ref_class:
                        continue

                    # Latest AI grade for the task
                    ai_grades = sorted(data["ai_grades"], key=lambda g: g["created_at"] or 0, reverse=True)
                    ai_grade = ai_grades[0]
                    pred_class = label_to_class.get(ai_grade["label"])
                    ai_score = _parse_ai_probability(ai_grade.get("comment"))

                    if not pred_class:
                        continue

                    pairs.append((ref_class, pred_class))

                    if positive_class:
                        is_positive_true = ref_class == positive_class
                        score_raw = ai_score
                        if score_raw is not None:
                            positive_score = score_raw if pred_class == positive_class else 1 - score_raw
                            predicted_positive = positive_score >= threshold
                        else:
                            positive_score = None
                            predicted_positive = pred_class == positive_class

                        cases.append(
                            {
                                "y_true": is_positive_true,
                                "y_pred": predicted_positive,
                                "score": positive_score,
                                "reference": ref_class,
                                "predicted": pred_class,
                            }
                        )

                    analyzed_rows.append(
                        {
                            "task_id": data.get("task_id"),
                            "image_uuid": data.get("image_uuid"),
                            "disease": data.get("disease_name"),
                            "reference_label": ref_label,
                            "reference_class": ref_class,
                            "predicted_label": ai_grade["label"],
                            "predicted_class": pred_class,
                            "ai_probability": ai_score,
                            "lab_unit": data.get("lab_unit_name"),
                            "camera_id": data.get("camera_id"),
                            "hospital": data.get("hospital_name"),
                        }
                    )
                    if ref_class != pred_class:
                        if positive_class:
                            if ref_class != positive_class and pred_class == positive_class:
                                fp_count += 1
                            if ref_class == positive_class and pred_class != positive_class:
                                fn_count += 1
                        mismatches.append(
                            {
                                "task_id": data.get("task_id"),
                                "image_uuid": data.get("image_uuid"),
                                "reference_class": ref_class,
                                "reference_label": ref_label,
                                "predicted_class": pred_class,
                                "predicted_label": ai_grade["label"],
                                "ai_probability": ai_score,
                                "lab_unit": data.get("lab_unit_name"),
                                "camera_id": data.get("camera_id"),
                                "hospital": data.get("hospital_name"),
                            }
                        )

                if pairs:
                    total = len(pairs)
                    # Build class list (respect user-defined order)
                    label_order = class_names
                    all_labels: List[str] = list(label_order)
                    for actual, predicted in pairs:
                        if actual not in all_labels:
                            all_labels.append(actual)
                        if predicted not in all_labels:
                            all_labels.append(predicted)

                    cross_tab = _build_cross_tab(all_labels, pairs)
                    y_true = [a for a, _ in pairs]
                    y_pred = [p for _, p in pairs]
                    cm = confusion_matrix(y_true, y_pred, labels=all_labels)
                    cm_list = cm.tolist() if cm is not None else None
                    row_totals = [int(sum(row)) for row in cm_list] if cm_list else None
                    col_totals = [int(cm[:, idx].sum()) for idx in range(len(all_labels))] if cm is not None else None
                    percent_matrix = None
                    if cm_list and total:
                        percent_matrix = [
                            [round((cell / total) * 100, 1) if total else 0.0 for cell in row]
                            for row in cm_list
                        ]

                    label_metrics: List[LabelMetrics] = []
                    correct = int(cm.trace())
                    is_multi_class = len(all_labels) > 2

                    for idx, lbl in enumerate(all_labels):
                        tp = int(cm[idx, idx])
                        fp = int(cm[:, idx].sum() - tp)
                        fn = int(cm[idx, :].sum() - tp)
                        tn = int(cm.sum() - tp - fp - fn)
                        precision = _safe_div(tp, tp + fp)
                        recall = _safe_div(tp, tp + fn)
                        specificity = _safe_div(tn, tn + fp)
                        npv = _safe_div(tn, tn + fn)
                        f1 = _safe_div(2 * tp, 2 * tp + fp + fn)

                        def _r(val: Optional[float]) -> Optional[float]:
                            return round(val, 3) if val is not None else None

                        label_metrics.append(
                            LabelMetrics(
                                label=lbl,
                                support=tp + fn,
                                tp=tp,
                                fp=fp,
                                tn=tn,
                                fn=fn,
                                precision=_r(precision),
                                recall=_r(recall),
                                sensitivity=_r(recall),
                                specificity=_r(specificity),
                                ppv=_r(precision),
                                npv=_r(npv),
                                f1=_r(f1),
                            )
                        )

                    prec_macro, rec_macro, f1_macro, _ = precision_recall_fscore_support(
                        y_true, y_pred, labels=all_labels, average="macro", zero_division=0
                    )
                    kappa_weighted = _cohens_kappa(pairs, all_labels)
                    try:
                        kappa_weighted = round(cohen_kappa_score(y_true, y_pred, labels=all_labels, weights="quadratic"), 3)
                    except Exception:
                        kappa_weighted = None
                    try:
                        balanced_agreement = round(balanced_accuracy_score(y_true, y_pred), 3)
                    except Exception:
                        balanced_agreement = None

                    overall = {
                        "accuracy": round(accuracy_score(y_true, y_pred), 3) if total else None,
                        "balanced_accuracy": balanced_agreement,
                        "macro_precision": round(prec_macro, 3) if total else None,
                        "macro_recall": round(rec_macro, 3) if total else None,
                        "macro_specificity": round(
                            sum(m.specificity for m in label_metrics if m.specificity is not None) / len(
                                [m for m in label_metrics if m.specificity is not None]
                            ), 3
                        ) if any(m.specificity is not None for m in label_metrics) else None,
                        "macro_f1": round(f1_macro, 3) if total else None,
                        "cohens_kappa": _cohens_kappa(pairs, all_labels),
                        "weighted_kappa": kappa_weighted,
                    }

                    binary_metrics = None
                    binary_ci = None
                    auc = None
                    auc_ci = None
                    roc_points: List[Dict[str, float]] = []
                    binary_sample_size = 0
                    binary_ci_computed = False
                    roc_available = False

                    if positive_class:
                        (
                            point_metrics,
                            ci_map,
                            auc_val,
                            auc_ci_val,
                            roc_pts,
                            sample_size,
                            ci_ok,
                            roc_ok,
                        ) = _build_binary_with_ci(
                            cases,
                            threshold,
                            bootstrap_samples,
                        )
                        binary_metrics = point_metrics if point_metrics else None
                        binary_ci = ci_map if ci_map else None
                        auc = auc_val
                        auc_ci = auc_ci_val
                        roc_points = roc_pts
                        binary_sample_size = sample_size
                        binary_ci_computed = ci_ok
                        roc_available = roc_ok
                    else:
                        # No positives selected; still compute ROC if scores exist? Skip.
                        binary_sample_size = 0
                        binary_ci_computed = False
                        roc_available = False

                    performance = ModelPerformance(
                        labels=all_labels,
                        class_definitions=class_definitions,
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
                        binary_sample_size=binary_sample_size,
                        binary_ci_computed=binary_ci_computed,
                        roc_available=roc_available,
                        confusion_matrix=cm_list,
                        confusion_image_base64=_render_confusion_image(cm_list, all_labels) if cm_list else None,
                        row_totals=row_totals,
                        col_totals=col_totals,
                        percent_matrix=percent_matrix,
                        mismatches=mismatches,
                        fp_count=fp_count,
                        fn_count=fn_count,
                        multi_class=is_multi_class,
                    )

                    if cache_key:
                        try:
                            cache.set(cache_key, performance, timeout=60 * 60)
                        except Exception:
                            # Fail open; caching should not break response
                            pass

                    if download and analyzed_rows:
                        buf = _render_excel(analyzed_rows)
                        if buf:
                            return send_file(
                                buf,
                                as_attachment=True,
                                download_name="model_performance.xlsx",
                                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        positive_class=positive_class,
        threshold=threshold,
        bootstrap_samples=bootstrap_samples,
        lab_units=lab_units_payload,
        selected_lab_units=selected_lab_units,
        upload_type=upload_type,
        cameras=cameras_payload,
        selected_camera_id=camera_id,
        roc_points_json=json.dumps(performance.roc_points) if performance and performance.roc_points else "[]",
        class_map_json=json.dumps(class_definitions),
    )


@bp.route("/model-performance/threshold-explorer", methods=["POST"])
@roles_required("admin", "local_admin", "data_manager")
def threshold_explorer() -> object:
    """Compute binary metrics across a threshold range (max 5 points) for the current filters."""
    if not _ensure_sklearn():
        return jsonify({"error": "scikit-learn is required for this analysis."}), 400

    payload = request.get_json(silent=True) or {}
    disease_id = payload.get("disease_id")
    ai_model_id = payload.get("ai_model_id")
    reference_source = payload.get("reference_source", "consensus") or "consensus"
    upload_type = (payload.get("upload_type") or "").strip().lower() or None
    camera_id_raw = payload.get("camera_id")
    class_map_raw = payload.get("class_map") or {}
    positive_class = payload.get("positive_class") or None
    selected_lab_units = payload.get("lab_unit_id") or []

    try:
        threshold_min = float(payload.get("threshold_min", 0.0))
        threshold_max = float(payload.get("threshold_max", 1.0))
        threshold_delta = float(payload.get("threshold_delta", 0.1))
    except (TypeError, ValueError):
        return jsonify({"error": "Threshold inputs must be numeric."}), 400

    thresholds, range_error = _build_threshold_range(threshold_min, threshold_max, threshold_delta, max_points=25)
    if range_error:
        return jsonify({"error": range_error}), 400

    try:
        disease_id = int(disease_id)
        ai_model_id = int(ai_model_id)
        camera_id = int(camera_id_raw) if camera_id_raw not in (None, "") else None
    except (TypeError, ValueError):
        disease_id = None
        ai_model_id = None
        camera_id = None

    if disease_id is None or ai_model_id is None:
        return jsonify({"error": "disease_id and ai_model_id are required."}), 400

    class_map: Dict[str, List[str]] = {}
    if isinstance(positive_class, str):
        positive_class = positive_class.strip() or None
    if isinstance(class_map_raw, str):
        class_map = _parse_class_map(class_map_raw)
    elif isinstance(class_map_raw, dict):
        for k, v in class_map_raw.items():
            if isinstance(k, str) and isinstance(v, list):
                class_map[k] = [s for s in v if isinstance(s, str)]

    # Normalize lab units list
    if isinstance(selected_lab_units, list):
        selected_lab_units = [int(v) for v in selected_lab_units if isinstance(v, (int, str)) and str(v).isdigit()]
    else:
        selected_lab_units = []

    with get_db_session() as db:
        # Validate class mapping and positive class
        class_definitions, label_to_class, positive_class, labels_for_disease, map_error = _resolve_class_mapping(
            db, disease_id, class_map, positive_class
        )
        if map_error:
            return jsonify({"error": map_error}), 400
        if not positive_class:
            return jsonify({"error": "Positive class could not be resolved."}), 400

        user_lab_unit_ids = list(get_user_lab_unit_ids_no_admin_override(current_user.id) or [])

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

        if selected_lab_units:
            requested = set(selected_lab_units) & set(user_lab_unit_ids or [])
            if requested:
                placeholders = []
                for idx, val in enumerate(requested):
                    key = f"lab_unit_id_{idx}"
                    params[key] = val
                    placeholders.append(f":{key}")
                sql_parts.append(f"AND lab_unit_id IN ({', '.join(placeholders)})")
            else:
                sql_parts.append("AND 1=0")
        elif user_lab_unit_ids:
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

        # Organize AI and reference grades per task/image
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

            if row["grade_role_slot"] == "ai" and row["ai_model_id"] == ai_model_id:
                tasks[task_id]["ai_grades"].append(
                    {
                        "label": row["grade_name"],
                        "comment": row["grade_comment"],
                        "created_at": row["grade_created_at"],
                    }
                )

            if row["grade_role_slot"] in {"resident", "resident2", "arbitrator"} and row["grade_name"]:
                current = tasks[task_id]["ref_grades"].get(row["grade_role_slot"])
                if current is None or (row["grade_created_at"] and row["grade_created_at"] > current["created_at"]):
                    tasks[task_id]["ref_grades"][row["grade_role_slot"]] = {
                        "label": row["grade_name"],
                        "created_at": row["grade_created_at"],
                    }

        tasks = {tid: data for tid, data in tasks.items() if data["ai_grades"]}

        grouped: Dict[Tuple[str, int], List[Tuple[int, Dict[str, object]]]] = {}
        for tid, data in tasks.items():
            key = (data["image_uuid"], data["disease_id"])
            grouped.setdefault(key, []).append((tid, data))

        cases_raw: List[Dict[str, object]] = []
        probabilities_present = False

        for _key, task_entries in grouped.items():
            task_entries.sort(
                key=lambda item: item[1]["task_created_at"] or item[1]["ai_grades"][0]["created_at"],
                reverse=True,
            )
            _, data = task_entries[0]

            ref_label = None
            if reference_source == "consensus":
                ref_label = data["consensus_label"]
            else:
                ref_obj = data["ref_grades"].get(reference_source)
                ref_label = ref_obj["label"] if ref_obj else None

            if not ref_label:
                continue

            ref_class = label_to_class.get(ref_label)
            if not ref_class:
                continue

            ai_grades = sorted(data["ai_grades"], key=lambda g: g["created_at"] or 0, reverse=True)
            ai_grade = ai_grades[0]
            pred_class = label_to_class.get(ai_grade["label"])
            ai_score = _parse_ai_probability(ai_grade.get("comment"))

            if not pred_class:
                continue

            is_positive_true = ref_class == positive_class
            positive_score: Optional[float] = None
            if ai_score is not None:
                positive_score = ai_score if pred_class == positive_class else 1 - ai_score
                probabilities_present = True

            cases_raw.append(
                {
                    "y_true": is_positive_true,
                    "predicted_class": pred_class,
                    "positive_score": positive_score,
                }
            )

        if not cases_raw:
            return jsonify({"error": "No cases available for the selected filters."}), 400

        sample_size = len(cases_raw)
        cache_key = _build_threshold_cache_key(
            disease_id=disease_id,
            ai_model_id=ai_model_id,
            reference_source=reference_source,
            upload_type=upload_type,
            camera_id=camera_id,
            class_definitions=class_definitions,
            positive_class=positive_class,
            lab_units=selected_lab_units or [],
            thresholds=thresholds,
            sample_size=sample_size,
        )

        cached = cache.get(cache_key) if cache else None
        if cached:
            return jsonify(cached)

        results: List[Dict[str, object]] = []
        for thr in thresholds:
            threshold_cases = _apply_threshold_to_cases(cases_raw, positive_class, thr)
            metrics = _compute_binary_metrics(threshold_cases, thr) if threshold_cases else {}
            results.append(
                {
                    "threshold": thr,
                    "sensitivity": metrics.get("sensitivity") if metrics else None,
                    "specificity": metrics.get("specificity") if metrics else None,
                    "ppv": metrics.get("ppv") if metrics else None,
                    "npv": metrics.get("npv") if metrics else None,
                    "f1": metrics.get("f1") if metrics else None,
                    "accuracy": metrics.get("accuracy") if metrics else None,
                    "balanced_accuracy": metrics.get("balanced_accuracy") if metrics else None,
                    "kappa": metrics.get("kappa") if metrics else None,
                    "weighted_kappa": metrics.get("weighted_kappa") if metrics else None,
                    "tp": metrics.get("tp") if metrics else None,
                    "fp": metrics.get("fp") if metrics else None,
                    "tn": metrics.get("tn") if metrics else None,
                    "fn": metrics.get("fn") if metrics else None,
                    "support": metrics.get("support") if metrics else None,
                }
            )

        roc_cases = [{"score": c["positive_score"], "y_true": c["y_true"]} for c in cases_raw if c.get("positive_score") is not None]
        _, auc_val = _compute_roc(roc_cases) if roc_cases else ([], None)

        response_payload = {
            "thresholds": results,
            "auc": auc_val,
            "sample_size": sample_size,
            "positive_class": positive_class,
            "probabilities_present": probabilities_present,
        }

        if cache:
            cache.set(cache_key, response_payload, timeout=60 * 60)  # 1 hour

        return jsonify(response_payload)
