import uuid
from typing import Any

from sqlmodel import Session

from app.models import Notification
from app.services.admin_settings import are_user_notifications_enabled


def create_user_notification(
    *,
    session: Session,
    user_id: uuid.UUID,
    type: str,
    title: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> Notification | None:
    if not are_user_notifications_enabled(session):
        return None

    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        data=data,
    )
    session.add(notification)
    return notification
