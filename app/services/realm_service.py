"""Realm access. The project is single-realm; these helpers make that explicit."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Realm


def get_or_create_realm(db: Session, name: str) -> Realm:
    """Return the realm named `name`, creating it if absent.

    Idempotent — safe to call from bootstrap scripts and tests.
    """
    existing = db.execute(select(Realm).where(Realm.name == name)).scalar_one_or_none()
    if existing is not None:
        return existing
    realm = Realm(name=name)
    db.add(realm)
    db.commit()
    db.refresh(realm)
    return realm


def get_single_realm(db: Session) -> Realm:
    """Return the one realm, or raise if none / multiple exist.

    Enforces the single-realm constraint from §1.3 of the design.
    """
    realms = db.execute(select(Realm)).scalars().all()
    if len(realms) != 1:
        raise RuntimeError(
            f"Expected exactly one realm, found {len(realms)}. "
            "Run scripts/bootstrap.py to initialize the single realm."
        )
    return realms[0]