"""Bootstrap mini-idp: realm, standard scopes, admin user, demo data, admin JWT.

Idempotent: safe to run multiple times. Re-running does not duplicate or
overwrite anything that already exists. Every run prints a fresh admin JWT
with a configurable TTL.

Usage:
    python scripts/bootstrap.py

Environment:
    BOOTSTRAP_ADMIN_PASSWORD             override the default admin password
    BOOTSTRAP_ADMIN_TOKEN_TTL_SECONDS    JWT TTL (default 3600)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure the project root is importable so `from app...` works when this
# file is executed as `python scripts/bootstrap.py` from any directory.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Client, Group, Realm, Scope, User
from app.security.jwt_signer import get_jwt_signer
from app.services.authorization import compute_effective_scopes
from app.services import (
    client_service,
    group_service,
    realm_service,
    scope_service,
    user_service,
)
from app.services.errors import (
    DuplicateClientId,
    DuplicateGroupName,
    DuplicateScopeName,
    DuplicateUsername,
)

_STANDARD_SCOPES: list[tuple[str, str]] = [
    ("admin", "Full administrative access"),
    ("openid", "OIDC standard: subject identifier"),
    ("profile", "OIDC standard: name and profile fields"),
    ("email", "OIDC standard: email and email_verified"),
    ("orders.read", "Demo: read orders"),
    ("orders.write", "Demo: create/update orders"),
    ("reports.read", "Demo: read reports"),
]

_DEFAULT_ADMIN_USERNAME = "admin"
_DEFAULT_ADMIN_PASSWORD = "admin-pass-123"


@dataclass
class BootstrapResult:
    realm: Realm
    admin_user: User
    admin_token: str
    admin_password_was_default: bool
    scopes_ensured: list[str]
    demo_seeded: bool


# ---------- idempotent helpers ----------

def _ensure_scope(db: Session, *, realm_id: int, name: str, description: str) -> Scope:
    try:
        return scope_service.create_scope(
            db, realm_id=realm_id, name=name, description=description
        )
    except DuplicateScopeName:
        return db.execute(
            select(Scope).where(Scope.realm_id == realm_id, Scope.name == name)
        ).scalar_one()


def _ensure_user(db: Session, *, realm_id: int, username: str, password: str) -> User:
    try:
        return user_service.create_user(
            db, realm_id=realm_id, username=username, password=password
        )
    except DuplicateUsername:
        return db.execute(
            select(User).where(User.realm_id == realm_id, User.username == username)
        ).scalar_one()


def _ensure_group(db: Session, *, realm_id: int, name: str) -> Group:
    try:
        return group_service.create_group(db, realm_id=realm_id, name=name)
    except DuplicateGroupName:
        return db.execute(
            select(Group).where(Group.realm_id == realm_id, Group.name == name)
        ).scalar_one()


def _ensure_client(db: Session, **kwargs) -> Client:
    try:
        client, _secret = client_service.register_client(db, **kwargs)
        return client
    except DuplicateClientId:
        return client_service.get_client_by_public_id(
            db, realm_id=kwargs["realm_id"], client_id=kwargs["client_id"]
        )


# ---------- bootstrap ----------

def bootstrap(
    db: Session,
    *,
    realm_name: str = "main",
    admin_username: str = _DEFAULT_ADMIN_USERNAME,
    admin_password: str | None = None,
    seed_demo: bool = True,
    admin_token_ttl_seconds: int = 3600,
) -> BootstrapResult:
    """Ensure realm, scopes, admin user, and (optionally) demo data exist.

    Returns a BootstrapResult including a freshly-signed admin JWT.
    """
    password = (
        admin_password
        or os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
        or _DEFAULT_ADMIN_PASSWORD
    )
    used_default = password == _DEFAULT_ADMIN_PASSWORD

    realm = realm_service.get_or_create_realm(db, realm_name)

    for name, desc in _STANDARD_SCOPES:
        _ensure_scope(db, realm_id=realm.id, name=name, description=desc)

        admin_user = _ensure_user(
        db, realm_id=realm.id, username=admin_username, password=password
    )

    # Grant the standard OIDC scopes plus admin to the bootstrap admin.
    # All four scopes were created by the standard-scopes loop above.
    for scope_name in ("openid", "profile", "email", "admin"):
        scope = db.execute(
            select(Scope).where(Scope.realm_id == realm.id, Scope.name == scope_name)
        ).scalar_one()
        user_service.grant_scope_to_user(db, user_id=admin_user.id, scope_id=scope.id)

    if seed_demo:
        _seed_demo(db, realm_id=realm.id)

    # Derive the token's scope claim from the DB — the single source of truth
    # (§4.5). Never hardcode claims that may diverge from granted scopes.
    admin_scopes = sorted(compute_effective_scopes(db, admin_user.id))
    token = get_jwt_signer().sign(
        {
            "sub": str(admin_user.id),
            "scope": " ".join(admin_scopes),
            "preferred_username": admin_user.username,
        },
        ttl_seconds=admin_token_ttl_seconds,
    )

    return BootstrapResult(
        realm=realm,
        admin_user=admin_user,
        admin_token=token,
        admin_password_was_default=used_default,
        scopes_ensured=[name for name, _ in _STANDARD_SCOPES],
        demo_seeded=seed_demo,
    )


def _seed_demo(db: Session, *, realm_id: int) -> None:
    """Demo groups, users, and public OIDC clients.

    - sales group: orders.read
    - finance group: reports.read
    - alice: member of sales (pass: alice-pass-123)
    - bob:   member of finance (pass: bob-pass-123)
    - orders-ui: public client, allowed scopes openid/profile/email/orders.*
    - reports-ui: public client, allowed scopes openid/profile/email/reports.*
    """
    sales = _ensure_group(db, realm_id=realm_id, name="sales")
    finance = _ensure_group(db, realm_id=realm_id, name="finance")

    # Both scopes were already created in the standard scopes loop.
    orders_read = db.execute(
        select(Scope).where(Scope.realm_id == realm_id, Scope.name == "orders.read")
    ).scalar_one()
    reports_read = db.execute(
        select(Scope).where(Scope.realm_id == realm_id, Scope.name == "reports.read")
    ).scalar_one()

    group_service.grant_scope_to_group(db, group_id=sales.id, scope_id=orders_read.id)
    group_service.grant_scope_to_group(db, group_id=finance.id, scope_id=reports_read.id)

    alice = _ensure_user(db, realm_id=realm_id, username="alice", password="alice-pass-123")
    bob = _ensure_user(db, realm_id=realm_id, username="bob", password="bob-pass-123")
    group_service.add_member(db, group_id=sales.id, user_id=alice.id)
    group_service.add_member(db, group_id=finance.id, user_id=bob.id)

    _ensure_client(
        db,
        realm_id=realm_id,
        client_id="orders-ui",
        client_name="Orders UI",
        redirect_uris=["http://localhost:3000/callback"],
        post_logout_redirect_uris=["http://localhost:3000/"],
        allowed_scopes=["openid", "profile", "email", "orders.read", "orders.write"],
        is_public=True,
    )
    _ensure_client(
        db,
        realm_id=realm_id,
        client_id="reports-ui",
        client_name="Reports UI",
        redirect_uris=["http://localhost:4000/callback"],
        post_logout_redirect_uris=["http://localhost:4000/"],
        allowed_scopes=["openid", "profile", "email", "reports.read"],
        is_public=True,
    )


# ---------- CLI ----------

def _print_report(result: BootstrapResult, ttl_seconds: int) -> None:
    print()
    print("=== mini-idp bootstrap ===")
    print(f"Realm:          {result.realm.name} (id={result.realm.id})")
    print(f"Scopes:         {len(result.scopes_ensured)} ensured")
    print(f"Admin user:     {result.admin_user.username} (id={result.admin_user.id})")
    if result.admin_password_was_default:
        print(f"Admin password: {_DEFAULT_ADMIN_PASSWORD}  <-- CHANGE IN PRODUCTION")
        print( "                Set BOOTSTRAP_ADMIN_PASSWORD to override.")
    if result.demo_seeded:
        print("Demo seeded:")
        print("  Groups:    sales, finance")
        print("  Users:     alice (alice-pass-123), bob (bob-pass-123)")
        print("  Clients:   orders-ui, reports-ui")
    print()
    print(f"=== ADMIN JWT (valid for {ttl_seconds}s) ===")
    print(result.admin_token)
    print("=== END ADMIN JWT ===")
    print()
    print("Use it:")
    print('  export TOKEN=<paste JWT above>')
    print('  curl -s -H "Authorization: Bearer $TOKEN" \\')
    print(f'       http://localhost:8000/admin/v1/users/{result.admin_user.id}/effective-scopes')
    print()


def main() -> int:
    if not Path(".env").exists():
        print("ERROR: .env not found. Copy .env.example to .env first:", file=sys.stderr)
        print("       cp .env.example .env", file=sys.stderr)
        return 1

    settings = get_settings()
    if not Path(settings.private_key_path).exists():
        print(
            f"ERROR: RSA private key not found at {settings.private_key_path}",
            file=sys.stderr,
        )
        print("       Run `python scripts/generate_keys.py` first.", file=sys.stderr)
        return 1

    # Register every model so create_all sees the full schema.
    from app import models  # noqa: F401
    from app.db import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)

    ttl = int(os.environ.get("BOOTSTRAP_ADMIN_TOKEN_TTL_SECONDS", "3600"))

    with SessionLocal() as db:
        result = bootstrap(db, admin_token_ttl_seconds=ttl)

    _print_report(result, ttl)
    return 0


if __name__ == "__main__":
    sys.exit(main())