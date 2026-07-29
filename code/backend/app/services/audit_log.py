from typing import Any

from sqlmodel import Session

from app.models import AdminAuditLog, User


def create_admin_audit_log(
    *,
    session: Session,
    actor: User,
    action: str,
    target_type: str,
    target_id: str | None = None,
    target_label: str | None = None,
    details: dict[str, Any] | None = None,
) -> AdminAuditLog:
    audit_log = AdminAuditLog(
        actor_user_id=actor.id,
        actor_email=actor.email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details,
    )
    session.add(audit_log)
    return audit_log
