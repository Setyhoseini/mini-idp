"""Tests for POST /token — code exchange."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.services import group_service, scope_service, user_service
from tests.conftest import make_pkce_pair


@pytest.fixture
def alice_with_orders(db_session, realm):
    user = user_service.create_user(
        db_session, realm_id=realm.id, username="alice", password="password-123"
    )
    scope = scope_service.create_scope(db_session, realm_id=realm.id, name="orders.read")
    user_service.grant_scope_to_user(db_session, user_id=user.id, scope_id=scope.id)
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
        allowed_scopes=["openid", "profile", "email", "orders.read"],
        is_public=True,
    )[0]


def _authorize_and_get_code(client, alice, code_challenge: str) -> str:
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "orders-ui",
            "redirect_uri": "http://localhost:3000/callback",
            "scope": "openid orders.read",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    return parse_qs(urlparse(r.headers["location"]).query)["code"][0]


def test_code_exchange_issues_tokens(client, alice_with_orders, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    code = _authorize_and_get_code(client, alice_with_orders, challenge)

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
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["id_token"]
    assert body["refresh_token"]
    assert "orders.read" in body["scope"].split()
    assert "openid" in body["scope"].split()


def test_code_exchange_rejects_wrong_verifier(client, alice_with_orders, orders_ui) -> None:
    _, challenge = make_pkce_pair()
    wrong_verifier, _ = make_pkce_pair()
    code = _authorize_and_get_code(client, alice_with_orders, challenge)

    r = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": "orders-ui",
            "code_verifier": wrong_verifier,
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"
    assert "PKCE" in r.json()["error_description"]


def test_code_exchange_rejects_reused_code(client, alice_with_orders, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    code = _authorize_and_get_code(client, alice_with_orders, challenge)

    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "http://localhost:3000/callback",
        "client_id": "orders-ui",
        "code_verifier": verifier,
    }
    r1 = client.post("/token", data=body)
    assert r1.status_code == 200
    r2 = client.post("/token", data=body)
    assert r2.status_code == 400
    assert "already redeemed" in r2.json()["error_description"]


def test_code_exchange_rejects_wrong_redirect_uri(client, alice_with_orders, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    code = _authorize_and_get_code(client, alice_with_orders, challenge)

    r = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:3000/other",
            "client_id": "orders-ui",
            "code_verifier": verifier,
        },
    )
    assert r.status_code == 400
    assert "redirect_uri" in r.json()["error_description"]


def test_code_exchange_rejects_after_session_revoked(client, alice_with_orders, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    code = _authorize_and_get_code(client, alice_with_orders, challenge)
    # Logout → session revoked → code cannot be consumed
    client.post("/auth/logout")

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
    assert r.status_code == 400
    assert "session" in r.json()["error_description"].lower()


def test_token_rejects_unsupported_grant_type(client, alice_with_orders, orders_ui) -> None:
    r = client.post(
        "/token",
        data={"grant_type": "password", "client_id": "orders-ui"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_grant_type"