"""HTTP endpoints for authentication. Routers only receive, call a service and respond."""
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth_service
from app.tenancy.context import (
    ACCESS_COOKIE_NAME,
    TenantContext,
    get_tenant_context,
    set_auth_cookie,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    user = auth_service.register_user(db, payload)
    # Only non-sensitive fields are returned. Never the password or its hash.
    return ok(
        {
            "id": user.id,
            "email": user.email,
            "university_id": user.university_id,
            "message": "Account created. Verify your email with the link we sent you.",
        }
    )


@router.get("/verify-email")
def verify_email(
    token: str = Query(min_length=10, max_length=200),
    db: Session = Depends(get_db),
):
    user = auth_service.verify_email(db, token)
    return ok({"email": user.email, "message": "Email verified. You can now log in."})


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    user, token = auth_service.login_user(db, payload, client_ip)
    set_auth_cookie(response, token)
    return ok(
        {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "university_id": user.university_id,
        }
    )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=ACCESS_COOKIE_NAME, path="/")
    return ok({"message": "Logged out"})


@router.get("/me")
def me(ctx: TenantContext = Depends(get_tenant_context)):
    university = None
    if ctx.university:
        university = {
            "id": ctx.university.id,
            "name": ctx.university.name,
            "short_code": ctx.university.short_code,
        }
    return ok(
        {
            "id": ctx.user.id,
            "email": ctx.user.email,
            "full_name": ctx.user.full_name,
            "role": ctx.user.role,
            "university": university,
        }
    )
