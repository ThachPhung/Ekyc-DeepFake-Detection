import warnings
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self


_CONFIG_DIR = Path(__file__).resolve().parent
_DEFAULT_ENV_FILES = (
    _CONFIG_DIR.parents[3] / ".env.local",
    _CONFIG_DIR.parents[2] / ".env.local",
    _CONFIG_DIR.parents[2] / "config" / ".env.local",
    _CONFIG_DIR.parents[3] / ".env",
    _CONFIG_DIR.parents[2] / ".env",
)


def parse_cors(v: Any) -> list[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [i.strip() for i in v.split(",") if i.strip()]
    elif isinstance(v, list | str):
        return v
    raise ValueError(v)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Prefer local overrides first, then fall back to the shared handoff envs.
        env_file=_DEFAULT_ENV_FILES,
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    # 60 minutes
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_HOST: str = "http://localhost:3060"
    FRONTEND_URL: str | None = None
    BACKEND_URL: str = "http://localhost:8000"
    ENVIRONMENT: Literal["local", "dev", "staging", "production"] = "local"

    BACKEND_CORS_ORIGINS: Annotated[
        list[AnyUrl] | str, BeforeValidator(parse_cors)
    ] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def all_cors_origins(self) -> list[str]:
        frontend_origins = [self.FRONTEND_HOST]
        if self.FRONTEND_URL:
            frontend_origins.append(self.FRONTEND_URL)
        return [str(origin).rstrip("/") for origin in self.BACKEND_CORS_ORIGINS] + [
            origin.rstrip("/") for origin in frontend_origins
        ]

    PROJECT_NAME: str
    SENTRY_DSN: HttpUrl | None = None
    REDIS_URL: str = "redis://localhost:6379/0"
    EKYC_QUEUE_NAME: str = "ekyc:ocr:jobs"
    UPLOAD_DIR: str = "../uploads/ekyc"
    MAX_UPLOAD_SIZE_MB: int = 5
    MAX_VIDEO_UPLOAD_SIZE_MB: int = 10
    EKYC_PROCESSING_TIMEOUT_MINUTES: int = 5
    AI_MODEL_VERSION: str = "ocr-id-card-two-sides-v1"
    EKYC_AI_SERVICE_URL: str = "http://localhost:8001"
    EKYC_AI_REQUEST_TIMEOUT_SECONDS: float = 90.0
    EKYC_INTERNAL_API_KEY: str | None = None
    EKYC_PII_PUBLIC_KEY_PEM: str | None = None
    EKYC_PII_PUBLIC_KEY_PATH: str | None = None
    EKYC_PII_PRIVATE_KEY_PEM: str | None = None
    EKYC_PII_PRIVATE_KEY_PATH: str | None = None
    EKYC_PRIVATE_STORAGE_DIR: str | None = None
    EKYC_IDENTITY_HASH_KEY: str | None = None
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    FACEBOOK_CLIENT_ID: str | None = None
    FACEBOOK_CLIENT_SECRET: str | None = None
    MICROSOFT_CLIENT_ID: str | None = None
    MICROSOFT_CLIENT_SECRET: str | None = None
    MICROSOFT_TENANT_ID: str = "common"
    OAUTH_STATE_SECRET: str | None = None
    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 12
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 12
    EMAIL_VERIFICATION_REQUIRED: bool = True

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.ENVIRONMENT == "local":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        self._check_default_secret("POSTGRES_PASSWORD", self.POSTGRES_PASSWORD)
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore
