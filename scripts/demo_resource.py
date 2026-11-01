"""End-to-end demo: SSO across two clients → resource-server enforcement.

Requires BOTH servers running:
    uvicorn app.main:app --reload --port 8000
    uvicorn resource_server.main:app --reload --port 8001

Run:
    python scripts/demo_resource.py
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sys
from urllib.parse import parse_qs, urlparse

import httpx

IDP = "http://localhost:8000"
RS = "http://localhost:8001"


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


def get_tokens(session_client: httpx.Client, client_id: str, redirect_uri: str, scope: str) -> dict:
    verifier, challenge = pkce_pair()
    r = session_client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )
    if r.status_code != 302:
        raise RuntimeError(f"/authorize for {client_id} failed: {r.status_code} {r.text}")
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]

    r = session_client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    r.raise_for_status()
    return r.json()


def call(url: str, token: str) -> tuple[int, dict]:
    r = httpx.get(url, headers={"Authorization": f"Bearer {token}"})
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text}


def probe_servers() -> None:
    try:
        httpx.get(f"{IDP}/healthz", timeout=2).raise_for_status()
        httpx.get(f"{RS}/healthz", timeout=2).raise_for_status()
    except Exception as exc:
        print(f"ERROR: servers not reachable. Is both uvicorn running?\n  {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> int:
    probe_servers()

    # ---- Alice in 'sales' (orders.read) ----
    with httpx.Client(base_url=IDP, follow_redirects=False) as c:
        r = c.post("/auth/login", json={"username": "alice", "password": "alice-pass-123"})
        if r.status_code != 200:
            print(f"login failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        print("[1] logged in as alice (in 'sales' group → orders.read)")

        orders_tokens = get_tokens(
            c, "orders-ui", "http://localhost:3000/callback", "openid orders.read"
        )
        print(f"    alice orders-ui token scope:  {orders_tokens['scope']!r}")

        # SSO: same session, second client. Filter removes reports.read
        # because alice is not in the finance group.
        alice_reports_tokens = get_tokens(
            c, "reports-ui", "http://localhost:4000/callback", "openid reports.read"
        )
        print(f"    alice reports-ui token scope: {alice_reports_tokens['scope']!r}  (reports.read filtered)")

    # ---- Bob in 'finance' (reports.read) ----
    with httpx.Client(base_url=IDP, follow_redirects=False) as c:
        r = c.post("/auth/login", json={"username": "bob", "password": "bob-pass-123"})
        if r.status_code != 200:
            print(f"login failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        print("\n[2] logged in as bob (in 'finance' group → reports.read)")

        bob_reports_tokens = get_tokens(
            c, "reports-ui", "http://localhost:4000/callback", "openid reports.read"
        )
        print(f"    bob reports-ui token scope:   {bob_reports_tokens['scope']!r}")

    print("\n[3] Resource-server enforcement (port 8001):")

    s, _ = call(f"{RS}/api/orders", orders_tokens["access_token"])
    print(f"    alice's orders-ui token  → GET /api/orders   -> {s}   (expect 200: orders.read)")
    assert s == 200

    s, _ = call(f"{RS}/api/reports", orders_tokens["access_token"])
    print(f"    alice's orders-ui token  → GET /api/reports  -> {s}   (expect 403: no reports.read)")
    assert s == 403

    s, _ = call(f"{RS}/api/reports", alice_reports_tokens["access_token"])
    print(f"    alice's reports-ui token → GET /api/reports  -> {s}   (expect 403: alice lacks reports.read)")
    assert s == 403

    s, _ = call(f"{RS}/api/reports", bob_reports_tokens["access_token"])
    print(f"    bob's   reports-ui token → GET /api/reports  -> {s}   (expect 200: reports.read)")
    assert s == 200

    s, _ = call(f"{RS}/api/orders", bob_reports_tokens["access_token"])
    print(f"    bob's   reports-ui token → GET /api/orders   -> {s}   (expect 403: no orders.read)")
    assert s == 403

    print("\n[OK] demo complete — scope filtering + enforcement work end-to-end")
    return 0


if __name__ == "__main__":
    sys.exit(main())