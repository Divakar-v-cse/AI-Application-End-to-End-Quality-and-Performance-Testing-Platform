"""Authentication: token issuance, rejection paths and validation errors."""
from __future__ import annotations

import pytest

from app.config import settings


def test_login_returns_bearer_token_and_profile(client):
    response = client.post(
        "/api/auth/login",
        json={"email": settings.demo_user_email, "password": settings.demo_user_password},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["expires_in"] == settings.token_ttl_minutes * 60
    assert payload["user"]["email"] == settings.demo_user_email
    assert payload["user"]["role"]
    assert "password" not in payload["user"]
    assert "password_hash" not in payload["user"]


def test_login_is_case_insensitive_for_email(client):
    response = client.post(
        "/api/auth/login",
        json={"email": settings.demo_user_email.upper(), "password": settings.demo_user_password},
    )

    assert response.status_code == 200, response.text


def test_login_rejects_wrong_password(client):
    response = client.post(
        "/api/auth/login", json={"email": settings.demo_user_email, "password": "wrong-pass"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers["www-authenticate"] == "Bearer"


def test_login_rejects_unknown_email_with_the_same_message(client):
    response = client.post(
        "/api/auth/login", json={"email": "nobody@example.com", "password": settings.demo_user_password}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.parametrize(
    "payload, missing_field",
    [
        ({"password": "Passw0rd!"}, "email"),
        ({"email": "qa@example.com"}, "password"),
    ],
)
def test_login_validation_names_the_missing_field(client, payload, missing_field):
    response = client.post("/api/auth/login", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail, "validation errors must be itemised"
    assert detail[0]["loc"][-1] == missing_field


def test_login_rejects_malformed_email(client):
    response = client.post("/api/auth/login", json={"email": "not-an-email", "password": "Passw0rd!"})

    assert response.status_code == 422


def test_login_rejects_over_long_password(client):
    response = client.post(
        "/api/auth/login", json={"email": settings.demo_user_email, "password": "x" * 129}
    )

    assert response.status_code == 422


def test_me_requires_a_token(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer not-a-real-token", "Basic abc", "Bearer "])
def test_me_rejects_malformed_credentials(client, header):
    response = client.get("/api/auth/me", headers={"Authorization": header})

    assert response.status_code == 401


def test_me_returns_the_authenticated_identity(client, auth):
    response = client.get("/api/auth/me", headers=auth)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["email"] == settings.demo_user_email
    assert payload["is_active"] is True


def test_logout_acknowledges_the_caller(client, auth):
    response = client.post("/api/auth/logout", headers=auth)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert settings.demo_user_email in payload["message"]


def test_logout_requires_a_token(client):
    assert client.post("/api/auth/logout").status_code == 401
