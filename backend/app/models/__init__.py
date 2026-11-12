"""Importing this package registers every model with Base.metadata.

Alembic's env.py imports it so autogenerate can see all tables.
"""
from app.models.audit import AuditLog
from app.models.rider import ReliabilityStats, RiderProfile
from app.models.rides import (
    Block,
    ContactDisclosure,
    RideOffer,
    RideRequest,
    Trip,
)
from app.models.university import CampusDestination, University, UniversitySettings
from app.models.user import EmailVerificationToken, User

__all__ = [
    "AuditLog",
    "Block",
    "CampusDestination",
    "ContactDisclosure",
    "EmailVerificationToken",
    "ReliabilityStats",
    "RideOffer",
    "RideRequest",
    "RiderProfile",
    "Trip",
    "University",
    "UniversitySettings",
    "User",
]
