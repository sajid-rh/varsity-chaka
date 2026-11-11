"""Seeds the database with the two demo tenants and their admin accounts.

Run from the backend/ folder:   python -m app.seed

Safe to run more than once: anything that already exists is skipped.
All passwords and fare values come from .env. Nothing secret is written in code,
and passwords are stored only as Argon2 hashes.
"""
import sys
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.security import check_password_strength, hash_password
from app.models import University, UniversitySettings, User
from app.models.types import utcnow

# DIU is the first real tenant. The second one exists to demonstrate and test isolation.
TENANTS = [
    {
        "name": "Daffodil International University",
        "short_code": "DIU",
        "email_domain": "diu.edu.bd",
        "primary_color": "#1B5E20",
        "admin_email": "admin@diu.edu.bd",
        "admin_name": "DIU Admin",
    },
    {
        "name": "American International University-Bangladesh",
        "short_code": "AIUB",
        "email_domain": "aiub.edu",
        "primary_color": "#B71C1C",
        "admin_email": "admin@aiub.edu",
        "admin_name": "AIUB Admin",
    },
]


def check_seed_settings(settings: Settings) -> list[str]:
    """Return a list of problems with the seed values. Empty means ready to seed."""
    problems = []
    if not settings.seed_super_admin_email:
        problems.append("SEED_SUPER_ADMIN_EMAIL is not set in .env")
    if not settings.seed_admin_password:
        problems.append("SEED_ADMIN_PASSWORD is not set in .env")
    else:
        for issue in check_password_strength(settings.seed_admin_password):
            problems.append(f"SEED_ADMIN_PASSWORD: {issue}")
    if settings.seed_fuel_price_per_litre is None:
        problems.append("SEED_FUEL_PRICE_PER_LITRE is not set in .env")
    if settings.seed_max_rate_per_km is None:
        problems.append("SEED_MAX_RATE_PER_KM is not set in .env")
    return problems


def ensure_university(db: Session, data: dict) -> tuple[University, bool]:
    existing = db.scalar(
        select(University).where(University.short_code == data["short_code"])
    )
    if existing:
        return existing, False
    university = University(
        name=data["name"],
        short_code=data["short_code"],
        email_domain=data["email_domain"],
        primary_color=data["primary_color"],
    )
    db.add(university)
    db.flush()  # assigns university.id without committing yet
    return university, True


def ensure_settings(db: Session, university: University, settings: Settings) -> bool:
    if db.get(UniversitySettings, university.id):
        return False
    db.add(
        UniversitySettings(
            university_id=university.id,
            fuel_price_per_litre=settings.seed_fuel_price_per_litre,
            max_rate_per_km=settings.seed_max_rate_per_km,
        )
    )
    return True


def ensure_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    role: str,
    university_id: int | None,
    password: str,
) -> bool:
    if db.scalar(select(User).where(User.email == email)):
        return False
    db.add(
        User(
            email=email,
            full_name=full_name,
            role=role,
            university_id=university_id,
            password_hash=hash_password(password),
            email_verified_at=utcnow(),  # seeded admins are trusted, no email step
        )
    )
    return True


def run_seed(db: Session, settings: Settings) -> list[str]:
    """Create anything missing and return a log of what was created or skipped."""
    log = []
    password = settings.seed_admin_password

    created = ensure_user(
        db,
        email=settings.seed_super_admin_email,
        full_name="Platform Super Admin",
        role="super_admin",
        university_id=None,
        password=password,
    )
    log.append(f"super admin {settings.seed_super_admin_email}: {'created' if created else 'already exists'}")

    for data in TENANTS:
        university, created = ensure_university(db, data)
        log.append(f"university {data['short_code']}: {'created' if created else 'already exists'}")

        created = ensure_settings(db, university, settings)
        log.append(f"  settings: {'created' if created else 'already exist'}")

        created = ensure_user(
            db,
            email=data["admin_email"],
            full_name=data["admin_name"],
            role="university_admin",
            university_id=university.id,
            password=password,
        )
        log.append(f"  admin {data['admin_email']}: {'created' if created else 'already exists'}")

    db.commit()
    return log


def main() -> int:
    settings = get_settings()
    problems = check_seed_settings(settings)
    if problems:
        print("Cannot seed. Fix these in your .env file:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    with SessionLocal() as db:
        for line in run_seed(db, settings):
            print(line)
    print("Done. Passwords are never printed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
