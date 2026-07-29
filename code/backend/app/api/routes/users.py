import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import col, func, select

from app import crud
from app.api.deps import (
    CurrentUser,
    SessionDep,
    get_current_active_superuser,
)
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models import (
    EkycRequestStatus,
    EkycSession,
    EmailVerification,
    EmailVerificationResend,
    Message,
    UpdatePassword,
    User,
    UserAdminUpdate,
    UserCreate,
    UserPublic,
    UserRegister,
    UserRole,
    UsersPublic,
    UserUpdateMe,
    get_datetime_utc,
)
from app.services.audit_log import create_admin_audit_log
from app.utils import (
    generate_email_verification_email,
    generate_email_verification_token,
    generate_new_account_email,
    send_email,
    verify_email_verification_token,
)

router = APIRouter(prefix="/users", tags=["users"])


def _latest_ekyc_status(session: SessionDep, user_id: uuid.UUID) -> str | None:
    statement = (
        select(EkycSession.status)
        .where(EkycSession.user_id == user_id)
        .order_by(col(EkycSession.created_at).desc())  # type: ignore[union-attr]
        .limit(1)
    )
    latest_status = session.exec(statement).first()
    if isinstance(latest_status, EkycRequestStatus):
        return latest_status.value
    return latest_status


def _user_public(
    user: User,
    *,
    ekyc_status: str | None = None,
) -> UserPublic:
    return UserPublic.model_validate(user, update={"ekyc_status": ekyc_status})


def _user_role_value(role: UserRole | str) -> str:
    return role.value if isinstance(role, UserRole) else role


def _normalize_admin_update(user: User, user_data: dict[str, Any]) -> dict[str, Any]:
    if user_data.get("is_superuser") is True and not user.is_superuser:
        if user.role != UserRole.EKYC_REVIEWER:
            raise HTTPException(
                status_code=400,
                detail="Only staff reviewers can be promoted to system admin",
            )

    if user_data.get("is_superuser") is True:
        user_data["role"] = UserRole.USER

    return user_data


def _send_verification_email(user: User) -> None:
    email_verification_token = generate_email_verification_token(email=user.email)
    email_data = generate_email_verification_email(
        email_to=user.email, email=user.email, token=email_verification_token
    )
    send_email(
        email_to=user.email,
        subject=email_data.subject,
        html_content=email_data.html_content,
        raise_on_failure=True,
    )


def _email_verification_enabled() -> bool:
    return settings.EMAIL_VERIFICATION_REQUIRED and settings.emails_enabled


@router.get(
    "/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve users.
    """

    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = (
        select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    )
    users = session.exec(statement).all()

    users_public = [
        _user_public(user, ekyc_status=_latest_ekyc_status(session, user.id))
        for user in users
    ]
    return UsersPublic(data=users_public, count=count)


@router.post("/", response_model=UserPublic)
def create_user(
    *,
    session: SessionDep,
    user_in: UserCreate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Create new user.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    if user_in.is_superuser:
        raise HTTPException(
            status_code=400,
            detail="Only staff reviewers can be promoted to system admin",
        )
    if user_in.role != UserRole.EKYC_REVIEWER:
        raise HTTPException(
            status_code=400,
            detail="Admin-created accounts must be staff reviewers",
        )

    user = crud.create_user(session=session, user_create=user_in)
    user_public = _user_public(user)
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="user.create",
        target_type="user",
        target_id=str(user.id),
        target_label=user.email,
        details={
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "role": _user_role_value(user.role),
        },
    )
    session.commit()
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user_public


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """

    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return _user_public(current_user)


@router.patch("/me/password", response_model=Message)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Password login is not enabled for this account",
        )
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return _user_public(current_user)


@router.delete("/me", response_model=Message)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    session.delete(current_user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        if not user.is_email_verified:
            if _email_verification_enabled():
                try:
                    _send_verification_email(user)
                except Exception:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Could not send verification email. "
                            "Please try again later."
                        ),
                    )
            return _user_public(user)
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    user_create = UserCreate.model_validate(
        user_in, update={"is_email_verified": not settings.EMAIL_VERIFICATION_REQUIRED}
    )
    user = crud.create_user(session=session, user_create=user_create)
    if _email_verification_enabled():
        try:
            _send_verification_email(user)
        except Exception:
            session.delete(user)
            session.commit()
            raise HTTPException(
                status_code=503,
                detail="Could not send verification email. Please try again later.",
            )
    return _user_public(user)


@router.post("/resend-verification", response_model=Message)
def resend_email_verification(
    session: SessionDep, body: EmailVerificationResend
) -> Message:
    """
    Resend a verification email for an existing unverified account.
    """
    user = crud.get_user_by_email(session=session, email=body.email)
    message = "If that email needs verification, we sent a verification link"
    if not user or user.is_email_verified:
        return Message(message=message)
    if _email_verification_enabled():
        try:
            _send_verification_email(user)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Could not send verification email. Please try again later.",
            )
    return Message(message=message)


@router.post("/verify-email", response_model=Message)
def verify_email(session: SessionDep, body: EmailVerification) -> Message:
    """
    Verify a newly registered user's email address.
    """
    email = verify_email_verification_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = crud.get_user_by_email(session=session, email=email)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    user.is_email_verified = True
    user.updated_at = get_datetime_utc()
    session.add(user)
    session.commit()
    return Message(message="Email verified successfully")


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id.
    """
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        return _user_public(user, ekyc_status=_latest_ekyc_status(session, user.id))
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    return _user_public(user, ekyc_status=_latest_ekyc_status(session, user.id))


@router.patch(
    "/{user_id}",
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserAdminUpdate,
    current_user: User = Depends(get_current_active_superuser),
) -> Any:
    """
    Update a user.
    """

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    before = {
        "is_active": db_user.is_active,
        "is_superuser": db_user.is_superuser,
        "role": _user_role_value(db_user.role),
    }
    user_data = user_in.model_dump(exclude_unset=True)
    user_data = _normalize_admin_update(db_user, user_data)
    db_user.sqlmodel_update(user_data, update={"updated_at": get_datetime_utc()})
    after = {
        "is_active": db_user.is_active,
        "is_superuser": db_user.is_superuser,
        "role": _user_role_value(db_user.role),
    }
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="user.update",
        target_type="user",
        target_id=str(db_user.id),
        target_label=db_user.email,
        details={
            "before": before,
            "after": after,
            "changed_fields": sorted(user_data.keys()),
        },
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return _user_public(
        db_user,
        ekyc_status=_latest_ekyc_status(session, db_user.id),
    )


@router.delete("/{user_id}")
def delete_user(
    session: SessionDep,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_active_superuser),
) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    create_admin_audit_log(
        session=session,
        actor=current_user,
        action="user.delete",
        target_type="user",
        target_id=str(user.id),
        target_label=user.email,
        details={
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "role": _user_role_value(user.role),
        },
    )
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")
