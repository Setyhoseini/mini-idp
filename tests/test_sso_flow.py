"""End-to-end SSO and permission-propagation tests."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.services import client_service, group_service, scope_service, user_service
from tests.conftest import make_pkce_pair


@pytest.fixture
def alice(db_session, realm):
    return user_service.create_user(
        db_session, realm_id=realm.id, username="alice", password="password-123"
    )


@pytest.fixture
def sales_and_finance(db_session, realm):
    sales = group_service.create_group(db_session, realm_id=realm.id, name="sales")
    finance = group_service.create_group(db_session, realm_id=realm.id, name="finance")
    orders = scope_service.create_scope(db_session, realm_id=realm.id, name="orders.read")
    reports = scope_service.create_scope(db_session, realm_id=realm.id, name="reports.read")
    group_service.grant_scope_to_group(db_session, group_id=sales.id, scope_id=orders.id)
    group_service.grant_scope_to_group(db_session, group_id=finance.id, scope_id=reports.id)
    return {"sales": sales, "finance": finance, "orders": orders, "reports": reports}


@pytest.fixture
def two_clients(db_session, realm):
    orders_ui = client_service.register_client(
        db_session, realm_id=realm.id, client_id="orders-ui", client_name="Orders UI",
        redirect_uris=["http://localhost:3000/callback"],
        allowed_scopes=["openid", "orders.read"], is_public=True,
    )[0]
    reports_ui = client_service.register_client(
        db_session, realm_id=realm.id, client_id="reports-ui", client_name="Reports UI",
        redirect_uris=["http://localhost:4000/callback"],
        allowed_scopes=["openid", "reports.read"], is_public=True,
    )[0]
    return orders_ui, reports_ui


def _get_code(client, client_pk: str, redirect_uri: str, scope: str) -> tuple[str, str]:
    _, challenge = make_pkce_pair()
    verifier, challenge = _regenerate(challenge)
    r = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_pk,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    return code, verifier


def _regenerate(_old: str) -> tuple[str, str]:
    return make_pkce_pair()


def _exchange(client, code: str, verifier: str, redirect_uri: str, client_pk: str) -> dict:
    r = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_pk,
            "code_verifier": verifier,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_sso_two_clients_one_login(client, db_session, alice, sales_and_finance, two_clients) -> None:
    """Log in once; authorize against orders-ui AND reports-ui without re-authing."""
    group_service.add_member(db_session, group_id=sales_and_finance["sales"].id, user_id=alice.id)
    group_service.add_member(db_session, group_id=sales_and_finance["finance"].id, user_id=alice.id)

    client.post("/auth/login", json={"username": "alice", "password": "password-123"})

    # First authorize for orders-ui (no new login)
    code1, v1 = _get_code(client, "orders-ui", "http://localhost:3000/callback", "openid orders.read")
    t1 = _exchange(client, code1, v1, "http://localhost:3000/callback", "orders-ui")
    assert "orders.read" in t1["scope"].split()

    # Second authorize for reports-ui (still no new login — session is enough)
    code2, v2 = _get_code(client, "reports-ui", "http://localhost:4000/callback", "openid reports.read")
    t2 = _exchange(client, code2, v2, "http://localhost:4000/callback", "reports-ui")
    assert "reports.read" in t2["scope"].split()

    # Both tokens were issued during the same session, no re-authentication.
    assert t1["access_token"] != t2["access_token"]


def test_group_change_affects_new_tokens(client, db_session, alice, sales_and_finance, two_clients) -> None:
    """Move alice sales→finance; her new orders-ui token loses orders.read."""
    group_service.add_member(db_session, group_id=sales_and_finance["sales"].id, user_id=alice.id)
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})

    code1, v1 = _get_code(client, "orders-ui", "http://localhost:3000/callback", "openid orders.read")
    t1 = _exchange(client, code1, v1, "http://localhost:3000/callback", "orders-ui")
    assert "orders.read" in t1["scope"].split()

    # Move alice out of sales, into finance
    group_service.remove_member(db_session, group_id=sales_and_finance["sales"].id, user_id=alice.id)
    group_service.add_member(db_session, group_id=sales_and_finance["finance"].id, user_id=alice.id)

    # Re-authorize orders-ui (same session). orders.read should now be filtered.
    code2, v2 = _get_code(client, "orders-ui", "http://localhost:3000/callback", "openid orders.read")
    t2 = _exchange(client, code2, v2, "http://localhost:3000/callback", "orders-ui")
    assert "orders.read" not in t2["scope"].split()


def test_refresh_rotation(client, db_session, alice, sales_and_finance, two_clients) -> None:
    """Refresh token is single-use and rotated on each refresh."""
    group_service.add_member(db_session, group_id=sales_and_finance["sales"].id, user_id=alice.id)
    client.post("/auth/login", json={"username": "alice", "password": "password-123"})

    code, v = _get_code(client, "orders-ui", "http://localhost:3000/callback", "openid orders.read")
    t = _exchange(client, code, v, "http://localhost:3000/callback", "orders-ui")
    old_refresh = t["refresh_token"]

    r = client.post(
        "/token",
        data={"grant_type": "refresh_token", "refresh_token": old_refresh, "client_id": "orders-ui"},
    )
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Old token cannot be reused (rotation revoked it)
    r = client.post(
        "/token",
        data={"grant_type": "refresh_token", "refresh_token": old_refresh, "client_id": "orders-ui"},
    )
    assert r.status_code == 400