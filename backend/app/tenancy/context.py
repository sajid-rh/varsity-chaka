"""Who is making this request, and which university do they belong to?

Every protected route depends on get_tenant_context. The user, their role and their
university are always re-read from the database. They are never taken from request
input and never trusted from the token alone (docs/02-architecture.md, section 6).
"""
from dataclasses import dataclass

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.models import University, User

ACCESS_COOKIE_NAME = "access_token"


@dataclass
class TenantContext:
    user: User
    university: University | None  # None only for the platform super admin

    @property
    def university_id(self) -> int | None:
        return self.user.university_id


def _not_authenticated(message: str = "Please log in") -> AppError:
    return AppError("not_authenticated", message, 401)


def get_tenant_context(request: Request, db: Session = Depends(get_db)) -> TenantContext:
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        raise _not_authenticated()

    payload = decode_access_token(token)
    if payload is None:
        raise _not_authenticated("Your session is invalid or has expired. Please log in again.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise _not_authenticated("Your session is invalid. Please log in again.")

    user = db.get(User, user_id)
    if user is None or not user.is_active or user.email_verified_at is None:
        raise _not_authenticated("Your session is no longer valid. Please log in again.")

    # The token must agree with the database about the tenant
    if payload.get("uid") != user.university_id:
        raise _not_authenticated("Your session is invalid. Please log in again.")

    university = None
    if user.university_id is not None:
        university = db.get(University, user.university_id)
        if university is None or not university.is_active:
            raise AppError("account_disabled", "Your university is not active on Varsity Chaka", 403)

    return TenantContext(user=user, university=university)


def require_role(*allowed_roles: str):
    """Dependency factory: only users with one of these roles may call the route."""

    def checker(ctx: TenantContext = Depends(get_tenant_context)) -> TenantContext:
        if ctx.user.role not in allowed_roles:
            raise AppError("forbidden", "You do not have permission to do this", 403)
        return ctx

    return checker


def set_auth_cookie(response: Response, token: str) -> None:
    """Store the login token in a cookie the browser sends back automatically.

    HttpOnly: JavaScript cannot read it, which limits the damage of an XSS bug.
    SameSite=Lax: the browser does not send it on cross-site POSTs (CSRF protection).
    """
    settings = get_settings()
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
