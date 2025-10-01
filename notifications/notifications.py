from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload
import logging
from datetime import datetime

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from utils.notifications import (
    MAX_MESSAGE_LENGTH,
    MAX_TITLE_LENGTH,
    get_user_notifications,
    mark_all_user_notifications_as_read,
    mark_notification_as_read,
    prepare_notification_payload,
    send_notification_to_admins,
    send_notification_to_user,
    send_system_notification,
)
from models import LabUnit, Notification, NotificationRead, NotificationType, User


def register_routes(bp):
    """Register notification routes with the blueprint."""
    bp.add_url_rule("/", view_func=notifications, methods=["GET"])
    bp.add_url_rule("/<int:notification_id>/mark_read", view_func=mark_notification_read, methods=["POST"])
    bp.add_url_rule("/mark_all_read", view_func=mark_all_notifications_read, methods=["POST"])
    bp.add_url_rule("/compose", view_func=compose_notification, methods=["GET", "POST"])
    bp.add_url_rule("/broadcast", view_func=broadcast_notification, methods=["GET", "POST"])
    bp.add_url_rule("/system", view_func=system_notification, methods=["GET", "POST"])


def _get_peer_users(db, user_id: int) -> list[User]:
    """Return active users sharing at least one lab unit with the given user."""
    current_user_obj = (
        db.query(User)
        .options(selectinload(User.lab_units))
        .filter(User.id == user_id)
        .one_or_none()
    )
    if current_user_obj is None:
        return []

    lab_unit_ids = {lu.id for lu in current_user_obj.lab_units or []}
    if not lab_unit_ids:
        return []

    peers = (
        db.query(User)
        .join(User.lab_units)
        .filter(
            User.is_active.is_(True),
            User.id != user_id,
            LabUnit.id.in_(lab_unit_ids),
        )
        .distinct()
        .order_by(User.full_name, User.username)
        .all()
    )
    return peers


@login_required
def notifications():
    """Display user's notifications with pagination."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        notification_type = request.args.get('type', None)
        # Correct way to get boolean from URL parameters
        unread_only = request.args.get('unread', default=False, type=lambda x: x in ['1', 'True', 'true', 'on'])
        
        # Limit per_page to reasonable values
        per_page = min(max(per_page, 1), 100)  # Between 1 and 100 items per page
        
        with get_db_session() as db:
            # Start building the query
            query = (
                db.query(Notification)
                .options(
                    selectinload(Notification.sender),
                    selectinload(Notification.recipient),
                )
                .filter(
            or_(
                Notification.recipient_user_id == current_user.id,
                Notification.sender_user_id == current_user.id,
                Notification.recipient_user_id.is_(None),
                )
            )
            )
            
            # Apply filters
            if notification_type:
                query = query.filter(Notification.notification_type == notification_type)
            
            if unread_only:
                query = query.filter(
                    Notification.recipient_user_id == current_user.id,
                    Notification.is_read.is_(False)
                )
            
            # Order by creation date (newest first)
            query = query.order_by(Notification.created_at.desc())
            
            # Calculate pagination
            total = query.count()
            offset = (page - 1) * per_page
            notifications_list = query.offset(offset).limit(per_page).all()
            
            # Calculate pagination details
            pages = (total + per_page - 1) // per_page  # Ceiling division
            
            system_notification_ids = [n.id for n in notifications_list if n.recipient_user_id is None]
            system_read_ids: set[int] = set()
            if system_notification_ids:
                system_read_ids = set(
                    db.execute(
                        select(NotificationRead.notification_id).where(
                            NotificationRead.user_id == current_user.id,
                            NotificationRead.notification_id.in_(system_notification_ids),
                        )
                    ).scalars()
                )

            pagination = {
                'page': page,
                'pages': pages,
                'per_page': per_page,
                'total': total,
                'has_prev': page > 1,
                'has_next': page < pages,
                'prev_num': page - 1 if page > 1 else None,
                'next_num': page + 1 if page < pages else None
            }
            
            return render_template(
                "notifications/index.html",
                notifications=notifications_list,
                pagination=pagination,
                current_filters={'type': notification_type, 'unread_only': unread_only},
                system_read_ids=system_read_ids,
            )
    except Exception as e:
        current_app.logger.exception("Failed to load notifications: %s", e)
        flash("Failed to load notifications.", "danger")
        return redirect(url_for("notifications.notifications"))


@login_required
def mark_notification_read(notification_id):
    """Mark a specific notification as read."""
    try:
        if mark_notification_as_read(notification_id, current_user.id):
            flash("Notification marked as read.", "success")
        else:
            flash("Unable to mark this notification as read.", "warning")
        return redirect(url_for("notifications.notifications"))
    except Exception as e:
        current_app.logger.exception("Failed to mark notification as read: %s", e)
        flash("Failed to mark notification as read.", "danger")
        return redirect(url_for("notifications.notifications"))


@login_required
def mark_all_notifications_read():
    """Mark all user's notifications as read."""
    try:
        mark_all_user_notifications_as_read(current_user.id)
        flash("All notifications marked as read.", "success")
        return redirect(url_for("notifications.notifications"))
    except Exception as e:
        current_app.logger.exception("Failed to mark all notifications as read: %s", e)
        flash("Failed to mark all notifications as read.", "danger")
        return redirect(url_for("notifications.notifications"))


@login_required
def compose_notification():
    """Allow the current user to send a notification to admins or lab peers."""
    peer_options: list[dict[str, str | int]] = []
    try:
        with get_db_session() as db:
            peers = _get_peer_users(db, current_user.id)
            peer_options = [
                {
                    "id": peer.id,
                    "label": peer.full_name or peer.username,
                    "username": peer.username,
                }
                for peer in peers
            ]

        if request.method == "POST":
            recipient_type = (request.form.get("recipient_type") or "").strip()
            title = (request.form.get("title") or "").strip()
            message = (request.form.get("message") or "").strip()
            peer_id_raw = request.form.get("peer_user_id")

            if not title or not message:
                raise ValueError("Title and message are required.")

            if recipient_type == "admins":
                send_notification_to_admins(
                    title,
                    message,
                    NotificationType.INFO,
                    sender_user_id=current_user.id,
                )
                flash("Notification sent to admins.", "success")
                return redirect(url_for("notifications.notifications"))

            if recipient_type == "user":
                try:
                    peer_user_id = int(peer_id_raw or "0")
                except ValueError as exc:  # pragma: no cover - defensive
                    raise ValueError("Invalid recipient selected.") from exc

                allowed_peer_ids = {option["id"] for option in peer_options}
                if peer_user_id not in allowed_peer_ids:
                    raise ValueError("You can only message users mapped to your lab units.")

                send_notification_to_user(
                    peer_user_id,
                    title,
                    message,
                    NotificationType.INFO,
                    sender_user_id=current_user.id,
                )
                flash("Notification sent successfully.", "success")
                return redirect(url_for("notifications.notifications"))

            raise ValueError("Select a valid recipient option.")
    except ValueError as validation_error:
        flash(str(validation_error), "danger")
    except Exception as exc:  # pragma: no cover - unexpected
        current_app.logger.exception("Failed to send notification: %s", exc)
        flash("Failed to send notification.", "danger")

    return render_template(
        "notifications/compose.html",
        peer_options=peer_options,
        max_title_length=MAX_TITLE_LENGTH,
        max_message_length=MAX_MESSAGE_LENGTH,
    )


@roles_required('admin')
def broadcast_notification():
    """Display form to send broadcast notifications to all users."""
    if request.method == 'POST':
        title = request.form.get('title', '')
        message = request.form.get('message', '')
        notification_type = request.form.get('notification_type', 'info')
        try:
            cleaned_title, cleaned_message = prepare_notification_payload(title, message)
            notif_type_value = (
                notification_type
                if notification_type in {t.value for t in NotificationType}
                else NotificationType.INFO.value
            )
            with get_db_session() as db:
                users = db.query(User).filter(User.is_active.is_(True)).all()

                for user in users:
                    db.add(
                        Notification(
                            title=cleaned_title,
                            message=cleaned_message,
                            notification_type=notif_type_value,
                            recipient_user_id=user.id,
                            sender_user_id=current_user.id,
                        )
                    )

                db.commit()
                flash(f"Broadcast notification sent to {len(users)} users.", "success")
                return redirect(url_for("notifications.broadcast_notification"))
        except ValueError as ve:
            flash(str(ve), "danger")
        except Exception as e:
            current_app.logger.exception("Failed to send broadcast notification: %s", e)
            flash("Failed to send broadcast notification.", "danger")

    return render_template(
        "notifications/broadcast.html",
        max_title_length=MAX_TITLE_LENGTH,
        max_message_length=MAX_MESSAGE_LENGTH,
    )


@roles_required('admin')
def system_notification():
    """Display form to send system-wide notifications."""
    if request.method == 'POST':
        title = request.form.get('title', '')
        message = request.form.get('message', '')
        notification_type = request.form.get('notification_type', 'info')
        try:
            cleaned_title, cleaned_message = prepare_notification_payload(title, message)
            notif_enum = NotificationType(notification_type) if notification_type in {t.value for t in NotificationType} else NotificationType.INFO
            send_system_notification(
                cleaned_title,
                cleaned_message,
                notif_enum,
                sender_user_id=current_user.id,
            )
            flash("System notification sent successfully.", "success")
            return redirect(url_for("notifications.system_notification"))
        except ValueError as ve:
            flash(str(ve), "danger")
        except Exception as e:
            current_app.logger.exception("Failed to send system notification: %s", e)
            flash("Failed to send system notification.", "danger")

    return render_template(
        "notifications/system.html",
        max_title_length=MAX_TITLE_LENGTH,
        max_message_length=MAX_MESSAGE_LENGTH,
    )
