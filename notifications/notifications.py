from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import current_user, login_required
from sqlalchemy import and_, or_
import logging
from datetime import datetime

from auth.roles import roles_required
from db_transaction_manager import get_db_session
from utils.notifications import get_user_notifications, mark_notification_as_read, mark_all_user_notifications_as_read, send_system_notification, send_notification_to_admins
from models import Notification, User


def register_routes(bp):
    """Register notification routes with the blueprint."""
    bp.add_url_rule("/", view_func=notifications, methods=["GET"])
    bp.add_url_rule("/<int:notification_id>/mark_read", view_func=mark_notification_read, methods=["POST"])
    bp.add_url_rule("/mark_all_read", view_func=mark_all_notifications_read, methods=["POST"])
    bp.add_url_rule("/broadcast", view_func=broadcast_notification, methods=["GET", "POST"])
    bp.add_url_rule("/system", view_func=system_notification, methods=["GET", "POST"])


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
            query = db.query(Notification).filter(
                or_(
                    Notification.recipient_user_id == current_user.id,
                    Notification.recipient_user_id.is_(None)  # System-wide notifications
                )
            )
            
            # Apply filters
            if notification_type:
                query = query.filter(Notification.notification_type == notification_type)
            
            if unread_only:
                query = query.filter(Notification.is_read == False)
            
            # Order by creation date (newest first)
            query = query.order_by(Notification.created_at.desc())
            
            # Calculate pagination
            total = query.count()
            offset = (page - 1) * per_page
            notifications_list = query.offset(offset).limit(per_page).all()
            
            # Calculate pagination details
            pages = (total + per_page - 1) // per_page  # Ceiling division
            
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
                current_filters={'type': notification_type, 'unread_only': unread_only}
            )
    except Exception as e:
        current_app.logger.exception("Failed to load notifications: %s", e)
        flash("Failed to load notifications.", "danger")
        return redirect(url_for("notifications.notifications"))


@login_required
def mark_notification_read(notification_id):
    """Mark a specific notification as read."""
    try:
        mark_notification_as_read(notification_id)
        flash("Notification marked as read.", "success")
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


@roles_required('admin')
def broadcast_notification():
    """Display form to send broadcast notifications to all users."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        notification_type = request.form.get('notification_type', 'info')
        
        if not title or not message:
            flash("Title and message are required.", "danger")
            return render_template("notifications/broadcast.html")
        
        try:
            with get_db_session() as db:
                # Get all active users
                users = db.query(User).filter(User.is_active == True).all()
                
                # Send notification to each user
                for user in users:
                    notification = Notification(
                        title=title,
                        message=message,
                        notification_type=notification_type,
                        recipient_user_id=user.id
                    )
                    db.add(notification)
                
                db.commit()
                flash(f"Broadcast notification sent to {len(users)} users.", "success")
                return redirect(url_for("notifications.broadcast_notification"))
        except Exception as e:
            current_app.logger.exception("Failed to send broadcast notification: %s", e)
            flash("Failed to send broadcast notification.", "danger")
    
    return render_template("notifications/broadcast.html")


@roles_required('admin')
def system_notification():
    """Display form to send system-wide notifications."""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        notification_type = request.form.get('notification_type', 'info')
        
        if not title or not message:
            flash("Title and message are required.", "danger")
            return render_template("notifications/system.html")
        
        try:
            # Send system notification (no recipient user)
            send_system_notification(title, message, notification_type)
            flash("System notification sent successfully.", "success")
            return redirect(url_for("notifications.system_notification"))
        except Exception as e:
            current_app.logger.exception("Failed to send system notification: %s", e)
            flash("Failed to send system notification.", "danger")
    
    return render_template("notifications/system.html")