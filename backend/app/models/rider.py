"""Rider trust tables: the rider application and its derived reliability summary."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UBigInt, utcnow

ENGINE_CLASSES = ("cc100", "cc125_150", "cc150_plus")
RIDER_STATUSES = ("pending", "approved", "rejected", "suspended", "expired")


class RiderProfile(Base):
    """A student's rider application. One per user; it also holds the approval state."""

    __tablename__ = "rider_profiles"
    __table_args__ = (UniqueConstraint("university_id", "plate_number"),)

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(UBigInt, ForeignKey("users.id"), unique=True)
    motorcycle_model: Mapped[str] = mapped_column(String(100))
    engine_class: Mapped[str] = mapped_column(Enum(*ENGINE_CLASSES, name="engine_class"))
    plate_number: Mapped[str] = mapped_column(String(30))
    # Relative path inside the private upload folder. Never exposed in API responses.
    registration_doc_path: Mapped[str] = mapped_column(String(255))
    # Self-declarations. They are recorded, not verified (stated as a limitation).
    license_declared: Mapped[bool] = mapped_column(Boolean)
    helmet_declared: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(
        Enum(*RIDER_STATUSES, name="rider_status"),
        default="pending",
        server_default=text("'pending'"),
    )
    reviewed_by: Mapped[int | None] = mapped_column(UBigInt, ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Holds the reason for a rejection or a suspension
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)  # approved_at + 2 years
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class ReliabilityStats(Base):
    """Derived counters used later by matching. They can be rebuilt from trips and reviews."""

    __tablename__ = "reliability_stats"

    rider_profile_id: Mapped[int] = mapped_column(
        UBigInt,
        ForeignKey("rider_profiles.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True
    )
    completed_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    cancelled_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    rating_sum: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    on_time_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
