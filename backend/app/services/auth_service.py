"""Registration and email verification business rules. No HTTP code in this file."""
import hashlib
import logging
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.rate_limit import login_limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.models import EmailVerificationToken, University, User
from app.models.types import utcnow
from app.schemas.auth import LoginRequest, RegisterRequest

TOKEN_LIFETIME_HOURS = 24

# uvicorn shows this logger in the terminal at INFO level
logger = logging.getLogger("uvicorn.error")


def hash_token(raw_token: str) -> str:
    """Only the hash of a verification token is stored, so a leaked database cannot be used to verify accounts."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def send_verification_link(email: str, raw_token: str) -> None:
    """No mail server in this prototype: in development the link is printed in the server log.
    A real deployment would send this link by email."""
    settings = get_settings()
    link = f"{settings.app_base_url}/verify-email?token={raw_token}"
    if settings.app_env == "development":
        logger.info("[DEV] Verification link for %s: %s", email, link)
    else:
        logger.warning("Email sending is not configured; link for %s was not delivered", email)


def register_user(db: Session, data: RegisterRequest) -> User:
    email = data.email.lower()
    domain = email.rsplit("@", 1)[1]

    # The tenant comes from the email domain, never from user input
    university = db.scalar(select(University).where(University.email_domain == domain))
    if university is None or not university.is_active:
        raise AppError(
            "unsupported_email_domain",
            "Use your university email address. Your university may not be on Varsity Chaka yet.",
            400,
        )

    if db.scalar(select(User.id).where(User.email == email)):
        raise AppError("email_taken", "An account with this email already exists", 409)

    if data.student_id_no and db.scalar(
        select(User.id).where(
            User.university_id == university.id,
            User.student_id_no == data.student_id_no,
        )
    ):
        raise AppError("student_id_taken", "This student ID is already registered", 409)

    user = User(
        university_id=university.id,
        email=email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        student_id_no=data.student_id_no,
        role="student",
    )
    raw_token = secrets.token_urlsafe(32)
    try:
        db.add(user)
        db.flush()  # assigns user.id
        db.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=hash_token(raw_token),
                expires_at=utcnow() + timedelta(hours=TOKEN_LIFETIME_HOURS),
            )
        )
        db.commit()
    except IntegrityError:
        # Two sign-ups racing for the same email: the database unique key decides
        db.rollback()
        raise AppError("email_taken", "An account with this email already exists", 409)

    send_verification_link(user.email, raw_token)
    return user


def verify_email(db: Session, raw_token: str) -> User:
    token = db.scalar(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == hash_token(raw_token),
            EmailVerificationToken.used_at.is_(None),
        )
    )
    now = utcnow()
    if token is None or token.expires_at < now:
        raise AppError(
            "invalid_token", "This verification link is invalid or has expired", 400
        )

    user = db.get(User, token.user_id)
    token.used_at = now  # a link works only once
    if user.email_verified_at is None:
        user.email_verified_at = now
    db.commit()
    return user


# Hash of a throwaway password. When the email is unknown we still run one hash check
# against it, so "no such user" and "wrong password" take about the same time.
_DUMMY_HASH = hash_password("not-a-real-password-Zz9")

GENERIC_LOGIN_ERROR = "Incorrect email or password"


def login_user(db: Session, data: LoginRequest, client_ip: str) -> tuple[User, str]:
    """Check credentials and return (user, access token).

    Every failure about the credentials gives the same generic message, so an attacker
    cannot tell which emails have accounts.
    """
    email = data.email.lower()
    keys = [f"email:{email}", f"ip:{client_ip}"]

    wait = max(login_limiter.blocked_for(key) for key in keys)
    if wait:
        raise AppError(
            "too_many_attempts",
            f"Too many failed attempts. Try again in {wait} seconds.",
            429,
        )

    user = db.scalar(select(User).where(User.email == email))
    password_ok = verify_password(data.password, user.password_hash if user else _DUMMY_HASH)

    if user is None or not password_ok:
        for key in keys:
            login_limiter.register_failure(key)
        raise AppError("invalid_credentials", GENERIC_LOGIN_ERROR, 401)

    # Correct password from here on, so it is safe to explain the account state
    if not user.is_active:
        raise AppError("account_disabled", "This account has been disabled", 403)
    if user.email_verified_at is None:
        raise AppError("email_not_verified", "Verify your email before logging in", 403)

    login_limiter.reset(f"email:{email}")
    token = create_access_token(
        user_id=user.id, university_id=user.university_id, role=user.role
    )
    return user, token
