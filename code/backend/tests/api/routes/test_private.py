from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import User


def test_create_user(client: TestClient, db: Session) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json={
            "email": "pollo@listo.com",
            "password": "password123",
            "full_name": "Pollo Listo",
        },
    )

    assert r.status_code == 200

    data = r.json()
    assert "hashed_password" not in data
    assert "password" not in data

    user = db.exec(select(User).where(User.id == data["id"])).first()

    assert user
    assert user.email == "pollo@listo.com"
    assert user.full_name == "Pollo Listo"


def test_create_user_existing_email(client: TestClient) -> None:
    payload = {
        "email": "duplicate@listo.com",
        "password": "password123",
        "full_name": "Duplicate User",
    }
    first_response = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json=payload,
    )
    duplicate_response = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json=payload,
    )

    assert first_response.status_code == 200
    assert duplicate_response.status_code == 400
    assert duplicate_response.json() == {
        "detail": "The user with this email already exists in the system."
    }


def test_create_user_invalid_email(client: TestClient) -> None:
    r = client.post(
        f"{settings.API_V1_STR}/private/users/",
        json={
            "email": "not-an-email",
            "password": "password123",
            "full_name": "Invalid Email",
        },
    )

    assert r.status_code == 422
