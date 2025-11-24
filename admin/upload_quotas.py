"""Admin routes for managing user upload quotas and usage."""

from __future__ import annotations

from typing import Any, Dict, List

from flask import flash, redirect, render_template, request, url_for
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from direct_uploads.upload import _get_int_setting
from models import User


def _resolve_default_quota(db_session) -> int | None:
    """Get the default lifetime quota (None means unlimited)."""
    quota = _get_int_setting(
        db_session,
        "DIRECT_UPLOAD_LIFETIME_QUOTA",
        "DIRECT_UPLOAD_LIFETIME_QUOTA",
        50,
    )
    if quota is None or quota <= 0:
        return None
    return quota


@roles_required("admin", "data_manager")
def list_upload_quotas():
    """Display user upload quotas, usage, and allow edits."""
    with get_db_session() as db:
        default_quota = _resolve_default_quota(db)

        users = (
            db.execute(
                select(User).options(
                    selectinload(User.roles),
                    selectinload(User.lab_units),
                ).order_by(User.username)
            )
            .scalars()
            .all()
        )

        rows: List[Dict[str, Any]] = []
        for user in users:
            effective_quota = (
                user.file_upload_quota
                if user.file_upload_quota and user.file_upload_quota > 0
                else default_quota
            )
            rows.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "file_upload_count": user.file_upload_count,
                    "file_upload_quota": user.file_upload_quota,
                    "effective_quota": effective_quota,
                    "remaining": None
                    if effective_quota is None
                    else max(effective_quota - user.file_upload_count, 0),
                }
            )

        return render_template(
            "admin/upload_quotas.html",
            users=rows,
            default_quota=default_quota,
        )


@roles_required("admin", "data_manager")
def update_upload_quota(user_id: int):
    """Update a user's quota and optionally reset/upload count."""
    new_quota_raw = request.form.get("file_upload_quota")
    new_count_raw = request.form.get("file_upload_count")

    def _parse_int(value: str | None, allow_empty=False):
        if value is None:
            return None
        value = value.strip()
        if allow_empty and value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    new_quota = _parse_int(new_quota_raw, allow_empty=True)
    new_count = _parse_int(new_count_raw, allow_empty=True)

    with get_db_session() as db:
        user = db.get(User, int(user_id))
        if not user:
            flash("User not found.", "danger")
            return redirect(url_for("admin.list_upload_quotas"), code=303)

        if new_quota is not None:
            if new_quota < 0:
                flash("Quota must be zero or a positive number.", "danger")
                return redirect(url_for("admin.list_upload_quotas"), code=303)
            user.file_upload_quota = new_quota

        if new_count is not None:
            if new_count < 0:
                flash("Upload count cannot be negative.", "danger")
                return redirect(url_for("admin.list_upload_quotas"), code=303)
            user.file_upload_count = new_count

        flash("Upload quota updated.", "success")
        return redirect(url_for("admin.list_upload_quotas"), code=303)


@roles_required("admin", "data_manager")
def upload_quota_redirect():
    """Backward-compatible redirect for singular path."""
    return redirect(url_for("admin.list_upload_quotas"), code=302)
