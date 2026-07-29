import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import ConfigDict, EmailStr, field_validator
from sqlalchemy import JSON, Column, DateTime, Index, String, Text, text
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    USER = "user"
    EKYC_REVIEWER = "ekyc_reviewer"


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_email_verified: bool = True
    is_superuser: bool = False
    role: UserRole = Field(
        default=UserRole.USER,
        sa_column=Column(String(50), nullable=False, default=UserRole.USER.value, index=True),
    )
    full_name: str | None = Field(default=None, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=1024)
    auth_provider: str | None = Field(default=None, max_length=50, index=True)
    provider_user_id: str | None = Field(default=None, max_length=255, index=True)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=59)
    email: EmailStr | None = Field(default=None, max_length=255)

    @field_validator("full_name", mode="before")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Username cannot be empty")
        normalized = value.strip()
        if not normalized:
            raise ValueError("Username cannot be empty")
        return normalized


class UserAdminUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = None
    is_superuser: bool | None = None
    role: UserRole | None = None


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str | None = Field(default=None)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    ekyc_sessions: list["EkycSession"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    ekyc_results: list["EkycResult"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"passive_deletes": True},
    )
    verified_identities: list["VerifiedIdentity"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"passive_deletes": True},
    )


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None
    updated_at: datetime | None = None
    ekyc_status: str | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


class EkycRequestStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class EkycVideoStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class EkycDocumentType(str, Enum):
    CCCD = "CCCD"
    GPLX = "GPLX"
    HOCHIEU = "HOCHIEU"


class EkycFileType(str, Enum):
    DOCUMENT_FRONT = "DOCUMENT_FRONT"
    DOCUMENT_BACK = "DOCUMENT_BACK"
    LIVENESS_VIDEO = "LIVENESS_VIDEO"
    VOICE_AUDIO = "VOICE_AUDIO"


class EkycVoiceSessionStatus(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class EkycSession(SQLModel, table=True):
    __tablename__ = "ekyc_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4, unique=True, index=True)
    user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        ondelete="SET NULL",
    )
    status: EkycRequestStatus = Field(default=EkycRequestStatus.PENDING, index=True)
    document_type: EkycDocumentType = Field(default=EkycDocumentType.CCCD, max_length=20)
    result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    score: float | None = Field(default=None)
    confidence: float | None = Field(default=None)
    decision: str | None = Field(default=None, max_length=50)
    error_message: str | None = Field(default=None, max_length=1024)
    model_version: str | None = Field(default=None, max_length=100)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    processed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    owner: User | None = Relationship(back_populates="ekyc_sessions")
    files: list["EkycFile"] = Relationship(
        back_populates="session",
        cascade_delete=True,
    )
    results: list["EkycResult"] = Relationship(
        back_populates="session",
        cascade_delete=True,
    )


class EkycVoiceSession(SQLModel, table=True):
    __tablename__ = "ekyc_voice_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    status: EkycVoiceSessionStatus = Field(
        default=EkycVoiceSessionStatus.PENDING,
        max_length=20,
        index=True,
    )
    display_digits: list[str] = Field(sa_column=Column(JSON, nullable=False))
    display_text: str = Field(max_length=50)
    expected_text: str = Field(max_length=255)
    spoken_hint: str = Field(max_length=255)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)
    liveness_video_hash: str | None = Field(default=None, max_length=128)
    ai_result: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        index=True,
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))  # type: ignore
    verified_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore


class EkycFile(SQLModel, table=True):
    __tablename__ = "ekyc_files"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(
        foreign_key="ekyc_sessions.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    file_type: EkycFileType = Field(index=True, max_length=50)
    file_path: str = Field(max_length=1024)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int | None = Field(default=None)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    session: EkycSession = Relationship(back_populates="files")


class EkycResult(SQLModel, table=True):
    __tablename__ = "ekyc_results"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(
        foreign_key="ekyc_sessions.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        index=True,
        ondelete="SET NULL",
    )
    status: EkycRequestStatus = Field(default=EkycRequestStatus.PENDING, index=True)
    decision: str | None = Field(default=None, max_length=50, index=True)
    score: float | None = Field(default=None)
    confidence: float | None = Field(default=None)
    document_result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    encrypted_document_result: str | None = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    liveness_result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    voice_result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    raw_result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    error_message: str | None = Field(default=None, max_length=1024)
    model_version: str | None = Field(default=None, max_length=100)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    session: EkycSession = Relationship(back_populates="results")
    owner: User | None = Relationship(back_populates="ekyc_results")
    verified_identity: Optional["VerifiedIdentity"] = Relationship(
        back_populates="ekyc_result",
    )


class VerifiedIdentity(SQLModel, table=True):
    __tablename__ = "verified_identities"
    __table_args__ = (
        Index(
            "ux_verified_identities_active_identity_number_hash",
            "identity_number_hash",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    ekyc_result_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="ekyc_results.id",
        nullable=True,
        unique=True,
        index=True,
        ondelete="SET NULL",
    )
    document_type: EkycDocumentType = Field(default=EkycDocumentType.CCCD, max_length=20)
    identity_number_hash: str = Field(max_length=128)
    identity_number_encrypted: str | None = Field(default=None, max_length=2048)
    full_name: str | None = Field(default=None, max_length=255)
    birth_date: str | None = Field(default=None, max_length=50)
    gender: str | None = Field(default=None, max_length=50)
    nationality: str | None = Field(default=None, max_length=100)
    issued_date: str | None = Field(default=None, max_length=50)
    expired_date: str | None = Field(default=None, max_length=50)
    verified_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    updated_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner: User = Relationship(back_populates="verified_identities")
    ekyc_result: EkycResult | None = Relationship(back_populates="verified_identity")


class EkycRequestCreateResponse(SQLModel):
    request_id: uuid.UUID
    status: EkycRequestStatus
    document_type: EkycDocumentType
    message: str


class MyVerifiedIdentityPublic(SQLModel):
    is_verified: bool
    document_type: EkycDocumentType | None = None
    identity_number: str | None = None
    full_name: str | None = None
    birth_date: str | None = None
    gender: str | None = None
    nationality: str | None = None
    address: str | None = None
    place_of_origin: str | None = None
    place_of_residence: str | None = None
    issued_date: str | None = None
    issue_place: str | None = None
    expired_date: str | None = None
    verified_at: datetime | None = None


class EkycRequestPublic(SQLModel):
    request_id: uuid.UUID
    status: EkycRequestStatus
    document_type: EkycDocumentType
    message: str | None = None
    result: dict[str, Any] | None = None
    score: float | None = None
    confidence: float | None = None
    decision: str | None = None
    ocr_result: dict[str, Any] | None = None
    document_confirmed_fields: dict[str, Any] | None = None
    document_confirmed_at: datetime | None = None
    video_status: EkycVideoStatus = EkycVideoStatus.NOT_STARTED
    video_result: dict[str, Any] | None = None
    voice_result: dict[str, Any] | None = None
    face_similarity: float | None = None
    face_decision: str | None = None
    error_message: str | None = None
    video_error_message: str | None = None
    model_version: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    processed_at: datetime | None = None
    video_processed_at: datetime | None = None


class EkycRequestAdminPublic(EkycRequestPublic):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    owner_email: str | None = None
    owner_full_name: str | None = None
    duplicate_identity_detected: bool = False
    duplicate_identity_warning: str | None = None
    image_path: str | None = None
    front_image_path: str | None = None
    back_image_path: str | None = None
    liveness_path: str | None = None
    voice_path: str | None = None
    video_path: str | None = None
    video_result: dict[str, Any] | None = None
    ai_admin_review: dict[str, Any] | None = None
    error_message: str | None = None
    video_error_message: str | None = None


class EkycDocumentFieldsAdminUpdate(SQLModel):
    full_name: str | None = None
    id_number: str | None = None
    passport_number: str | None = None
    date_of_birth: str | None = None
    birth_year: str | None = None
    sex: str | None = None
    gender: str | None = None
    nationality: str | None = None
    address: str | None = None
    place_of_origin: str | None = None
    place_of_residence: str | None = None
    issue_date: str | None = None
    issue_place: str | None = None
    expiry_date: str | None = None
    expired_date: str | None = None


class EkycRequestsAdminPublic(SQLModel):
    data: list[EkycRequestAdminPublic]
    count: int


class AdminAuditLog(SQLModel, table=True):
    __tablename__ = "admin_audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    actor_user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        index=True,
        ondelete="SET NULL",
    )
    actor_email: str | None = Field(default=None, max_length=255, index=True)
    action: str = Field(max_length=100, index=True)
    target_type: str = Field(max_length=100, index=True)
    target_id: str | None = Field(default=None, max_length=255, index=True)
    target_label: str | None = Field(default=None, max_length=255)
    details: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        index=True,
    )


class AdminAuditLogPublic(SQLModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    actor_email: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    target_label: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime


class AdminAuditLogsPublic(SQLModel):
    data: list[AdminAuditLogPublic]
    count: int


class AdminSetting(SQLModel, table=True):
    __tablename__ = "admin_settings"

    key: str = Field(primary_key=True, max_length=120)
    value: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    updated_by_user_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
        ondelete="SET NULL",
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(
        foreign_key="user.id",
        nullable=False,
        index=True,
        ondelete="CASCADE",
    )
    type: str = Field(max_length=100, index=True)
    title: str = Field(max_length=255)
    message: str = Field(max_length=1024)
    data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    read_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
        index=True,
    )


class NotificationPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: str
    data: dict[str, Any] | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationsPublic(SQLModel):
    data: list[NotificationPublic]
    count: int
    unread_count: int


class NotificationUnreadCount(SQLModel):
    unread_count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class EmailVerification(SQLModel):
    token: str


class EmailVerificationResend(SQLModel):
    email: EmailStr = Field(max_length=255)
