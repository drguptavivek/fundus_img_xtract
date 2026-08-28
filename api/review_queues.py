"""REST API for discrepancy-review queue creation."""
from __future__ import annotations

from flask import jsonify, request, url_for
from flask_login import current_user, login_required

from db_transaction_manager import transaction_scope
from review.queues import MAX_CSV_BYTES, ReviewQueueError, create_review_queue

from . import api_bp


@api_bp.route("/review/queues", methods=["POST"])
@login_required
def create_discrepancy_review_queue():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"success": False, "error": "A CSV file is required."}), 400
    content = upload.stream.read(MAX_CSV_BYTES + 1)
    try:
        with transaction_scope() as db:
            queue = create_review_queue(
                db,
                user=current_user,
                filename=upload.filename,
                content=content,
            )
            review_url = url_for(
                "review.discrepancy_review",
                review_queue=queue.token,
                disease_id=queue.disease_id,
            )
            return jsonify({
                "success": True,
                "data": {
                    "token": queue.token,
                    "disease_id": queue.disease_id,
                    "task_count": len(queue.task_ids),
                    "review_url": review_url,
                },
            }), 201
    except ReviewQueueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
