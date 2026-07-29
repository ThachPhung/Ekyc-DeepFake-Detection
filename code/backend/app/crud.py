from typing import Any

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models import User, UserCreate, UserUpdate, get_datetime_utc


def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user
def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


def get_user_by_oauth_provider(
    *, session: Session, provider: str, provider_user_id: str
) -> User | None:
    statement = select(User).where(
        User.auth_provider == provider,
        User.provider_user_id == provider_user_id,
    )
    return session.exec(statement).first()


def upsert_oauth_user(
    *,
    session: Session,
    provider: str,
    provider_user_id: str,
    email: str,
    full_name: str | None = None,
    avatar_url: str | None = None,
) -> User:
    user = get_user_by_oauth_provider(
        session=session, provider=provider, provider_user_id=provider_user_id
    )
    if not user:
        user = get_user_by_email(session=session, email=email)

    now = get_datetime_utc()

    if user:
        user.auth_provider = provider
        user.provider_user_id = provider_user_id
        user.avatar_url = avatar_url or user.avatar_url
        user.full_name = full_name or user.full_name
        user.updated_at = now
    else:
        user = User(
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            auth_provider=provider,
            provider_user_id=provider_user_id,
            hashed_password=None,
            is_active=True,
            is_superuser=False,
            created_at=now,
            updated_at=now,
        )

    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    if not db_user.hashed_password:
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
