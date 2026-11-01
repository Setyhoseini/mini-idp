"""Tests for the demo resource server."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.security.jwt_signer import JwtSigner, get_jwt_signer
from resource_server.deps import get_jwks_client
from resource_server.main import app as rs_app


class _FakeJWKClient:
    """Mimics PyJWKClient: returns the same public key regardless of kid.

    The real client parses the JWT header's kid and selects the matching key
    from a cached JWKS. In tests there's only one key, so the lookup is trivial.
    """

    def __init__(self) -> None:
        self._pem = get_jwt_signer()._public_pem  # bytes

    def get_signing_key_from_jwt(self, _token: str) -> SimpleNamespace:
        return SimpleNamespace(key=self._pem)


@pytest.fixture
def rs_client():
    rs_app.dependency_overrides[get_jwks_client] = lambda: _FakeJWKClient()
    with TestClient(rs_app) as c:
        yield c
    rs_app.dependency_overrides.clear()


def _token(scope: str = "openid orders.read", sub: str = "1", ttl: int = 60) -> str:
    return get_jwt_signer().sign({"sub": sub, "scope": scope, "aud": "orders-ui"}, ttl_seconds=ttl)


# ---------- health ----------

def test_healthz_is_public(rs_client) -> None:
    r = rs_client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- auth failures ----------

def test_orders_requires_bearer(rs_client) -> None:
    r = rs_client.get("/api/orders")
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_request"
    assert r.headers["www-authenticate"].startswith("Bearer")


def test_expired_token_rejected(rs_client) -> None:
    r = rs_client.get("/api/orders", headers={"Authorization": f"Bearer {_token(ttl=-10)}"})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_token"
    assert "expired" in r.json()["error_description"].lower()


def test_wrong_issuer_rejected(rs_client) -> None:
    s = get_settings()
    other = JwtSigner(
        private_key_path=s.private_key_path,
        public_key_path=s.public_key_path,
        issuer="http://wrong-issuer.example",
    )
    token = other.sign({"sub": "1", "scope": "orders.read"}, ttl_seconds=60)
    r = rs_client.get("/api/orders", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "iss" in r.json()["error_description"].lower() or "issuer" in r.json()["error_description"].lower()


def test_tampered_signature_rejected(rs_client) -> None:
    token = _token()
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    r = rs_client.get("/api/orders", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


# ---------- scope enforcement ----------

def test_orders_succeeds_with_orders_read(rs_client) -> None:
    r = rs_client.get(
        "/api/orders", headers={"Authorization": f"Bearer {_token(scope='openid orders.read')}"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sub"] == "1"
    assert len(body["orders"]) == 2


def test_orders_rejected_without_scope(rs_client) -> None:
    r = rs_client.get(
        "/api/orders", headers={"Authorization": f"Bearer {_token(scope='openid admin')}"}
    )
    assert r.status_code == 403
    assert r.json()["error"] == "insufficient_scope"
    assert "orders.read" in r.json()["error_description"]


def test_create_order_requires_orders_write(rs_client) -> None:
    r = rs_client.post(
        "/api/orders", headers={"Authorization": f"Bearer {_token(scope='orders.read')}"}
    )
    assert r.status_code == 403

    r = rs_client.post(
        "/api/orders", headers={"Authorization": f"Bearer {_token(scope='orders.write')}"}
    )
    assert r.status_code == 200
    assert r.json()["created"] is True


def test_reports_requires_reports_read(rs_client) -> None:
    r = rs_client.get(
        "/api/reports", headers={"Authorization": f"Bearer {_token(scope='orders.read')}"}
    )
    assert r.status_code == 403

    r = rs_client.get(
        "/api/reports", headers={"Authorization": f"Bearer {_token(scope='reports.read')}"}
    )
    assert r.status_code == 200
    assert r.json()["sub"] == "1"