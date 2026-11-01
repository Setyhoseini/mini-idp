"""Invariant tests for the effective-scope resolver — the design's §4.5 formula."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services import group_service, scope_service, user_service
from app.services.authorization import compute_effective_scopes
from app.services.errors import UserNotFound


def _user(db: Session, realm_id: int, username: str):
    return user_service.create_user(
        db, realm_id=realm_id, username=username, password="password-123"
    )


def _scope(db: Session, realm_id: int, name: str):
    return scope_service.create_scope(db, realm_id=realm_id, name=name)


def test_empty_user_has_no_scopes(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    assert compute_effective_scopes(db_session, u.id) == set()


def test_direct_scopes_are_included(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    s1 = _scope(db_session, realm.id, "orders.read")
    s2 = _scope(db_session, realm.id, "orders.write")
    user_service.grant_scope_to_user(db_session, user_id=u.id, scope_id=s1.id)
    user_service.grant_scope_to_user(db_session, user_id=u.id, scope_id=s2.id)

    assert compute_effective_scopes(db_session, u.id) == {"orders.read", "orders.write"}


def test_group_scopes_are_inherited(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    g = group_service.create_group(db_session, realm_id=realm.id, name="sales")
    s = _scope(db_session, realm.id, "orders.read")
    group_service.add_member(db_session, group_id=g.id, user_id=u.id)
    group_service.grant_scope_to_group(db_session, group_id=g.id, scope_id=s.id)

    assert compute_effective_scopes(db_session, u.id) == {"orders.read"}


def test_direct_and_group_scopes_are_unioned(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    g = group_service.create_group(db_session, realm_id=realm.id, name="sales")
    s1 = _scope(db_session, realm.id, "orders.read")
    s2 = _scope(db_session, realm.id, "reports.read")
    user_service.grant_scope_to_user(db_session, user_id=u.id, scope_id=s1.id)
    group_service.add_member(db_session, group_id=g.id, user_id=u.id)
    group_service.grant_scope_to_group(db_session, group_id=g.id, scope_id=s2.id)

    assert compute_effective_scopes(db_session, u.id) == {"orders.read", "reports.read"}


def test_parent_group_scopes_are_inherited(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    parent = group_service.create_group(db_session, realm_id=realm.id, name="staff")
    child = group_service.create_group(
        db_session, realm_id=realm.id, name="sales", parent_group_id=parent.id
    )
    s_parent = _scope(db_session, realm.id, "reports.read")
    s_child = _scope(db_session, realm.id, "orders.read")
    group_service.grant_scope_to_group(db_session, group_id=parent.id, scope_id=s_parent.id)
    group_service.grant_scope_to_group(db_session, group_id=child.id, scope_id=s_child.id)
    group_service.add_member(db_session, group_id=child.id, user_id=u.id)

    assert compute_effective_scopes(db_session, u.id) == {"reports.read", "orders.read"}


def test_revoking_scope_removes_it_from_effective_set(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    s = _scope(db_session, realm.id, "orders.read")
    user_service.grant_scope_to_user(db_session, user_id=u.id, scope_id=s.id)
    assert "orders.read" in compute_effective_scopes(db_session, u.id)

    user_service.revoke_scope_from_user(db_session, user_id=u.id, scope_id=s.id)
    assert "orders.read" not in compute_effective_scopes(db_session, u.id)


def test_removing_user_from_group_removes_group_scopes(db_session: Session, realm) -> None:
    u = _user(db_session, realm.id, "alice")
    g = group_service.create_group(db_session, realm_id=realm.id, name="sales")
    s = _scope(db_session, realm.id, "orders.read")
    group_service.add_member(db_session, group_id=g.id, user_id=u.id)
    group_service.grant_scope_to_group(db_session, group_id=g.id, scope_id=s.id)
    assert "orders.read" in compute_effective_scopes(db_session, u.id)

    group_service.remove_member(db_session, group_id=g.id, user_id=u.id)
    assert compute_effective_scopes(db_session, u.id) == set()


def test_moving_user_between_groups_changes_effective_scopes(db_session: Session, realm) -> None:
    """The headline invariant from the assignment brief."""
    u = _user(db_session, realm.id, "alice")
    g_sales = group_service.create_group(db_session, realm_id=realm.id, name="sales")
    g_finance = group_service.create_group(db_session, realm_id=realm.id, name="finance")
    s_orders = _scope(db_session, realm.id, "orders.read")
    s_reports = _scope(db_session, realm.id, "reports.read")
    group_service.grant_scope_to_group(db_session, group_id=g_sales.id, scope_id=s_orders.id)
    group_service.grant_scope_to_group(db_session, group_id=g_finance.id, scope_id=s_reports.id)

    group_service.add_member(db_session, group_id=g_sales.id, user_id=u.id)
    assert compute_effective_scopes(db_session, u.id) == {"orders.read"}

    group_service.remove_member(db_session, group_id=g_sales.id, user_id=u.id)
    group_service.add_member(db_session, group_id=g_finance.id, user_id=u.id)
    assert compute_effective_scopes(db_session, u.id) == {"reports.read"}


def test_unknown_user_raises(db_session: Session) -> None:
    with pytest.raises(UserNotFound):
        compute_effective_scopes(db_session, 99999)