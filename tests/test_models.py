"""Model-level tests: the schema creates and round-trips basic data."""

from __future__ import annotations

import hashlib

from sqlalchemy.orm import Session

from app.models import Client, Group, Realm, Scope, User, UserSession
from app.security.passwords import hash_password


def _seed_realm(db: Session) -> Realm:
    realm = Realm(name="main")
    db.add(realm)
    db.flush()
    return realm


def test_create_user_and_query(db_session: Session) -> None:
    realm = _seed_realm(db_session)

    user = User(
        realm_id=realm.id,
        username="alice",
        email="alice@example.com",
        password_hash=hash_password("hunter2"),
    )
    db_session.add(user)
    db_session.commit()

    loaded = db_session.query(User).filter_by(username="alice").one()
    assert loaded.id == user.id
    assert loaded.enabled is True
    assert loaded.realm_id == realm.id


def test_user_can_be_added_to_group(db_session: Session) -> None:
    realm = _seed_realm(db_session)
    user = User(realm_id=realm.id, username="alice", password_hash=hash_password("hunter2"))
    group = Group(realm_id=realm.id, name="sales")
    db_session.add_all([user, group])
    db_session.flush()

    user.groups.append(group)
    db_session.commit()

    reloaded = db_session.query(User).filter_by(username="alice").one()
    assert [g.name for g in reloaded.groups] == ["sales"]


def test_scope_can_be_granted_via_group(db_session: Session) -> None:
    realm = _seed_realm(db_session)
    group = Group(realm_id=realm.id, name="sales")
    scope = Scope(realm_id=realm.id, name="orders.read")
    db_session.add_all([group, scope])
    db_session.flush()

    group.scopes.append(scope)
    db_session.commit()

    reloaded = db_session.query(Group).filter_by(name="sales").one()
    assert [s.name for s in reloaded.scopes] == ["orders.read"]


def test_client_with_json_fields(db_session: Session) -> None:
    realm = _seed_realm(db_session)
    client = Client(
        realm_id=realm.id,
        client_id="orders-ui",
        client_name="Orders UI",
        is_public=True,
        redirect_uris=["http://localhost:3000/callback"],
        post_logout_redirect_uris=["http://localhost:3000/"],
        allowed_scopes=["openid", "orders.read"],
    )
    db_session.add(client)
    db_session.commit()

    reloaded = db_session.query(Client).filter_by(client_id="orders-ui").one()
    assert reloaded.redirect_uris == ["http://localhost:3000/callback"]
    assert reloaded.allowed_scopes == ["openid", "orders.read"]


def test_session_belongs_to_user(db_session: Session) -> None:
    from datetime import datetime, timedelta, timezone

    realm = _seed_realm(db_session)
    user = User(realm_id=realm.id, username="alice", password_hash=hash_password("hunter2"))
    db_session.add(user)
    db_session.flush()

    now = datetime.now(timezone.utc)
    session = UserSession(
        user_id=user.id,
        realm_id=realm.id,
        token_hash=hashlib.sha256(b"test-token").hexdigest(),
        expires_at=now + timedelta(hours=1),
        last_activity_at=now,
    )
    db_session.add(session)
    db_session.commit()

    assert session.user.username == "alice"