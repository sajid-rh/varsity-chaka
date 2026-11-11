"""Importing this package registers every model with Base.metadata.

Alembic's env.py imports it so autogenerate can see all tables.
"""
from app.models.university import CampusDestination, University, UniversitySettings
from app.models.user import EmailVerificationToken, User

__all__ = [
    "CampusDestination",
    "EmailVerificationToken",
    "University",
    "UniversitySettings",
    "User",
]
