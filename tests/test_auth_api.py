"""End-to-end tests for /auth/login, /auth/logout, /auth/session."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.services import user_service


@pytest.fixture
def client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def alice(db_session: Session, realm):
    return user_service.create_user(
        db_session, realm_id=realm.id, username="alice", password="password-123"
    )


def test_login_success_sets_cookie(client, alice) -> None:
    r = client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "alice"
    assert body["user"]["id"] == alice.id
    assert "session_exp" in body
    # Set-Cookie for SID must be present, HttpOnly.
    set_cookie = r.headers.get("set-cookie", "")
    assert "SID=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()


def test_login_wrong_password_returns_generic_error(client, alice) -> None:
    r = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_credentials"
    # Must NOT say "wrong password" vs "user not found" — generic by design.
    assert r.json()["error_description"] == "invalid username or password"


def test_login_unknown_user_returns_same_generic_error(client) -> None:
    r = client.post("/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_credentials"


def test_login_rate_limited(client, alice) -> None:
    for _ in range(10):
        client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    r = client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    assert r.status_code == 429
    assert r.json()["error"] == "rate_limited"
    assert r.headers.get("retry-after") == "60"


def test_session_endpoint_returns_false_without_cookie(client) -> None:
    r = client.get("/auth/session")
    assert r.status_code == 200
    assert r.json() == {"authenticated": False, "user": None, "session_exp": None}


def test_session_endpoint_returns_user_after_login(client, alice) -> None:
    login = client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    # The TestClient cookie jar stores Set-Cookie from the login response.
    r = client.get("/auth/session")
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is True
    assert body["user"]["username"] == "alice"


def test_logout_clears_cookie_and_revokes(client, alice) -> None:
    login = client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    sid_before = client.cookies.get("SID")
    assert sid_before

    r = client.post("/auth/logout")
    assert r.status_code == 204
    # Cookie jar should no longer send SID.
    assert client.cookies.get("SID") in (None, "")

    # Session endpoint should reflect logged-out state.
    r = client.get("/auth/session")
    assert r.json()["authenticated"] is False


def test_logout_without_session_is_idempotent(client) -> None:
    r = client.post("/auth/logout")
    assert r.status_code == 204


def test_session_endpoint_ignores_garbage_cookie(client) -> None:
    client.cookies.set("SID", "garbage-token-not-in-db")
    r = client.get("/auth/session")
    assert r.status_code == 200
    assert r.json()["authenticated"] is False