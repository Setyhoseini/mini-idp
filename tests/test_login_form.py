"""HTML login form tests."""

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


def test_login_form_renders(client) -> None:
    r = client.get("/login")
    assert r.status_code == 200
    assert "Sign in to mini-idp" in r.text
    assert 'name="username"' in r.text
    assert 'name="password"' in r.text


def test_login_form_passes_return_to_into_hidden_field(client) -> None:
    r = client.get("/login?return_to=/authorize?client_id=orders-ui")
    assert 'name="return_to" value="/authorize?client_id=orders-ui"' in r.text


def test_form_login_success_redirects_and_sets_cookie(client, alice) -> None:
    r = client.post(
        "/login",
        data={"username": "alice", "password": "password-123", "return_to": "/somewhere"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/somewhere"
    assert "SID=" in r.headers.get("set-cookie", "")


def test_form_login_rejects_open_redirect(client, alice) -> None:
    r = client.post(
        "/login",
        data={"username": "alice", "password": "password-123", "return_to": "https://evil.example/x"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"  # sanitized

    r2 = client.post(
        "/login",
        data={"username": "alice", "password": "password-123", "return_to": "//evil.example/x"},
        follow_redirects=False,
    )
    assert r2.headers["location"] == "/"


def test_form_login_wrong_password_returns_401_and_error(client, alice) -> None:
    r = client.post(
        "/login",
        data={"username": "alice", "password": "wrong", "return_to": "/x"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert "Invalid username or password" in r.text