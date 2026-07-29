from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session


def _is_scripts_only(args: list[str]) -> bool:
    if not args:
        return False
    return all(arg.replace("\\", "/").startswith("tests/scripts") for arg in args)


def _ensure_test_database() -> None:
    from app.core.config import settings

    db_name = settings.POSTGRES_DB.lower()
    if db_name.endswith("_test") or db_name.startswith("test_"):
        return

    pytest.exit(
        "Refusing to run backend tests against non-test database "
        f"{settings.POSTGRES_DB!r}. Set POSTGRES_DB to a test database "
        "(for example 'app_test') before running pytest.",
        returncode=2,
    )


def pytest_configure(config: pytest.Config) -> None:
    if _is_scripts_only(list(config.args)):
        return
    _ensure_test_database()


@pytest.fixture(scope="session", autouse=True)
def db(request: pytest.FixtureRequest) -> Generator[Session, None, None]:
    if all(item.nodeid.startswith("tests/scripts/") for item in request.session.items):
        yield
        return

    _ensure_test_database()

    from sqlmodel import delete

    from app.core.db import engine, init_db
    from app.models import User

    with Session(engine) as session:
        init_db(session)
        yield session
        statement = delete(User)
        session.execute(statement)
        session.commit()


@pytest.fixture(scope="module")
def client(db: Session) -> Generator[TestClient, None, None]:
    from app.api.deps import get_db
    from app.main import app

    def _get_test_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    from tests.utils.utils import get_superuser_token_headers

    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    from app.core.config import settings
    from tests.utils.user import authentication_token_from_email

    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
