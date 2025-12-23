from datetime import datetime

import pytz
import sqlalchemy as sa
from flask import jsonify, request, render_template
from flask_login import login_required

from auth.roles import roles_required
from db_transaction_manager import transaction_scope
from models import User, LoginAttempt, IpLock
from . import api_bp


@api_bp.route("/admin/users", methods=["GET"])
@login_required
@roles_required("admin", "data_manager")
def api_admin_users_activity():
    """Return paginated user activity for admin dashboards."""
    offset = request.args.get("offset", "0")
    limit = request.args.get("limit", "10")
    user_id = request.args.get("user_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    types_raw = request.args.get("types", "")

    try:
        offset_val = max(int(offset), 0)
    except ValueError:
        offset_val = 0

    try:
        limit_val = int(limit)
    except ValueError:
        limit_val = 10
    limit_val = max(1, min(limit_val, 100))

    user_id_val = None
    if user_id:
        try:
            user_id_val = int(user_id)
        except ValueError:
            return jsonify({"success": False, "error": "Invalid user_id"}), 400

    start_dt, end_dt = _parse_date_range(start_date, end_date)
    if start_date and start_dt is None:
        return jsonify({"success": False, "error": "Invalid start_date"}), 400
    if end_date and end_dt is None:
        return jsonify({"success": False, "error": "Invalid end_date"}), 400

    types = {t.strip() for t in types_raw.split(",") if t.strip()}
    if not types:
        types = {"user_created", "login_success", "login_failure", "ip_locked"}

    with transaction_scope() as db:
        union_query = _build_user_activity_query(types, user_id_val, start_dt, end_dt)
        subq = union_query.subquery()

        total = db.execute(sa.select(sa.func.count()).select_from(subq)).scalar_one() or 0
        rows = db.execute(
            sa.select(subq)
            .order_by(sa.desc(subq.c.event_time).nullslast())
            .offset(offset_val)
            .limit(limit_val)
        ).all()

    items = [
        {
            "event_type": row.event_type,
            "username": row.username,
            "ip_address": row.ip_address,
            "event_time": row.event_time,
            "user_id": row.user_id,
        }
        for row in rows
    ]

    if request.headers.get("HX-Request") or request.args.get("format") == "html":
        view = request.args.get("view", "login").strip() or "login"
        return render_template(
            "admin/partials/user_activity_table.html",
            items=items,
            offset=offset_val,
            limit=limit_val,
            total=total,
            view=view,
        )

    items_payload = [
        {
            "event_type": item["event_type"],
            "username": item["username"],
            "ip_address": item["ip_address"],
            "event_time": item["event_time"].isoformat() if item["event_time"] else None,
            "user_id": item["user_id"],
        }
        for item in items
    ]

    return jsonify({
        "success": True,
        "data": {
            "items": items_payload,
            "offset": offset_val,
            "limit": limit_val,
            "total": total,
        }
    })


def _parse_date_range(start_date: str | None, end_date: str | None):
    """Parse ISO date or datetime strings into UTC-aware datetime range."""
    def _parse(value: str, is_end: bool):
        if not value:
            return None
        value = value.strip()
        try:
            if "T" in value or ":" in value:
                dt = datetime.fromisoformat(value)
            else:
                dt = datetime.strptime(value, "%Y-%m-%d")
                if is_end:
                    dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt
        except ValueError:
            return None

    return _parse(start_date, False), _parse(end_date, True)


def _build_user_activity_query(types: set[str], user_id: int | None, start_dt: datetime | None, end_dt: datetime | None):
    """Build a UNION query of user activity events."""
    selects = []

    if "user_created" in types:
        created_q = sa.select(
            sa.literal("user_created").label("event_type"),
            User.username.label("username"),
            sa.literal(None).label("ip_address"),
            User.created_at.label("event_time"),
            User.id.label("user_id"),
        )
        if user_id is not None:
            created_q = created_q.where(User.id == user_id)
        if start_dt:
            created_q = created_q.where(User.created_at >= start_dt)
        if end_dt:
            created_q = created_q.where(User.created_at <= end_dt)
        selects.append(created_q)

    if "login_success" in types or "login_failure" in types:
        user_alias = sa.orm.aliased(User)
        join_condition = sa.func.lower(user_alias.username) == sa.func.lower(LoginAttempt.username_input)

        if "login_success" in types:
            success_q = sa.select(
                sa.literal("login_success").label("event_type"),
                LoginAttempt.username_input.label("username"),
                LoginAttempt.ip_address.label("ip_address"),
                LoginAttempt.created_at.label("event_time"),
                user_alias.id.label("user_id"),
            ).select_from(LoginAttempt).outerjoin(user_alias, join_condition).where(LoginAttempt.success.is_(True))
            if user_id is not None:
                success_q = success_q.where(user_alias.id == user_id)
            if start_dt:
                success_q = success_q.where(LoginAttempt.created_at >= start_dt)
            if end_dt:
                success_q = success_q.where(LoginAttempt.created_at <= end_dt)
            selects.append(success_q)

        if "login_failure" in types:
            failure_q = sa.select(
                sa.literal("login_failure").label("event_type"),
                LoginAttempt.username_input.label("username"),
                LoginAttempt.ip_address.label("ip_address"),
                LoginAttempt.created_at.label("event_time"),
                user_alias.id.label("user_id"),
            ).select_from(LoginAttempt).outerjoin(user_alias, join_condition).where(LoginAttempt.success.is_(False))
            if user_id is not None:
                failure_q = failure_q.where(user_alias.id == user_id)
            if start_dt:
                failure_q = failure_q.where(LoginAttempt.created_at >= start_dt)
            if end_dt:
                failure_q = failure_q.where(LoginAttempt.created_at <= end_dt)
            selects.append(failure_q)

    if "ip_locked" in types and user_id is None:
        ip_lock_q = sa.select(
            sa.literal("ip_locked").label("event_type"),
            sa.literal(None).label("username"),
            IpLock.ip_address.label("ip_address"),
            IpLock.locked_until.label("event_time"),
            sa.literal(None).label("user_id"),
        )
        if start_dt:
            ip_lock_q = ip_lock_q.where(IpLock.locked_until >= start_dt)
        if end_dt:
            ip_lock_q = ip_lock_q.where(IpLock.locked_until <= end_dt)
        selects.append(ip_lock_q)

    if not selects:
        return sa.select(
            sa.literal("none").label("event_type"),
            sa.literal(None).label("username"),
            sa.literal(None).label("ip_address"),
            sa.literal(None).label("event_time"),
            sa.literal(None).label("user_id"),
        ).where(sa.literal(False))

    return sa.union_all(*selects)
