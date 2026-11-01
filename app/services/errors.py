"""Domain errors raised by service methods.

Each error carries a `code` (stable machine string), a human message, and
an `http_status`. Layer above (FastAPI exception handlers, added in Step 4B)
maps them to OAuth2-shaped JSON: {"error": code, "error_description": message}.
"""

from __future__ import annotations


class DomainError(Exception):
    http_status: int = 400
    code: str = "invalid_request"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


# ---------- 404 ----------

class NotFoundError(DomainError):
    http_status = 404
    code = "not_found"


class UserNotFound(NotFoundError):
    code = "user_not_found"

    def __init__(self, user_id: int | str) -> None:
        super().__init__(f"User {user_id!r} does not exist")


class GroupNotFound(NotFoundError):
    code = "group_not_found"

    def __init__(self, group_id: int | str) -> None:
        super().__init__(f"Group {group_id!r} does not exist")


class ScopeNotFound(NotFoundError):
    code = "scope_not_found"

    def __init__(self, scope_id: int | str) -> None:
        super().__init__(f"Scope {scope_id!r} does not exist")


class ClientNotFound(NotFoundError):
    code = "client_not_found"

    def __init__(self, client_id: str) -> None:
        super().__init__(f"Client {client_id!r} does not exist")


# ---------- 409 ----------

class ConflictError(DomainError):
    http_status = 409
    code = "conflict"


class DuplicateUsername(ConflictError):
    code = "duplicate_username"

    def __init__(self, username: str) -> None:
        super().__init__(f"Username {username!r} already exists in this realm")


class DuplicateScopeName(ConflictError):
    code = "duplicate_scope"

    def __init__(self, name: str) -> None:
        super().__init__(f"Scope {name!r} already exists in this realm")


class DuplicateGroupName(ConflictError):
    code = "duplicate_group"

    def __init__(self, name: str) -> None:
        super().__init__(f"Group {name!r} already exists in this realm")


class DuplicateClientId(ConflictError):
    code = "duplicate_client"

    def __init__(self, client_id: str) -> None:
        super().__init__(f"Client {client_id!r} already exists in this realm")


# ---------- 400 ----------

class ValidationError(DomainError):
    http_status = 400
    code = "invalid_request"


class WeakPassword(ValidationError):
    code = "weak_password"

    def __init__(self, reason: str) -> None:
        super().__init__(f"Password rejected: {reason}")


class GroupHierarchyError(ValidationError):
    code = "invalid_group_hierarchy"

    def __init__(self, reason: str) -> None:
        super().__init__(f"Group hierarchy invalid: {reason}")