"""Tests for /introspect and /revoke."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.services import client_service, scope_service, user_service
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
    return client_service.register_client(
        db_session,
        realm_id=realm.id,
        client_id="orders-ui",
        client_name="Orders UI",
        redirect_uris=["http://localhost:3000/callback"],
        allowed_scopes=["openid", "orders.read"],
        is_public=True,
    )[0]


def _issue_tokens(client, challenge: str, verifier: str) -> dict:
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": "orders-ui",
            "redirect_uri": "http://localhost:3000/callback",
            "scope": "openid orders.read",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    return client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:3000/callback",
            "client_id": "orders-ui",
            "code_verifier": verifier,
        },
    ).json()


def test_introspect_active_token(client, alice_with_orders, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    tokens = _issue_tokens(client, challenge, verifier)

    r = client.post(
        "/introspect",
        data={"token": tokens["access_token"], "client_id": "orders-ui"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["client_id"] == "orders-ui"
    assert "orders.read" in body["scope"].split()


def test_introspect_inactive_token(client, orders_ui) -> None:
    r = client.post(
        "/introspect",
        data={"token": "not-a-real-token", "client_id": "orders-ui"},
    )
    assert r.status_code == 200
    assert r.json()["active"] is False


def test_revoke_refresh_token(client, alice_with_orders, orders_ui) -> None:
    verifier, challenge = make_pkce_pair()
    tokens = _issue_tokens(client, challenge, verifier)
    refresh = tokens["refresh_token"]

    r = client.post("/revoke", data={"token": refresh, "client_id": "orders-ui"})
    assert r.status_code == 200

    r = client.post(
        "/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": "orders-ui",
        },
    )
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


def test_revoke_unknown_token_is_idempotent(client, orders_ui) -> None:
    r = client.post("/revoke", data={"token": "garbage", "client_id": "orders-ui"})
    assert r.status_code == 200