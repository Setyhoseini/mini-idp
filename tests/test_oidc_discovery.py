"""Tests for discovery and JWKS endpoints."""

from __future__ import annotations


def test_discovery_returns_required_fields(client) -> None:
    r = client.get("/.well-known/openid-configuration")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "issuer", "authorization_endpoint", "token_endpoint", "jwks_uri",
        "userinfo_endpoint", "response_types_supported",
        "code_challenge_methods_supported",
        "id_token_signing_alg_values_supported",
    ):
        assert key in body
    assert "code" in body["response_types_supported"]
    assert "S256" in body["code_challenge_methods_supported"]
    assert "RS256" in body["id_token_signing_alg_values_supported"]


def test_discovery_issuer_matches_settings(client) -> None:
    from app.config import get_settings

    r = client.get("/.well-known/openid-configuration")
    assert r.json()["issuer"] == get_settings().issuer


def test_jwks_returns_rs256_key(client) -> None:
    r = client.get("/.well-known/jwks.json")
    assert r.status_code == 200
    body = r.json()
    assert len(body["keys"]) == 1
    key = body["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert key["use"] == "sig"
    assert "n" in key and "e" in key