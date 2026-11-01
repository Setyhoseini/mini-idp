"""Tests for password hashing and JWT signing."""

from __future__ import annotations

import pytest

from app.security.jwt_signer import JwtSigner, get_jwt_signer
from app.security.passwords import hash_password, needs_rehash, verify_password


# ---------- passwords ----------

def test_password_roundtrip() -> None:
    h = hash_password("hunter2")
    assert h != "hunter2"  # obviously, but pins the assumption
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_hash_is_salted() -> None:
    """Two hashes of the same password must differ (random salt)."""
    assert hash_password("hunter2") != hash_password("hunter2")


def test_needs_rehash_false_for_current_params() -> None:
    assert needs_rehash(hash_password("hunter2")) is False


# ---------- JWT ----------

def test_jwt_sign_and_verify() -> None:
    signer = get_jwt_signer()
    token = signer.sign({"sub": "user-123", "scope": "openid"}, ttl_seconds=60)
    claims = signer.verify(token)
    assert claims["sub"] == "user-123"
    assert claims["scope"] == "openid"
    assert claims["iss"] == "http://localhost:8000"


def test_jwt_rejects_tampered_token() -> None:
    signer = get_jwt_signer()
    token = signer.sign({"sub": "user-123"}, ttl_seconds=60)
    # Flip a character in the signature segment.
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(Exception):
        signer.verify(tampered)


def test_jwt_jwks_contains_public_key() -> None:
    signer = get_jwt_signer()
    jwks = signer.jwks()
    assert len(jwks["keys"]) == 1
    jwk = jwks["keys"][0]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RS256"
    assert jwk["use"] == "sig"
    assert jwk["kid"] == signer.kid
    assert "n" in jwk and "e" in jwk