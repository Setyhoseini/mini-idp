"""End-to-end SSO + scope-change demo.

Run with the dev server already running on http://localhost:8000.
"""

import base64
import hashlib
import secrets
import sys

import httpx

BASE = "http://localhost:8000"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def main() -> int:
    # 1. Login as alice — get session cookie
    with httpx.Client(base_url=BASE, follow_redirects=False) as c:
        r = c.post("/auth/login", json={"username": "alice", "password": "alice-pass-123"})
        assert r.status_code == 200, r.text
        print(f"[1] logged in as alice: session cookie set")

        for client_pk, redirect_uri, scope in [
            ("orders-ui", "http://localhost:3000/callback", "openid orders.read"),
            ("reports-ui", "http://localhost:4000/callback", "openid reports.read"),
        ]:
            verifier, challenge = pkce_pair()
            r = c.get(
                "/authorize",
                params={
                    "response_type": "code",
                    "client_id": client_pk,
                    "redirect_uri": redirect_uri,
                    "scope": scope,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
            )
            assert r.status_code == 302, r.text
            code = r.headers["location"].split("code=")[1].split("&")[0]
            print(f"[2] authorized {client_pk}: code={code[:16]}...")

            r = c.post(
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
            tokens = r.json()
            print(f"    tokens for {client_pk}: scope={tokens['scope']!r}")
            print(f"    id_token present: {bool(tokens.get('id_token'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())