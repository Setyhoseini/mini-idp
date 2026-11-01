"""Eager import of every model.

Must remain exhaustive: `Base.metadata.create_all()` only sees models
that have been imported into the process. Importing this package in
`app/main.py` guarantees every table is registered before create_all runs.
"""

from app.models.authorization_code import AuthorizationCode
from app.models.base import Base, CreatedAtMixin, TimestampMixin, group_scope, user_group, user_scope
from app.models.client import Client
from app.models.group import Group
from app.models.realm import Realm
from app.models.refresh_token import RefreshToken
from app.models.scope import Scope
from app.models.session import UserSession
from app.models.user import User

__all__ = [
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "group_scope",
    "user_group",
    "user_scope",
    "AuthorizationCode",
    "Client",
    "Group",
    "Realm",
    "RefreshToken",
    "Scope",
    "UserSession",
    "User",
]