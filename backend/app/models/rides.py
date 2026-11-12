"""Rides, requests, trips, and blocks models."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.types import UBigInt, utcnow

OFFER_DIRECTIONS = ("to_campus", "from_campus")
OFFER_STATUSES = ("open", "booked", "closed", "cancelled")
REQUEST_STATUSES = ("open", "matched", "cancelled", "expired")
TRIP_STATUSES = ("requested", "accepted", "confirmed", "in_progress", "completed", "cancelled")


class RideOffer(Base):
    """A seat offered by an approved rider."""

    __tablename__ = "ride_offers"
    __table_args__ = (
        Index("ix_ride_offers_search", "university_id", "status", "departure_time"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True, nullable=False
    )
    rider_profile_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("rider_profiles.id"), index=True, nullable=False
    )
    rider_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), index=True, nullable=False
    )

    # Coordinates and user-friendly labels
    origin_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    origin_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    origin_label: Mapped[str] = mapped_column(String(150), nullable=False)

    dest_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    dest_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    dest_label: Mapped[str] = mapped_column(String(150), nullable=False)

    direction: Mapped[str] = mapped_column(
        Enum(*OFFER_DIRECTIONS, name="offer_direction"), nullable=False
    )
    departure_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Optional route metrics
    route_distance_m: Mapped[int | None] = mapped_column(nullable=True)
    route_duration_s: Mapped[int | None] = mapped_column(nullable=True)

    status: Mapped[str] = mapped_column(
        Enum(*OFFER_STATUSES, name="offer_status"),
        default="open",
        server_default=text("'open'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    rider_profile = relationship("RiderProfile", lazy="joined")
    rider = relationship("User", foreign_keys=[rider_id], lazy="joined")


class RideRequest(Base):
    """A ride requested by a student passenger."""

    __tablename__ = "ride_requests"
    __table_args__ = (
        Index("ix_ride_requests_search", "university_id", "status", "preferred_time"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True, nullable=False
    )
    passenger_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), index=True, nullable=False
    )

    pickup_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    pickup_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    pickup_label: Mapped[str] = mapped_column(String(150), nullable=False)

    dest_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    dest_lng: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    dest_label: Mapped[str] = mapped_column(String(150), nullable=False)

    preferred_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*REQUEST_STATUSES, name="request_status"),
        default="open",
        server_default=text("'open'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    passenger = relationship("User", foreign_keys=[passenger_id], lazy="joined")


class Trip(Base):
    """The matched ride following the state machine:
    requested -> accepted -> confirmed -> in_progress -> completed (or cancelled)
    """

    __tablename__ = "trips"
    __table_args__ = (
        Index("ix_trips_uni_status", "university_id", "status"),
        Index("ix_trips_rider_status", "rider_id", "status"),
        Index("ix_trips_passenger_status", "passenger_id", "status"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True, nullable=False
    )
    ride_offer_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("ride_offers.id"), index=True, nullable=False
    )
    ride_request_id: Mapped[int | None] = mapped_column(
        UBigInt, ForeignKey("ride_requests.id"), index=True, nullable=True
    )
    rider_profile_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("rider_profiles.id"), index=True, nullable=False
    )
    rider_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), index=True, nullable=False
    )
    passenger_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), index=True, nullable=False
    )

    status: Mapped[str] = mapped_column(
        Enum(*TRIP_STATUSES, name="trip_status"),
        default="requested",
        server_default=text("'requested'"),
        nullable=False,
    )

    # Database-level capacity lock:
    # Set to ride_offer_id when trip is active (requested, accepted, confirmed, in_progress).
    # Cleared to NULL on completed or cancelled.
    # The UNIQUE constraint guarantees at most one active trip per offer.
    active_offer_id: Mapped[int | None] = mapped_column(
        UBigInt,
        ForeignKey("ride_offers.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )

    # Explainable matching score details
    match_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    match_explanation: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Advisory cost-sharing range (computed or suggested)
    suggested_fare_min: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    suggested_fare_max: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    # State transition timestamps
    helmet_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cancelled_by: Mapped[int | None] = mapped_column(
        UBigInt, ForeignKey("users.id"), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Dual completion confirmation & dispute handling
    rider_confirmed_complete_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    passenger_confirmed_complete_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disputed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0"), nullable=False
    )
    dispute_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    offer = relationship("RideOffer", foreign_keys=[ride_offer_id], lazy="joined")
    request = relationship("RideRequest", foreign_keys=[ride_request_id], lazy="joined")
    rider = relationship("User", foreign_keys=[rider_id], lazy="joined")
    passenger = relationship("User", foreign_keys=[passenger_id], lazy="joined")


class Block(Base):
    """User block relationship. Blocked pairs are strictly filtered out of matching."""

    __tablename__ = "blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_block_pair"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True, nullable=False
    )
    blocker_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), index=True, nullable=False
    )
    blocked_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ContactDisclosure(Base):
    """Audit log of contact detail exposures after trip confirmation."""

    __tablename__ = "contact_disclosures"
    __table_args__ = (
        Index("ix_contact_disclosures_trip", "trip_id"),
    )

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True, nullable=False
    )
    trip_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("trips.id"), nullable=False
    )
    viewer_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), nullable=False
    )
    disclosed_user_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
