from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import String, cast, func, or_
from sqlmodel import Field, SQLModel, col, select

from app.api.deps import SessionDep, get_current_active_superuser
from app.core.config import settings
from app.models import (
    AdminAuditLog,
    AdminAuditLogPublic,
    AdminAuditLogsPublic,
    EkycRequestStatus,
    EkycResult,
    EkycSession,
    User,
    UserRole,
)
from app.services.admin_settings import (
    EKYC_PROCESSING_TIMEOUT_KEY,
    MAX_EKYC_PROCESSING_TIMEOUT_MINUTES,
    MIN_EKYC_PROCESSING_TIMEOUT_MINUTES,
    USER_NOTIFICATIONS_ENABLED_KEY,
    get_ekyc_processing_timeout_setting,
    get_user_notifications_enabled_setting,
    set_admin_setting,
)
from app.services.audit_log import create_admin_audit_log
from app.services.ekyc_queue import (
    EkycQueueError,
    get_ekyc_queue_length,
    ping_redis,
)

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUsersOverview(SQLModel):
    total: int
    active: int
    admins: int
    reviewers: int


class AdminEkycOverview(SQLModel):
    total: int
    pending: int
    processing: int
    success: int
    failed: int
    manual_review: int
    today: int
    latest_created_at: datetime | None = None
    latest_processed_at: datetime | None = None


class AdminServiceHealth(SQLModel):
    status: str
    message: str | None = None


class AdminQueueHealth(SQLModel):
    status: str
    queue_name: str
    pending_jobs: int | None = None
    message: str | None = None


class AdminSystemOverview(SQLModel):
    database: AdminServiceHealth
    redis: AdminServiceHealth
    ekyc_queue: AdminQueueHealth
    generated_at: datetime


class AdminOverviewPublic(SQLModel):
    users: AdminUsersOverview
    ekyc: AdminEkycOverview
    system: AdminSystemOverview


class AdminRuntimeSettings(SQLModel):
    project_name: str
    environment: str
    ai_service_url: str
    ai_model_version: str
    ekyc_queue_name: str
    upload_dir: str
    max_upload_size_mb: int
    max_video_upload_size_mb: int


class AdminSettingsPublic(SQLModel):
    ekyc_processing_timeout_minutes: int
    ekyc_processing_timeout_source: str
    user_notifications_enabled: bool
    user_notifications_source: str
    runtime: AdminRuntimeSettings


class AdminSettingsUpdate(SQLModel):
    ekyc_processing_timeout_minutes: int | None = Field(
        default=None,
        ge=MIN_EKYC_PROCESSING_TIMEOUT_MINUTES,
        le=MAX_EKYC_PROCESSING_TIMEOUT_MINUTES,
    )
    user_notifications_enabled: bool | None = None


AUDIT_ACTIONS = (
    "admin.settings.update",
    "user.create",
    "user.update",
    "user.delete",
    "ekyc.approve",
    "ekyc.reject",
    "ekyc.retry",
    "ekyc.delete",
)


def _count(session: SessionDep, statement: Any) -> int:
    value = session.exec(statement).one()
    return int(value or 0)


def _count_ekyc_status(
    session: SessionDep,
    status: EkycRequestStatus,
) -> int:
    return _count(
        session,
        select(func.count())
        .select_from(EkycSession)
        .where(EkycSession.status == status),
    )


def _latest_datetime(*values: datetime | None) -> datetime | None:
    present_values = [value for value in values if value is not None]
    if not present_values:
        return None
    return max(present_values)


def _redis_health() -> tuple[AdminServiceHealth, AdminQueueHealth]:
    try:
        is_alive = ping_redis()
        pending_jobs = get_ekyc_queue_length() if is_alive else None
    except (EkycQueueError, OSError, TimeoutError) as exc:
        message = str(exc)
        return (
            AdminServiceHealth(status="error", message=message),
            AdminQueueHealth(
                status="error",
                queue_name=settings.EKYC_QUEUE_NAME,
                pending_jobs=None,
                message=message,
            ),
        )

    redis_status = "ok" if is_alive else "error"
    queue_status = "ok" if pending_jobs is not None else "error"
    return (
        AdminServiceHealth(status=redis_status),
        AdminQueueHealth(
            status=queue_status,
            queue_name=settings.EKYC_QUEUE_NAME,
            pending_jobs=pending_jobs,
        ),
    )


def _admin_settings_public(session: SessionDep) -> AdminSettingsPublic:
    timeout_minutes, timeout_source = get_ekyc_processing_timeout_setting(session)
    notifications_enabled, notifications_source = (
        get_user_notifications_enabled_setting(session)
    )
    return AdminSettingsPublic(
        ekyc_processing_timeout_minutes=timeout_minutes,
        ekyc_processing_timeout_source=timeout_source,
        user_notifications_enabled=notifications_enabled,
        user_notifications_source=notifications_source,
        runtime=AdminRuntimeSettings(
            project_name=settings.PROJECT_NAME,
            environment=settings.ENVIRONMENT,
            ai_service_url=settings.EKYC_AI_SERVICE_URL,
            ai_model_version=settings.AI_MODEL_VERSION,
            ekyc_queue_name=settings.EKYC_QUEUE_NAME,
            upload_dir=settings.UPLOAD_DIR,
            max_upload_size_mb=settings.MAX_UPLOAD_SIZE_MB,
            max_video_upload_size_mb=settings.MAX_VIDEO_UPLOAD_SIZE_MB,
        ),
    )


@router.get(
    "/overview",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=AdminOverviewPublic,
)
def read_admin_overview(session: SessionDep) -> Any:
    today_start = datetime.now(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    users = AdminUsersOverview(
        total=_count(session, select(func.count()).select_from(User)),
        active=_count(
            session,
            select(func.count())
            .select_from(User)
            .where(col(User.is_active).is_(True)),
        ),
        admins=_count(
            session,
            select(func.count())
            .select_from(User)
            .where(col(User.is_superuser).is_(True)),
        ),
        reviewers=_count(
            session,
            select(func.count())
            .select_from(User)
            .where(User.role == UserRole.EKYC_REVIEWER),
        ),
    )

    latest_session_processed_at = session.exec(
        select(func.max(EkycSession.processed_at))
    ).one()
    latest_result_completed_at = session.exec(
        select(func.max(EkycResult.completed_at))
    ).one()
    ekyc = AdminEkycOverview(
        total=_count(session, select(func.count()).select_from(EkycSession)),
        pending=_count_ekyc_status(session, EkycRequestStatus.PENDING),
        processing=_count_ekyc_status(session, EkycRequestStatus.PROCESSING),
        success=_count_ekyc_status(session, EkycRequestStatus.SUCCESS),
        failed=_count_ekyc_status(session, EkycRequestStatus.FAILED),
        manual_review=_count_ekyc_status(session, EkycRequestStatus.MANUAL_REVIEW),
        today=_count(
            session,
            select(func.count())
            .select_from(EkycSession)
            .where(EkycSession.created_at >= today_start),
        ),
        latest_created_at=session.exec(select(func.max(EkycSession.created_at))).one(),
        latest_processed_at=_latest_datetime(
            latest_session_processed_at,
            latest_result_completed_at,
        ),
    )

    redis, queue = _redis_health()
    return AdminOverviewPublic(
        users=users,
        ekyc=ekyc,
        system=AdminSystemOverview(
            database=AdminServiceHealth(status="ok"),
            redis=redis,
            ekyc_queue=queue,
            generated_at=datetime.now(timezone.utc),
        ),
    )


@router.get(
    "/settings",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=AdminSettingsPublic,
)
def read_admin_settings(session: SessionDep) -> Any:
    return _admin_settings_public(session)


@router.patch(
    "/settings",
    response_model=AdminSettingsPublic,
)
def update_admin_settings(
    session: SessionDep,
    payload: AdminSettingsUpdate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    updated_values: dict[str, Any] = {}

    if payload.ekyc_processing_timeout_minutes is not None:
        updated_values[EKYC_PROCESSING_TIMEOUT_KEY] = (
            payload.ekyc_processing_timeout_minutes
        )
        set_admin_setting(
            session=session,
            key=EKYC_PROCESSING_TIMEOUT_KEY,
            value=payload.ekyc_processing_timeout_minutes,
            updated_by_user_id=current_user.id,
        )

    if payload.user_notifications_enabled is not None:
        updated_values[USER_NOTIFICATIONS_ENABLED_KEY] = (
            payload.user_notifications_enabled
        )
        set_admin_setting(
            session=session,
            key=USER_NOTIFICATIONS_ENABLED_KEY,
            value=payload.user_notifications_enabled,
            updated_by_user_id=current_user.id,
        )

    if updated_values:
        create_admin_audit_log(
            session=session,
            actor=current_user,
            action="admin.settings.update",
            target_type="admin_settings",
            details={"updated_values": updated_values},
        )
        session.commit()

    return _admin_settings_public(session)


@router.get(
    "/audit-logs",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=AdminAuditLogsPublic,
)
def read_admin_audit_logs(
    session: SessionDep,
    skip: int = 0,
    limit: int = 50,
    action: str | None = None,
    target_type: str | None = None,
    q: str | None = None,
) -> Any:
    statement = select(AdminAuditLog)
    count_statement = select(func.count()).select_from(AdminAuditLog)

    filters = []
    if action:
        filters.append(AdminAuditLog.action == action)
    if target_type:
        filters.append(AdminAuditLog.target_type == target_type)
    search_query = (q or "").strip()
    if search_query:
        needle = f"%{search_query}%"
        filters.append(
            or_(
                AdminAuditLog.actor_email.ilike(needle),
                AdminAuditLog.action.ilike(needle),
                AdminAuditLog.target_type.ilike(needle),
                AdminAuditLog.target_id.ilike(needle),
                AdminAuditLog.target_label.ilike(needle),
                cast(AdminAuditLog.details, String).ilike(needle),
            )
        )

    for query_filter in filters:
        statement = statement.where(query_filter)
        count_statement = count_statement.where(query_filter)

    count = _count(session, count_statement)
    audit_logs = session.exec(
        statement
        .order_by(AdminAuditLog.created_at.desc())  # type: ignore[union-attr]
        .offset(skip)
        .limit(limit)
    ).all()

    return AdminAuditLogsPublic(
        data=[AdminAuditLogPublic.model_validate(audit_log) for audit_log in audit_logs],
        count=count,
    )
