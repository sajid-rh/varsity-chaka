"""Tenancy tables: universities, their policy settings and campus destinations."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.types import UBigInt, utcnow


class University(Base):
    """One row per tenant (DIU is the first)."""

    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150))
    short_code: Mapped[str] = mapped_column(String(20), unique=True)
    # Registration emails must end with this domain, e.g. diu.edu.bd
    email_domain: Mapped[str] = mapped_column(String(100), unique=True)
    logo_path: Mapped[str | None] = mapped_column(String(255))
    primary_color: Mapped[str | None] = mapped_column(CHAR(7))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class UniversitySettings(Base):
    """Per-tenant policy. One row per university."""

    __tablename__ = "university_settings"
    __table_args__ = (
        CheckConstraint(
            "weight_pickup + weight_overlap + weight_detour + weight_time"
            " + weight_destination + weight_reliability = 1",
            name="weights_sum_to_one",
        ),
    )

    university_id: Mapped[int] = mapped_column(
        UBigInt,
        ForeignKey("universities.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )

    # Fare policy. No default: the seeder and the admin must set real values.
    fuel_price_per_litre: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    max_rate_per_km: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    demand_adjustment_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    demand_cap_percent: Mapped[int] = mapped_column(
        SmallInteger().with_variant(TINYINT(unsigned=True), "mysql"),
        default=10,
        server_default=text("10"),
    )

    # Matching hard filters
    match_max_pickup_m: Mapped[int] = mapped_column(
        Integer, default=1000, server_default=text("1000")
    )
    match_max_detour_m: Mapped[int] = mapped_column(
        Integer, default=2000, server_default=text("2000")
    )
    match_time_window_min: Mapped[int] = mapped_column(
        Integer, default=20, server_default=text("20")
    )

    # Matching weights (initial values, to be tuned; they must sum to 1)
    weight_pickup: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.200"), server_default=text("0.200")
    )
    weight_overlap: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.250"), server_default=text("0.250")
    )
    weight_detour: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.150"), server_default=text("0.150")
    )
    weight_time: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.150"), server_default=text("0.150")
    )
    weight_destination: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.100"), server_default=text("0.100")
    )
    weight_reliability: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.150"), server_default=text("0.150")
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class CampusDestination(Base):
    """Named campus points (gates, buildings) a university offers as destinations."""

    __tablename__ = "campus_destinations"

    id: Mapped[int] = mapped_column(UBigInt, primary_key=True, autoincrement=True)
    university_id: Mapped[int] = mapped_column(
        UBigInt, ForeignKey("universities.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(150))
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
