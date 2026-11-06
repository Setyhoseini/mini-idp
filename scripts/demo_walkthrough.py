"""Assignment walkthrough — reproduce every claim as PASS/FAIL.

Prerequisites: both uvicorn servers running (IdP on 8000, RS on 8001),
and bootstrap already executed once (python scripts/bootstrap.py).

Usage:
    python scripts/demo_walkthrough.py
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

IDP = "http://localhost:8000"
RS = "http://localhost:8001"


# ---------- helpers ----------

def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


class Checker:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  [PASS] {label}")
        else:
            self.failed += 1
            suffix = f" — {detail}" if detail else ""
            print(f"  [FAIL] {label}{suffix}")
        return condition

    def section(self, title: str) -> None:
        print(f"\n{title}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"{self.passed}/{total} checks passed")
        if self.failed:
            print(f"{self.failed} FAILED — see above.")
            return 1
        print("ALL CHECKS PASSED")
        return 0


def reset_alice_to_sales() -> tuple[int, int, int]:
    """Put alice back into the sales group only. Returns (alice_id, sales_id, finance_id)."""
    from sqlalchemy import select

    from app.config import get_settings  # noqa: F401  (ensures settings load)
    from app.db import SessionLocal
    from app.models import Group
    from app.services import group_service, realm_service, user_service

    with SessionLocal() as db:
        realm = realm_service.get_single_realm(db)
        alice = user_service.get_user_by_username(db, realm_id=realm.id, username="alice")
        sales = db.execute(
            select(Group).where(Group.realm_id == realm.id, Group.name == "sales")
        ).scalar_one()
        finance = db.execute(
            select(Group).where(Group.realm_id == realm.id, Group.name == "finance")
        ).scalar_one()
        group_service.remove_member(db, group_id=finance.id, user_id=alice.id)
        group_service.add_member(db, group_id=sales.id, user_id=alice.id)
        return alice.id, sales.id, finance.id


def move_alice_to_finance(alice_id: int, sales_id: int, finance_id: int) -> None:
    from app.db import SessionLocal
    from app.services import group_service

    with SessionLocal() as db:
        group_service.remove_member(db, group_id=sales_id, user_id=alice_id)
        group_service.add_member(db, group_id=finance_id, user_id=alice_id)


def probe_servers() -> bool:
    try:
        httpx.get(f"{IDP}/healthz", timeout=3).raise_for_status()
        httpx.get(f"{RS}/healthz", timeout=3).raise_for_status()
        return True
    except Exception as exc:
        print(f"ERROR: servers not reachable — {exc}", file=sys.stderr)
        print("Start both:\n  uvicorn app.main:app --reload\n  uvicorn resource_server.main:app --reload --port 8001")
        return False


def authorize_and_get_tokens(
    session_client: httpx.Client, client_pk: str, redirect_uri: str, scope: str
) -> tuple[dict | None, str | None]:
    """Returns (tokens_dict, None) on success or (None, redirect_url) if bounced to /login."""
    verifier, challenge = pkce_pair()
    r = session_client.get(
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
    if r.status_code != 302:
        return None, f"{r.status_code}: {r.text[:100]}"
    location = r.headers["location"]
    if location.startswith("/login"):
        return None, location

    qs = parse_qs(urlparse(location).query)
    if "code" not in qs:
        return None, f"no code in {location}"
    code = qs["code"][0]

    r = session_client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_pk,
            "code_verifier": verifier,
        },
    )
    if r.status_code != 200:
        return None, f"{r.status_code}: {r.text[:200]}"
    return r.json(), None


# ---------- main ----------

def main() -> int:
    if not probe_servers():
        return 1
    chk = Checker()

    # ---- reset state ----
    try:
        alice_id, sales_id, finance_id = reset_alice_to_sales()
        chk.check("state reset: alice in sales, not in finance", True)
    except Exception as exc:
        chk.check("state reset", False, str(exc))
        return chk.summary()

    # ---- [1] login ----
    chk.section("[1] Authentication: alice logs in")
    with httpx.Client(base_url=IDP, follow_redirects=False) as c:
        r = c.post("/auth/login", json={"username": "alice", "password": "alice-pass-123"})
        chk.check("POST /auth/login → 200", r.status_code == 200, f"got {r.status_code}")
        chk.check("SID cookie set (HttpOnly)", "SID=" in r.headers.get("set-cookie", "")
                  and "HttpOnly" in r.headers.get("set-cookie", ""))
        r = c.get("/auth/session")
        chk.check("GET /auth/session authenticated=true", r.json().get("authenticated") is True)

        # ---- [2] authorize orders-ui ----
        chk.section("[2] Authorize: orders-ui (alice has orders.read via sales)")
        tokens_orders, err = authorize_and_get_tokens(
            c, "orders-ui", "http://localhost:3000/callback", "openid orders.read"
        )
        chk.check("orders-ui authorize → tokens", tokens_orders is not None, err or "")
        if tokens_orders:
            scope_set = set(tokens_orders["scope"].split())
            chk.check("orders-ui token has 'orders.read'", "orders.read" in scope_set,
                      f"scope={sorted(scope_set)}")
            chk.check("orders-ui token has 'openid'", "openid" in scope_set)
            chk.check("orders-ui token has ID token", "id_token" in tokens_orders)

        # ---- [3] SSO: authorize reports-ui with same session ----
        chk.section("[3] SSO: reports-ui (no re-login, session reused)")
        tokens_reports, err = authorize_and_get_tokens(
            c, "reports-ui", "http://localhost:4000/callback", "openid reports.read"
        )
        chk.check("SSO works: reports-ui authorize succeeded WITHOUT new login",
                  tokens_reports is not None, err or "")
        if tokens_reports:
            scope_set = set(tokens_reports["scope"].split())
            chk.check("scope filter: alice's reports-ui token has NO 'reports.read' (not in finance)",
                      "reports.read" not in scope_set, f"scope={sorted(scope_set)}")

    # ---- [4] RS enforcement with alice's tokens ----
    if tokens_orders:
        chk.section("[4] Resource Server: alice's orders-ui token")
        r = httpx.get(f"{RS}/api/orders", headers={"Authorization": f"Bearer {tokens_orders['access_token']}"})
        chk.check("GET /api/orders with orders.read → 200", r.status_code == 200, f"got {r.status_code}")
        r = httpx.get(f"{RS}/api/reports", headers={"Authorization": f"Bearer {tokens_orders['access_token']}"})
        chk.check("GET /api/reports without reports.read → 403", r.status_code == 403, f"got {r.status_code}")

    if tokens_reports:
        chk.section("[5] Resource Server: alice's reports-ui token (scope was filtered)")
        r = httpx.get(f"{RS}/api/reports", headers={"Authorization": f"Bearer {tokens_reports['access_token']}"})
        chk.check("GET /api/reports with filtered token → 403 (proves IdP filter worked)",
                  r.status_code == 403, f"got {r.status_code}")

    # ---- [6] permission change: move alice to finance ----
    chk.section("[6] Permission change: move alice sales→finance")
    move_alice_to_finance(alice_id, sales_id, finance_id)
    chk.check("alice moved to finance group", True)

    # ---- [7] re-authorize reports-ui, verify new scope ----
    chk.section("[7] Re-authorize reports-ui after permission change")
    with httpx.Client(base_url=IDP, follow_redirects=False) as c:
        c.post("/auth/login", json={"username": "alice", "password": "alice-pass-123"})
        new_tokens_reports, err = authorize_and_get_tokens(
            c, "reports-ui", "http://localhost:4000/callback", "openid reports.read"
        )
        chk.check("new reports-ui token issued", new_tokens_reports is not None, err or "")
        if new_tokens_reports:
            scope_set = set(new_tokens_reports["scope"].split())
            chk.check("permission change propagated: new token HAS 'reports.read'",
                      "reports.read" in scope_set, f"scope={sorted(scope_set)}")
            r = httpx.get(f"{RS}/api/reports",
                          headers={"Authorization": f"Bearer {new_tokens_reports['access_token']}"})
            chk.check("GET /api/reports with new token → 200", r.status_code == 200, f"got {r.status_code}")

        # ---- [8] refresh rotation ----
        if new_tokens_reports:
            chk.section("[8] Refresh token rotation")
            old_refresh = new_tokens_reports["refresh_token"]
            r = c.post("/token", data={
                "grant_type": "refresh_token",
                "refresh_token": old_refresh,
                "client_id": "reports-ui",
            })
            chk.check("first refresh succeeds", r.status_code == 200, f"got {r.status_code}")
            if r.status_code == 200:
                rotated = r.json()
                chk.check("refresh returned new token", rotated["refresh_token"] != old_refresh)
                r = c.post("/token", data={
                    "grant_type": "refresh_token",
                    "refresh_token": old_refresh,
                    "client_id": "reports-ui",
                })
                chk.check("reusing old refresh → 400 (rotation revoked it)",
                          r.status_code == 400, f"got {r.status_code}")

        # ---- [9] logout revokes session ----
        chk.section("[9] Logout revokes session")
        r = c.post("/auth/logout")
        chk.check("POST /auth/logout → 204", r.status_code == 204)
        r = c.get("/auth/session")
        chk.check("session no longer authenticated", r.json().get("authenticated") is False)
        # A new /authorize now must redirect to /login
        _, err = authorize_and_get_tokens(c, "reports-ui", "http://localhost:4000/callback", "openid")
        chk.check("authorize after logout → redirect to /login",
                  err is not None and err.startswith("/login"))

    # ---- [10] admin endpoint sanity ----
    chk.section("[10] Admin endpoint sanity")
    from app.security.jwt_signer import get_jwt_signer
    admin_token = get_jwt_signer().sign(
        {"sub": "1", "scope": "openid admin", "preferred_username": "admin"},
        ttl_seconds=120,
    )
    r = httpx.get(f"{IDP}/admin/v1/users/1/effective-scopes",
                  headers={"Authorization": f"Bearer {admin_token}"})
    chk.check("admin sees own effective scopes", r.status_code == 200)
    if r.status_code == 200:
        body = r.json()
        chk.check("admin scopes include 'admin'", "admin" in body["scopes"])
        chk.check("scopes are sorted (deterministic)",
                  body["scopes"] == sorted(body["scopes"]))

    # ---- cleanup ----
    reset_alice_to_sales()

    return chk.summary()


if __name__ == "__main__":
    sys.exit(main())