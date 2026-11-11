"""HTTP endpoints for authentication. Routers only receive, call a service and respond."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.schemas.auth import RegisterRequest
from app.services import auth_service

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
