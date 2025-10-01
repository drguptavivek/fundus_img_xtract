from db_transaction_manager import get_db_session
from models import Notification, NotificationType, User, Role
from sqlalchemy import select
from typing import List, Optional, Union


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
    with get_db_session() as db:
        # Create new notification
        notif_type = _normalize_type(notification_type)
        notification = Notification(
            title=title,
            message=message,
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
                title=title,
                message=message,
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
    with get_db_session() as db:
        notif_type = _normalize_type(notification_type)
        notification = Notification(
            title=title,
            message=message,
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


def mark_notification_as_read(notification_id: int):
    """
    Mark a specific notification as read
    
    Args:
        notification_id (int): ID of the notification to mark as read
    """
    with get_db_session() as db:
        notification = db.execute(
            select(Notification).where(Notification.id == notification_id)
        ).scalar()
        
        if notification:
            notification.mark_as_read()
            db.commit()


def mark_all_user_notifications_as_read(user_id: int):
    """
    Mark all notifications for a user as read
    
    Args:
        user_id (int): ID of the user
    """
    with get_db_session() as db:
        notifications = db.execute(
            select(Notification).where(
                Notification.recipient_user_id == user_id,
                Notification.is_read == False
            )
        ).scalars().all()
        
        for notification in notifications:
            notification.mark_as_read()
        
        db.commit()
