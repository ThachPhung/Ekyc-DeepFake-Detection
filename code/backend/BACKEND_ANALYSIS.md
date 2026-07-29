# Backend Analysis

Scope: this analysis only covers `code/backend`. AI modules, eKYC modules, model folders, and other project-level modules are intentionally excluded.

## Summary

The backend is a FastAPI application generated from a full-stack FastAPI template. It exposes REST endpoints under `/api/v1`, uses SQLModel for database models and Pydantic schemas, PostgreSQL through `psycopg`, Alembic for migrations, JWT bearer authentication, and email utilities for account/password flows.

## Framework And Main Libraries

- Framework: FastAPI
- API server entrypoint: `app/main.py`
- API router aggregator: `app/api/main.py`
- ORM/schema layer: SQLModel
- Validation/settings: Pydantic v2 and pydantic-settings
- Database: PostgreSQL via `psycopg`
- Migrations: Alembic
- Auth: OAuth2 password flow + JWT bearer token
- Password hashing: `pwdlib` with Argon2 and bcrypt verification/migration support
- Email: `emails`, Jinja2 templates
- Observability: Sentry SDK when configured and not in local environment
- Tests: Pytest + FastAPI TestClient

## Module Structure

```text
code/backend
|-- app
|   |-- main.py                  # FastAPI app creation, CORS, router include
|   |-- api
|   |   |-- main.py              # includes route modules
|   |   |-- deps.py              # DB session, OAuth2, current user, superuser deps
|   |   `-- routes
|   |       |-- login.py         # auth, token, password recovery
|   |       |-- users.py         # user CRUD/profile/signup
|   |       |-- items.py         # item CRUD
|   |       |-- utils.py         # test email, health check
|   |       `-- private.py       # local-only private user creation route
|   |-- core
|   |   |-- config.py            # environment settings
|   |   |-- db.py                # SQLModel engine and initial superuser creation
|   |   `-- security.py          # JWT and password hashing
|   |-- models.py                # SQLModel database models and API schemas
|   |-- crud.py                  # user/item CRUD helpers and authentication
|   |-- utils.py                 # email templates, reset tokens, email send
|   |-- initial_data.py          # creates initial superuser
|   |-- backend_pre_start.py     # waits for DB
|   `-- alembic                  # migration environment and versions
|-- scripts
|   |-- prestart.sh              # DB wait, migrations, initial data
|   |-- test.sh
|   |-- tests-start.sh
|   |-- lint.sh
|   `-- format.sh
|-- tests                         # route, CRUD, and script tests
|-- Dockerfile
|-- alembic.ini
|-- pyproject.toml
`-- README.md
```

## Main Configuration Files

- `pyproject.toml`
  - Defines Python package `app`, dependencies, dev dependencies, Ruff, mypy, coverage, and ty config.
- `app/core/config.py`
  - Defines runtime settings loaded from `../.env`.
  - Defines API prefix, CORS, JWT secret, database DSN, email settings, and first superuser settings.
- `app/main.py`
  - Creates FastAPI app.
  - Configures OpenAPI URL at `/api/v1/openapi.json`.
  - Adds CORS middleware if origins are configured.
  - Includes API router at `/api/v1`.
- `app/api/main.py`
  - Includes `login`, `users`, `utils`, and `items` routers.
  - Includes `private` router only when `ENVIRONMENT == "local"`.
- `alembic.ini` and `app/alembic/*`
  - Alembic migration config and migration history.
- `Dockerfile`
  - Production container command: `fastapi run --workers 4 app/main.py`.

## API Controllers / Routes

All standard routes are mounted below `settings.API_V1_STR`, default `/api/v1`.

### Login routes

File: `app/api/routes/login.py`

- `POST /login/access-token`
- `POST /login/test-token`
- `POST /password-recovery/{email}`
- `POST /reset-password/`
- `POST /password-recovery-html-content/{email}`

### User routes

File: `app/api/routes/users.py`

- `GET /users/`
- `POST /users/`
- `PATCH /users/me`
- `PATCH /users/me/password`
- `GET /users/me`
- `DELETE /users/me`
- `POST /users/signup`
- `GET /users/{user_id}`
- `PATCH /users/{user_id}`
- `DELETE /users/{user_id}`

### Item routes

File: `app/api/routes/items.py`

- `GET /items/`
- `GET /items/{id}`
- `POST /items/`
- `PUT /items/{id}`
- `DELETE /items/{id}`

### Utility routes

File: `app/api/routes/utils.py`

- `POST /utils/test-email/`
- `GET /utils/health-check/`

### Local-only private routes

File: `app/api/routes/private.py`

These are included only when `ENVIRONMENT == "local"`.

- `POST /private/users/`

## Services / Business Logic

There is no separate service layer yet. Business logic is split across:

- `app/crud.py`
  - `create_user`
  - `update_user`
  - `get_user_by_email`
  - `authenticate`
  - `create_item`
- `app/core/security.py`
  - `create_access_token`
  - `verify_password`
  - `get_password_hash`
- `app/core/db.py`
  - `engine`
  - `init_db`
- `app/utils.py`
  - email template rendering
  - SMTP email sending
  - password reset token generation/verification
  - test/new account/password recovery email generation

## DTO / Entity / Schema Inventory

File: `app/models.py`

### User schemas/models

- `UserBase`
  - `email`
  - `is_active`
  - `is_superuser`
  - `full_name`
- `UserCreate`
  - extends `UserBase`
  - `password`
- `UserRegister`
  - `email`
  - `password`
  - `full_name`
- `UserUpdate`
  - optional `email`
  - optional `password`
  - inherited optional-ish base fields
- `UserUpdateMe`
  - optional `full_name`
  - optional `email`
- `UpdatePassword`
  - `current_password`
  - `new_password`
- `User`
  - database table
  - `id`
  - `email`
  - `is_active`
  - `is_superuser`
  - `full_name`
  - `hashed_password`
  - `created_at`
  - relationship `items`
- `UserPublic`
  - public response shape
  - `id`
  - `email`
  - `is_active`
  - `is_superuser`
  - `full_name`
  - `created_at`
- `UsersPublic`
  - `data: UserPublic[]`
  - `count`

### Item schemas/models

- `ItemBase`
  - `title`
  - `description`
- `ItemCreate`
  - extends `ItemBase`
- `ItemUpdate`
  - optional `title`
  - optional/inherited `description`
- `Item`
  - database table
  - `id`
  - `title`
  - `description`
  - `created_at`
  - `owner_id`
  - relationship `owner`
- `ItemPublic`
  - public response shape
  - `id`
  - `title`
  - `description`
  - `owner_id`
  - `created_at`
- `ItemsPublic`
  - `data: ItemPublic[]`
  - `count`

### Auth / generic schemas

- `Message`
  - `message`
- `Token`
  - `access_token`
  - `token_type`, default `bearer`
- `TokenPayload`
  - `sub`
- `NewPassword`
  - `token`
  - `new_password`

## Authentication And Authorization

- Login uses OAuth2 password form data:
  - URL: `/api/v1/login/access-token`
  - form fields: `username`, `password`
- Protected routes use:
  - Header: `Authorization: Bearer <access_token>`
- JWT payload:
  - `sub` contains the user UUID as string
  - `exp` contains expiration
- Token algorithm: `HS256`
- Token expiry default: 8 days (`ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 8`)
- Role model:
  - `is_superuser: bool`
  - Some routes require active user only.
  - Admin routes require active superuser.

## How To Run Backend

Documented options in `README.md` and `Dockerfile`:

### With Docker Compose

From the wider project stack, the README points to `../development.md` and `docker compose watch`.

### Inside backend container

```bash
fastapi run --reload app/main.py
```

### Production container command

```bash
fastapi run --workers 4 app/main.py
```

### Local dependency setup

From `code/backend`:

```bash
uv sync
```

Then activate the virtual environment and run the FastAPI command.

## Backend Port

No explicit port is configured inside `code/backend`.

FastAPI CLI defaults to port `8000` unless overridden by command-line flags or outer Docker Compose configuration. Because this report is scoped to `code/backend`, project-level compose port mapping was not analyzed.

Expected local base URL if run directly:

```text
http://localhost:8000
```

API base path:

```text
http://localhost:8000/api/v1
```

## CORS

CORS is configured in `app/main.py` using `settings.all_cors_origins`.

`settings.all_cors_origins` is:

```python
[str(origin).rstrip("/") for origin in BACKEND_CORS_ORIGINS] + [FRONTEND_HOST]
```

Defaults:

- `FRONTEND_HOST = "http://localhost:5173"`
- `BACKEND_CORS_ORIGINS = []`

Current implication:

- Frontend on `http://localhost:5173` is allowed by default.
- Current Next frontend has been running on `http://localhost:3060`; this should be added through `FRONTEND_HOST` or `BACKEND_CORS_ORIGINS` before frontend integration.

## Required Environment Variables

Settings are loaded from `../.env`, one level above `code/backend`.

Required by `Settings` with no safe default:

- `PROJECT_NAME`
- `POSTGRES_SERVER`
- `POSTGRES_USER`
- `FIRST_SUPERUSER`
- `FIRST_SUPERUSER_PASSWORD`

Important optional/defaulted settings:

- `API_V1_STR`, default `/api/v1`
- `SECRET_KEY`, generated if not provided, but should be fixed in real deployments
- `ACCESS_TOKEN_EXPIRE_MINUTES`, default `11520`
- `FRONTEND_HOST`, default `http://localhost:5173`
- `ENVIRONMENT`, default `local`
- `BACKEND_CORS_ORIGINS`, default `[]`
- `POSTGRES_PORT`, default `5432`
- `POSTGRES_PASSWORD`, default empty string
- `POSTGRES_DB`, default empty string
- `SENTRY_DSN`, default `None`
- `SMTP_TLS`, default `True`
- `SMTP_SSL`, default `False`
- `SMTP_PORT`, default `587`
- `SMTP_HOST`, default `None`
- `SMTP_USER`, default `None`
- `SMTP_PASSWORD`, default `None`
- `EMAILS_FROM_EMAIL`, default `None`
- `EMAILS_FROM_NAME`, defaults to `PROJECT_NAME` if empty
- `EMAIL_RESET_TOKEN_EXPIRE_HOURS`, default `48`
- `EMAIL_TEST_USER`, default `test@example.com`

Security note:

- `SECRET_KEY`, `POSTGRES_PASSWORD`, and `FIRST_SUPERUSER_PASSWORD` must not be `"changethis"` outside local environment. In non-local environments, the app raises an error for those default values.

## Database And Migrations

- Engine is created in `app/core/db.py` from `settings.SQLALCHEMY_DATABASE_URI`.
- SQLAlchemy URI uses:
  - scheme `postgresql+psycopg`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`
  - `POSTGRES_SERVER`
  - `POSTGRES_PORT`
  - `POSTGRES_DB`
- Migrations live in `app/alembic/versions`.
- Startup script `scripts/prestart.sh`:
  1. waits for DB
  2. runs `alembic upgrade head`
  3. creates initial data/superuser

## Current Backend Domain Coverage

Available now:

- Authentication/login
- JWT token validation
- User signup
- User profile read/update/delete
- Password update
- Password recovery/reset
- Admin user CRUD
- Simple item CRUD
- Health check
- Email test route
- Local-only private user create route

Not present in `code/backend`:

- Trading market APIs
- Portfolio APIs
- AI signal APIs
- Risk scoring APIs
- eKYC APIs
- Upload CCCD/document APIs
- Face verification APIs
- Deepfake detection APIs
