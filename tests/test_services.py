"""Basic CRUD tests for each service."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services import client_service, group_service, scope_service, user_service
from app.services.errors import (
    DuplicateGroupName,
    DuplicateScopeName,
    DuplicateUsername,
    GroupHierarchyError,
    WeakPassword,
)


def test_create_user_and_set_password(db_session: Session, realm) -> None:
    u = user_service.create_user(
        db_session, realm_id=realm.id, username="alice", password="password-123"
    )
    assert u.id
    user_service.set_password(db_session, u.id, "new-password-456")


def test_duplicate_username_rejected(db_session: Session, realm) -> None:
    user_service.create_user(db_session, realm_id=realm.id, username="alice", password="password-123")
    with pytest.raises(DuplicateUsername):
        user_service.create_user(
            db_session, realm_id=realm.id, username="alice", password="password-123"
        )


def test_weak_password_rejected(db_session: Session, realm) -> None:
    with pytest.raises(WeakPassword):
        user_service.create_user(db_session, realm_id=realm.id, username="bob", password="short")


def test_duplicate_scope_rejected(db_session: Session, realm) -> None:
    scope_service.create_scope(db_session, realm_id=realm.id, name="orders.read")
    with pytest.raises(DuplicateScopeName):
        scope_service.create_scope(db_session, realm_id=realm.id, name="orders.read")


def test_duplicate_group_rejected(db_session: Session, realm) -> None:
    group_service.create_group(db_session, realm_id=realm.id, name="sales")
    with pytest.raises(DuplicateGroupName):
        group_service.create_group(db_session, realm_id=realm.id, name="sales")


def test_group_depth_one_enforced(db_session: Session, realm) -> None:
    root = group_service.create_group(db_session, realm_id=realm.id, name="staff")
    child = group_service.create_group(
        db_session, realm_id=realm.id, name="sales", parent_group_id=root.id
    )
    grandchild = group_service.create_group(db_session, realm_id=realm.id, name="emea")

    # Attaching grandchild under child would be depth 2.
    with pytest.raises(GroupHierarchyError):
        group_service.set_parent_group(db_session, grandchild.id, child.id)

    # Setting root's parent to child would create a cycle + depth 2.
    with pytest.raises(GroupHierarchyError):
        group_service.set_parent_group(db_session, root.id, child.id)


def test_register_public_client_has_no_secret(db_session: Session, realm) -> None:
    client, secret = client_service.register_client(
        db_session,
        realm_id=realm.id,
        client_id="orders-ui",
        client_name="Orders UI",
        redirect_uris=["http://localhost:3000/cb"],
        allowed_scopes=["openid", "orders.read"],
        is_public=True,
    )
    assert client.client_secret_hash is None
    assert secret is None


def test_register_confidential_client_returns_plaintext_once(db_session: Session, realm) -> None:
    client, secret = client_service.register_client(
        db_session,
        realm_id=realm.id,
        client_id="reports-svc",
        client_name="Reports Service",
        redirect_uris=["http://localhost:4000/cb"],
        allowed_scopes=["openid", "reports.read"],
        is_public=False,
    )
    assert secret is not None and len(secret) >= 32
    assert client.client_secret_hash is not None
    assert client.client_secret_hash != secret