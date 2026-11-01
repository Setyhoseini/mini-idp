"""Tests for the idempotent bootstrap script."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.security.jwt_signer import get_jwt_signer
from app.security.passwords import verify_password
from app.services.authorization import compute_effective_scopes
from app.services.user_service import get_user_by_username
from scripts.bootstrap import _DEFAULT_ADMIN_PASSWORD, bootstrap


def test_bootstrap_creates_realm_scopes_admin(db_session: Session) -> None:
    result = bootstrap(db_session)
    assert result.realm.name == "main"
    assert "admin" in result.scopes_ensured
    assert "openid" in result.scopes_ensured
    assert result.admin_user.username == "admin"
    assert result.admin_password_was_default is True


def test_bootstrap_is_idempotent(db_session: Session) -> None:
    r1 = bootstrap(db_session)
    r2 = bootstrap(db_session)
    assert r1.realm.id == r2.realm.id
    assert r1.admin_user.id == r2.admin_user.id
    assert r1.scopes_ensured == r2.scopes_ensured


def test_bootstrap_admin_has_admin_scope(db_session: Session) -> None:
    result = bootstrap(db_session)
    scopes = compute_effective_scopes(db_session, result.admin_user.id)
    assert "admin" in scopes


def test_bootstrap_token_verifies_and_carries_admin(db_session: Session) -> None:
    result = bootstrap(db_session)
    claims = get_jwt_signer().verify(result.admin_token)
    assert claims["sub"] == str(result.admin_user.id)
    assert "admin" in claims["scope"].split()
    assert claims["preferred_username"] == "admin"


def test_bootstrap_with_custom_admin_password(db_session: Session) -> None:
    result = bootstrap(db_session, admin_password="a-much-stronger-password-xyz")
    assert result.admin_password_was_default is False
    assert verify_password("a-much-stronger-password-xyz", result.admin_user.password_hash)
    assert not verify_password(_DEFAULT_ADMIN_PASSWORD, result.admin_user.password_hash)


def test_bootstrap_seeds_demo_users(db_session: Session) -> None:
    result = bootstrap(db_session, seed_demo=True)
    alice = get_user_by_username(db_session, realm_id=result.realm.id, username="alice")
    bob = get_user_by_username(db_session, realm_id=result.realm.id, username="bob")

    # alice is in sales → orders.read; bob is in finance → reports.read.
    assert "orders.read" in compute_effective_scopes(db_session, alice.id)
    assert "reports.read" in compute_effective_scopes(db_session, bob.id)
    # Neither demo user accidentally has admin.
    assert "admin" not in compute_effective_scopes(db_session, alice.id)
    assert "admin" not in compute_effective_scopes(db_session, bob.id)


def test_bootstrap_skip_demo(db_session: Session) -> None:
    bootstrap(db_session, seed_demo=False)
    alice = db_session.execute(
        select(User).where(User.username == "alice")
    ).scalar_one_or_none()
    assert alice is None