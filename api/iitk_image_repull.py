"""Admin API: queue the IITK image re-pull. See docs/API/iitk-image-repull/README.md."""
from __future__ import annotations

from datetime import date

from flask import jsonify, request
from flask_login import current_user

from auth.roles import roles_required
from utils.celery_helpers import enqueue_task
from utils.rate_limiter import rate_limit

from . import api_bp

MAX_BATCH_IMAGES = 200
MAX_BATCHES = 500


@api_bp.route("/admin/iitk/image-repull", methods=["POST"])
@roles_required("admin")
@rate_limit("10 per hour")
def queue_iitk_image_repull():
    """Queue the re-pull. JSON: ``limit_images`` (1-200), ``before`` (YYYY-MM-DD), ``batches`` (1-500), ``dry_run``."""
    payload = request.get_json(silent=True) or {}
    try:
        limit_images = int(payload.get("limit_images", 50))
        batches = int(payload.get("batches", 1))
        before = payload.get("before")
        if before:
            date.fromisoformat(str(before))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_request", "message": "limit_images and batches must be integers; before must be YYYY-MM-DD."}), 400
    if not 1 <= limit_images <= MAX_BATCH_IMAGES or not 1 <= batches <= MAX_BATCHES:
        return jsonify({"error": "invalid_request", "message": f"limit_images must be 1-{MAX_BATCH_IMAGES} and batches 1-{MAX_BATCHES}."}), 400
    task = enqueue_task(
        "celery_tasks.tasks.iitk_tasks.repull_iitk_images_task",
        limit_images=limit_images,
        before=str(before) if before else None,
        batches=batches,
        dry_run=bool(payload.get("dry_run", False)),
        user_id=current_user.id,
    )
    return jsonify({"queued": True, "task_id": getattr(task, "id", None)}), 202
