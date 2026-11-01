"""End-to-end tests for the first protected admin endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.security.jwt_signer import get_jwt_signer
from app.services import group_service, scope_service, user_service


@pytest.fixture
def client(db_session: Session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(admin_user):
    signer = get_jwt_signer()
    return signer.sign(
        {"sub": str(admin_user.id), "scope": "openid admin"},
        ttl_seconds=60,
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------- POST /admin/v1/users ----------

def test_create_user_requires_auth(client) -> None:
    r = client.post("/admin/v1/users", json={"username": "alice", "password": "password-123"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_request"
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_create_user_with_malformed_header(client) -> None:
    r = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "password-123"},
        headers={"Authorization": "Basic abc"},
    )
    assert r.status_code == 401


def test_create_user_success(client, admin_token) -> None:
    r = client.post(
        "/admin/v1/users",
        json={
            "username": "alice",
            "password": "password-123",
            "email": "alice@example.com",
            "first_name": "Alice",
        },
        headers=_auth(admin_token),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"
    assert body["first_name"] == "Alice"
    assert body["enabled"] is True
    assert "id" in body
    # Critical: no password material leaks.
    assert "password_hash" not in body
    assert "password" not in body


def test_create_user_duplicate_returns_409(client, admin_token) -> None:
    r1 = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "password-123"},
        headers=_auth(admin_token),
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "password-123"},
        headers=_auth(admin_token),
    )
    assert r2.status_code == 409
    assert r2.json()["error"] == "duplicate_username"


def test_create_user_short_password_returns_422(client, admin_token) -> None:
    r = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "short"},
        headers=_auth(admin_token),
    )
    assert r.status_code == 422


def test_create_user_insufficient_scope(client, admin_user) -> None:
    signer = get_jwt_signer()
    token = signer.sign({"sub": str(admin_user.id), "scope": "openid"}, ttl_seconds=60)
    r = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "password-123"},
        headers=_auth(token),
    )
    assert r.status_code == 403
    assert r.json()["error"] == "insufficient_scope"


def test_expired_token_rejected(client, admin_user) -> None:
    signer = get_jwt_signer()
    token = signer.sign(
        {"sub": str(admin_user.id), "scope": "openid admin"},
        ttl_seconds=-10,  # exp is already in the past
    )
    r = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "password-123"},
        headers=_auth(token),
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"


def test_disabled_admin_rejected(client, db_session, admin_user) -> None:
    admin_user.enabled = False
    db_session.commit()
    signer = get_jwt_signer()
    token = signer.sign({"sub": str(admin_user.id), "scope": "openid admin"}, ttl_seconds=60)
    r = client.post(
        "/admin/v1/users",
        json={"username": "alice", "password": "password-123"},
        headers=_auth(token),
    )
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"


# ---------- GET /admin/v1/users/{id}/effective-scopes ----------

def test_effective_scopes_success(client, db_session, admin_token, admin_user, realm) -> None:
    """The flagship integration test: the resolver works over HTTP."""
    # Give admin_user a group-derived scope in addition to the direct admin scope.
    g = group_service.create_group(db_session, realm_id=realm.id, name="sales")
    s = scope_service.create_scope(db_session, realm_id=realm.id, name="orders.read")
    group_service.add_member(db_session, group_id=g.id, user_id=admin_user.id)
    group_service.grant_scope_to_group(db_session, group_id=g.id, scope_id=s.id)

    r = client.get(
        f"/admin/v1/users/{admin_user.id}/effective-scopes",
        headers=_auth(admin_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == admin_user.id
    assert body["username"] == "admin"
    # Both the direct grant and the group-derived scope must appear.
    assert body["scopes"] == ["admin", "orders.read"]  # sorted → deterministic


def test_effective_scopes_unknown_user_returns_404(client, admin_token) -> None:
    r = client.get(
        "/admin/v1/users/99999/effective-scopes",
        headers=_auth(admin_token),
    )
    assert r.status_code == 404
    assert r.json()["error"] == "user_not_found"


def test_effective_scopes_requires_auth(client, admin_user) -> None:
    r = client.get(f"/admin/v1/users/{admin_user.id}/effective-scopes")
    assert r.status_code == 401