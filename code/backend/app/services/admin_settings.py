import uuid
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.models import AdminSetting, get_datetime_utc

EKYC_PROCESSING_TIMEOUT_KEY = "ekyc_processing_timeout_minutes"
USER_NOTIFICATIONS_ENABLED_KEY = "user_notifications_enabled"

MIN_EKYC_PROCESSING_TIMEOUT_MINUTES = 1
MAX_EKYC_PROCESSING_TIMEOUT_MINUTES = 240


def _setting_value(row: AdminSetting | None, default: Any) -> tuple[Any, str]:
    if not row or not isinstance(row.value, dict) or "value" not in row.value:
        return default, "environment"
    return row.value["value"], "database"


def _clamp_timeout(value: Any) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = settings.EKYC_PROCESSING_TIMEOUT_MINUTES
    return max(
        MIN_EKYC_PROCESSING_TIMEOUT_MINUTES,
        min(timeout, MAX_EKYC_PROCESSING_TIMEOUT_MINUTES),
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def get_ekyc_processing_timeout_minutes(session: Session) -> int:
    row = session.get(AdminSetting, EKYC_PROCESSING_TIMEOUT_KEY)
    value, _source = _setting_value(row, settings.EKYC_PROCESSING_TIMEOUT_MINUTES)
    return _clamp_timeout(value)


def get_ekyc_processing_timeout_setting(session: Session) -> tuple[int, str]:
    row = session.get(AdminSetting, EKYC_PROCESSING_TIMEOUT_KEY)
    value, source = _setting_value(row, settings.EKYC_PROCESSING_TIMEOUT_MINUTES)
    return _clamp_timeout(value), source


def are_user_notifications_enabled(session: Session) -> bool:
    row = session.get(AdminSetting, USER_NOTIFICATIONS_ENABLED_KEY)
    value, _source = _setting_value(row, True)
    return _coerce_bool(value)


def get_user_notifications_enabled_setting(session: Session) -> tuple[bool, str]:
    row = session.get(AdminSetting, USER_NOTIFICATIONS_ENABLED_KEY)
    value, source = _setting_value(row, True)
    return _coerce_bool(value), source


def set_admin_setting(
    *,
    session: Session,
    key: str,
    value: Any,
    updated_by_user_id: uuid.UUID | None,
) -> AdminSetting:
    row = session.get(AdminSetting, key)
    if row:
        row.value = {"value": value}
        row.updated_by_user_id = updated_by_user_id
        row.updated_at = get_datetime_utc()
    else:
        row = AdminSetting(
            key=key,
            value={"value": value},
            updated_by_user_id=updated_by_user_id,
        )
    session.add(row)
    return row
