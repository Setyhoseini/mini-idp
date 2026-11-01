"""RS256 JWT signing and verification, plus JWKS export."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives import serialization

from app.config import Settings, get_settings


class JwtSigner:
    """Signs and verifies JWTs with an RS256 keypair loaded from disk."""

    def __init__(
        self,
        private_key_path: str | Path,
        public_key_path: str | Path,
        issuer: str,
        algorithm: str = "RS256",
    ) -> None:
        self._private_pem = Path(private_key_path).read_bytes()
        self._public_pem = Path(public_key_path).read_bytes()
        self._issuer = issuer
        self._algorithm = algorithm
        # Stable `kid` derived from the public key bytes — same across restarts,
        # different if the keypair is regenerated.
        self._kid = hashlib.sha256(self._public_pem).hexdigest()[:16]

    @classmethod
    def from_settings(cls, settings: Settings) -> "JwtSigner":
        return cls(
            private_key_path=settings.private_key_path,
            public_key_path=settings.public_key_path,
            issuer=settings.issuer,
        )

    @property
    def kid(self) -> str:
        return self._kid

    def sign(self, claims: dict, ttl_seconds: int) -> str:
        """Sign `claims` with `iss`, `iat`, `exp` added automatically."""
        now = datetime.now(timezone.utc)
        payload = {
            **claims,
            "iss": self._issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        }
        return jwt.encode(
            payload,
            self._private_pem,
            algorithm=self._algorithm,
            headers={"kid": self._kid},
        )

    def verify(self, token: str, audience: str | None = None) -> dict:
        """Verify signature, `iss`, `exp`. If `audience` is given, also `aud`."""
        return jwt.decode(
            token,
            self._public_pem,
            algorithms=[self._algorithm],
            audience=audience,
            issuer=self._issuer,
            options={"verify_aud": audience is not None},
        )

    def public_jwk(self) -> dict:
        """Return the public key as a JWK (for /.well-known/jwks.json)."""
        public_key = serialization.load_pem_public_key(self._public_pem)
        jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
        jwk.update({"kid": self._kid, "use": "sig", "alg": self._algorithm})
        return jwk

    def jwks(self) -> dict:
        """Return a JWKS document containing the public key."""
        return {"keys": [self.public_jwk()]}


@lru_cache
def get_jwt_signer() -> JwtSigner:
    """Process-wide singleton signer built from Settings."""
    return JwtSigner.from_settings(get_settings())