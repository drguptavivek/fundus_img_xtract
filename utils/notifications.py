from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import select

from db_transaction_manager import get_db_session
from models import Notification, NotificationRead, NotificationType, Role, User

MAX_TITLE_LENGTH = 200
MAX_MESSAGE_LENGTH = 2000


def _clean_text(value: str) -> str:
    return value.strip()


def prepare_notification_payload(title: str, message: str) -> tuple[str, str]:
    cleaned_title = _clean_text(title)
    cleaned_message = _clean_text(message)

    if not cleaned_title or not cleaned_message:
        raise ValueError("Title and message are required.")

    if len(cleaned_title) > MAX_TITLE_LENGTH:
        raise ValueError(f"Title cannot exceed {MAX_TITLE_LENGTH} characters.")

    if len(cleaned_message) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Message cannot exceed {MAX_MESSAGE_LENGTH} characters.")

    return cleaned_title, cleaned_message


def _normalize_type(notification_type: Union[NotificationType, str]) -> NotificationType:
    if isinstance(notification_type, NotificationType):
        return notification_type
    try:
        return NotificationType(notification_type)
    except ValueError:
        return NotificationType.INFO


def send_notification_to_user(
    user_id: int,
    title: str,
    message: str,
    notification_type: Union[NotificationType, str] = NotificationType.INFO,
    *,
    sender_user_id: Optional[int] = None,
):
    """
    Send a notification to a specific user
    
    Args:
        user_id (int): ID of the user to send notification to
        title (str): Title of the notification
        message (str): Content of the notification
        notification_type (NotificationType): Type of notification (INFO, WARNING, ERROR, SYSTEM)
    
    Returns:
        Notification: The created notification object
    """
    cleaned_title, cleaned_message = prepare_notification_payload(title, message)

    with get_db_session() as db:
        notif_type = _normalize_type(notification_type)
        notification = Notification(
            title=cleaned_title,
            message=cleaned_message,
            notification_type=notif_type.value,
            recipient_user_id=user_id,
            sender_user_id=sender_user_id,
        )

        # Add to session and commit
        db.add(notification)
        db.flush()  # Get the ID without committing
        
        return notification


def send_notification_to_admins(
    title: str,
    message: str,
    notification_type: Union[NotificationType, str] = NotificationType.INFO,
    *,
    sender_user_id: Optional[int] = None,
):
    """
    Send a notification to all admin users
    
    Args:
        title (str): Title of the notification
        message (str): Content of the notification
        notification_type (NotificationType): Type of notification (INFO, WARNING, ERROR, SYSTEM)
    
    Returns:
        list: List of created notification objects
    """
    cleaned_title, cleaned_message = prepare_notification_payload(title, message)

    with get_db_session() as db:
        # Find admin users (users with 'admin' role)
        admin_role = db.execute(
            select(Role).where(Role.name == 'admin')
        ).scalar()
        
        if not admin_role:
            # If there's no admin role in the system, just return empty list
            return []
        
        # Get all users with the admin role
        admin_users = db.execute(
            select(User).where(User.roles.any(Role.id == admin_role.id))
        ).scalars().all()
        
        notifications = []
        notif_type = _normalize_type(notification_type)

        for admin_user in admin_users:
            notification = Notification(
                title=cleaned_title,
                message=cleaned_message,
                notification_type=notif_type.value,
                recipient_user_id=admin_user.id,
                sender_user_id=sender_user_id,
            )
            
            db.add(notification)
            notifications.append(notification)
        
        # Commit all notifications
        db.commit()
        return notifications


def send_system_notification(
    title: str,
    message: str,
    notification_type: Union[NotificationType, str] = NotificationType.INFO,
    *,
    sender_user_id: Optional[int] = None,
):
    """
    Send a system-wide notification (not directed to a specific user)
    
    Args:
        title (str): Title of the notification
        message (str): Content of the notification
        notification_type (NotificationType): Type of notification (INFO, WARNING, ERROR, SYSTEM)
    
    Returns:
        Notification: The created notification object
    """
    cleaned_title, cleaned_message = prepare_notification_payload(title, message)

    with get_db_session() as db:
        notif_type = _normalize_type(notification_type)
        notification = Notification(
            title=cleaned_title,
            message=cleaned_message,
            notification_type=notif_type.value,
            recipient_user_id=None,
            sender_user_id=sender_user_id,
        )
        
        db.add(notification)
        db.commit()
        
        return notification


def get_user_notifications(user_id: int, unread_only: bool = False, limit: Optional[int] = None):
    """
    Get notifications for a specific user
    
    Args:
        user_id (int): ID of the user
        unread_only (bool): If True, return only unread notifications
        limit (int): Limit number of notifications returned
    
    Returns:
        list: List of notification objects
    """
    with get_db_session() as db:
        query = select(Notification).where(Notification.recipient_user_id == user_id)
        
        if unread_only:
            query = query.where(Notification.is_read == False)
        
        query = query.order_by(Notification.created_at.desc())
        
        if limit:
            query = query.limit(limit)
        
        return db.execute(query).scalars().all()


def mark_notification_as_read(notification_id: int, user_id: int) -> bool:
    """
    Mark a specific notification as read

    Args:
        notification_id (int): ID of the notification to mark as read
        user_id (int): ID of the user requesting the change
    """
    with get_db_session() as db:
        notification = db.execute(
            select(Notification).where(Notification.id == notification_id)
        ).scalar()
        if notification is None:
            return False

        if notification.recipient_user_id is None:
            existing = db.execute(
                select(NotificationRead).where(
                    NotificationRead.notification_id == notification_id,
                    NotificationRead.user_id == user_id,
                )
            ).scalar()
            if existing:
                return True
            db.add(NotificationRead(notification_id=notification_id, user_id=user_id))
            db.commit()
            return True

        if notification.recipient_user_id != user_id:
            return False

        if notification.is_read:
            return True

        notification.mark_as_read()
        db.commit()
        return True


def mark_all_user_notifications_as_read(user_id: int):
    """
    Mark all notifications for a user as read
    
    Args:
        user_id (int): ID of the user
    """
    with get_db_session() as db:
        target_notifications = db.execute(
            select(Notification).where(
                Notification.recipient_user_id == user_id,
                Notification.is_read.is_(False),
            )
        ).scalars().all()

        for notification in target_notifications:
            notification.mark_as_read()

        system_notification_ids = db.execute(
            select(Notification.id).where(Notification.recipient_user_id.is_(None))
        ).scalars().all()

        if system_notification_ids:
            existing_ids = set(
                db.execute(
                    select(NotificationRead.notification_id).where(
                        NotificationRead.user_id == user_id,
                        NotificationRead.notification_id.in_(system_notification_ids),
                    )
                ).scalars()
            )
            for notification_id in system_notification_ids:
                if notification_id in existing_ids:
                    continue
                db.add(NotificationRead(notification_id=notification_id, user_id=user_id))

        db.commit()
