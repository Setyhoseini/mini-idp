"""Argon2id password hashing."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

# Defaults are OWASP-recommended for Argon2id:
# time_cost=3, memory_cost=64 MiB, parallelism=4.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Return an Argon2id hash of `password`."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification. Returns False for any verification error."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the stored hash uses older parameters than the current hasher."""
    return _hasher.check_needs_rehash(password_hash)