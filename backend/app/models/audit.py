"""Audit log: a permanent record of what administrators did."""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UBigInt, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    # NULL for platform-level (super admin) actions
    university_id: Mapped[int | None] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True
    )
    actor_id: Mapped[int] = mapped_column(UBigInt, ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))  # e.g. rider_approved
    target_type: Mapped[str] = mapped_column(String(50))
    target_id: Mapped[int | None] = mapped_column(UBigInt)
    details: Mapped[dict | None] = mapped_column(JSON)  # never sensitive content
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
