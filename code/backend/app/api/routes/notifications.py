import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Notification,
    NotificationPublic,
    NotificationsPublic,
    NotificationUnreadCount,
    get_datetime_utc,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _unread_count(session: SessionDep, user_id: uuid.UUID) -> int:
    value = session.exec(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            col(Notification.read_at).is_(None),
        )
    ).one()
    return int(value or 0)


def _own_notification_or_404(
    *,
    session: SessionDep,
    notification_id: uuid.UUID,
    current_user: CurrentUser,
) -> Notification:
    notification = session.get(Notification, notification_id)
    if not notification or notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notification


@router.get("", response_model=NotificationsPublic)
def read_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
    notification_type: str | None = Query(default=None, alias="type"),
) -> Any:
    filters = [Notification.user_id == current_user.id]
    if unread_only:
        filters.append(col(Notification.read_at).is_(None))
    if notification_type:
        filters.append(Notification.type == notification_type)

    count = session.exec(
        select(func.count()).select_from(Notification).where(*filters)
    ).one()
    notifications = session.exec(
        select(Notification)
        .where(*filters)
        .order_by(col(Notification.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()

    return NotificationsPublic(
        data=notifications,
        count=int(count or 0),
        unread_count=_unread_count(session, current_user.id),
    )


@router.get("/unread-count", response_model=NotificationUnreadCount)
def read_unread_notification_count(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    return NotificationUnreadCount(
        unread_count=_unread_count(session, current_user.id),
    )


@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_read(
    session: SessionDep,
    current_user: CurrentUser,
    notification_id: uuid.UUID,
) -> Any:
    notification = _own_notification_or_404(
        session=session,
        notification_id=notification_id,
        current_user=current_user,
    )
    if notification.read_at is None:
        notification.read_at = get_datetime_utc()
        session.add(notification)
        session.commit()
        session.refresh(notification)
    return notification


@router.patch("/read-all", response_model=NotificationUnreadCount)
def mark_all_notifications_read(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    notifications = session.exec(
        select(Notification).where(
            Notification.user_id == current_user.id,
            col(Notification.read_at).is_(None),
        )
    ).all()
    now = get_datetime_utc()
    for notification in notifications:
        notification.read_at = now
        session.add(notification)
    session.commit()
    return NotificationUnreadCount(unread_count=0)
