"""Account tables: users and email verification tokens."""
from datetime import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UBigInt, utcnow

USER_ROLES = ("super_admin", "university_admin", "student")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("university_id", "student_id_no"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    # NULL only for the platform super admin. Everyone else belongs to one tenant.
    university_id: Mapped[int | None] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True
    )
    email: Mapped[str] = mapped_column(String(190), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))  # Argon2 hash, never plain text
    full_name: Mapped[str] = mapped_column(String(150))
    # Nullable so data deletion can clear it when a profile is anonymized
    phone: Mapped[str | None] = mapped_column(String(20))
    student_id_no: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(
        Enum(*USER_ROLES, name="user_role"), default="student"
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    anonymized_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class EmailVerificationToken(Base):
    """Only the SHA-256 hash of a token is stored, never the token itself."""

    __tablename__ = "email_verification_tokens"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(CHAR(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime)
