"""Tests for GET /authorize (redirect behavior, validation, scope filtering)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.services import user_service
from tests.conftest import make_pkce_pair


@pytest.fixture
def alice(db_session, realm):
    return user_service.create_user(
        db_session, realm_id=realm.id, username="alice", password="password-123"
    )


@pytest.fixture
def orders_ui(db_session, realm):
    from app.services import client_service

    return client_service.register_client(
        db_session,
        realm_id=realm.id,
        client_id="orders-ui",
        client_name="Orders UI",
        redirect_uris=["http://localhost:3000/callback"],
        allowed_scopes=["openid", "profile", "email", "orders.read", "orders.write"],
        is_public=True,
    )[0]


def _authorize_params(redirect_uri: str) -> dict:
    _, challenge = make_pkce_pair()
    return {
        "response_type": "code",
        "client_id": "orders-ui",
        "redirect_uri": redirect_uri,
        "scope": "openid orders.read",
        "state": "xyz",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }


def test_authorize_redirects_to_login_without_session(client, orders_ui) -> None:
    r = client.get(
        "/authorize",
        params=_authorize_params("http://localhost:3000/callback"),
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"].startswith("/login?return_to=")


def test_authorize_rejects_unknown_client(client, alice) -> None:
    params = _authorize_params("http://localhost:3000/callback")
    params["client_id"] = "does-not-exist"
    r = client.get("/authorize", params=params, follow_redirects=False)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client"


def test_authorize_rejects_bad_redirect_uri(client, orders_ui) -> None:
    r = client.get(
        "/authorize",
        params=_authorize_params("http://evil.example/cb"),
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "redirect_uri" in r.json()["error_description"]


def test_authorize_rejects_unsupported_response_type(client, orders_ui) -> None:
    params = _authorize_params("http://localhost:3000/callback")
    params["response_type"] = "token"
    r = client.get("/authorize", params=params, follow_redirects=False)
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_response_type"


def test_authorize_requires_pkce(client, orders_ui) -> None:
    params = _authorize_params("http://localhost:3000/callback")
    del params["code_challenge"]
    r = client.get("/authorize", params=params, follow_redirects=False)
    assert r.status_code == 400
    assert "code_challenge" in r.json()["error_description"]


def test_authorize_issues_code_with_session(client, alice, orders_ui) -> None:
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    r = client.get(
        "/authorize",
        params=_authorize_params("http://localhost:3000/callback"),
        follow_redirects=False,
    )
    assert r.status_code == 302
    location = r.headers["location"]
    parsed = urlparse(location)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == "http://localhost:3000/callback"
    qs = parse_qs(parsed.query)
    assert "code" in qs and qs["code"][0]
    assert qs["state"][0] == "xyz"


def test_authorize_filters_scopes_by_effective(client, db_session, alice, orders_ui, realm) -> None:
    """Alice has no orders.read → the code must contain only granted scopes."""
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})
    r = client.get(
        "/authorize",
        params=_authorize_params("http://localhost:3000/callback"),
        follow_redirects=False,
    )
    assert r.status_code == 302
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    from sqlalchemy import select
    from app.models import AuthorizationCode
    row = db_session.execute(
        select(AuthorizationCode).where(AuthorizationCode.code_hash.isnot(None))
    ).scalars().all()
    # The most recently created code holds the filtered scopes.
    row = row[-1]
    assert "orders.read" not in row.scopes
    assert "openid" in row.scopes
    assert code  # presence check