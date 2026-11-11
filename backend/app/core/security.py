"""Password hashing, password rules and login tokens.

- Passwords are hashed with Argon2 (memory-hard). Plain passwords are never stored or logged.
- Login tokens are signed JWTs. They are signed, not encrypted, so they carry only
  ids and the role, never personal data.
"""
import re
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

ALGORITHM = "HS256"

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Return an Argon2 hash. The salt is random, so the same password gives different hashes."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True only if the password matches the stored hash. Never raises on bad input."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def check_password_strength(password: str) -> list[str]:
    """Return a list of problems with the password. An empty list means it is acceptable."""
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Must be at least {MIN_PASSWORD_LENGTH} characters long")
    if not re.search(r"[a-z]", password):
        problems.append("Must contain a lowercase letter")
    if not re.search(r"[A-Z]", password):
        problems.append("Must contain an uppercase letter")
    if not re.search(r"\d", password):
        problems.append("Must contain a digit")
    return problems


def create_access_token(
    *,
    user_id: int,
    university_id: int | None,
    role: str,
    expires_minutes: int | None = None,
) -> str:
    """Create a signed login token. `sub` is the user id; the tenant id is included
    but the server still re-reads the user from the database on every request."""
    settings = get_settings()
    if expires_minutes is None:
        expires_minutes = settings.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "uid": university_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Return the token payload, or None if the token is invalid, tampered with or expired."""
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
