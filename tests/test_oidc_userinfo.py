"""Tests for GET /userinfo."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.services import scope_service, user_service
from tests.conftest import make_pkce_pair


@pytest.fixture
def alice(db_session, realm):
    user = user_service.create_user(
        db_session,
        realm_id=realm.id,
        username="alice",
        password="password-123",
        email="alice@example.com",
        first_name="Alice",
    )
    return user


@pytest.fixture
def orders_ui(db_session, realm):
    from app.services import client_service

    return client_service.register_client(
        db_session,
        realm_id=realm.id,
        client_id="orders-ui",
        client_name="Orders UI",
        redirect_uris=["http://localhost:3000/callback"],
        allowed_scopes=["openid", "profile", "email"],
        is_public=True,
    )[0]


def _get_access_token(client, challenge: str, verifier: str) -> str:
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "orders-ui",
            "redirect_uri": "http://localhost:3000/callback",
            "scope": "openid profile email",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    r = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": "orders-ui",
            "code_verifier": verifier,
        },
    )
    return r.json()["access_token"]


def test_userinfo_returns_sub(client, alice, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    access = _get_access_token(client, challenge, verifier)

    r = client.get("/userinfo", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    body = r.json()
    assert body["sub"] == str(alice.id)


def test_userinfo_requires_bearer(client) -> None:
    r = client.get("/userinfo")
    assert r.status_code == 401


def test_userinfo_includes_profile_and_email_when_scoped(client, alice, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    access = _get_access_token(client, challenge, verifier)

    r = client.get("/userinfo", headers={"Authorization": f"Bearer {access}"})
    body = r.json()
    assert body["preferred_username"] == "alice"
    assert body.get("email") == "alice@example.com"