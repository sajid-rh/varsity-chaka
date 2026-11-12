"""Rider application and approval rules. No HTTP code in this file.

Status flow:
    (apply)  -> pending -> approved -> suspended -> approved (reinstated)
                       \\-> rejected -> (apply again) -> pending
    approved + past expires_at is treated as "expired" -> (apply again) -> pending
"""
import re
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.models import ReliabilityStats, RiderProfile, User
from app.models.types import utcnow
from app.services.audit_service import write_audit

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
APPROVAL_YEARS = 2
# Letters, digits, spaces and hyphens. \w also covers Bangla letters used on some plates.
PLATE_PATTERN = re.compile(r"^\w[\w \-]{2,28}\w$")
DOCUMENT_MEDIA_TYPES = {"jpg": "image/jpeg", "png": "image/png"}


# ---------- small helpers ----------

def normalize_plate(raw: str) -> str:
    plate = " ".join(raw.upper().split())
    if not PLATE_PATTERN.match(plate):
        raise AppError(
            "invalid_plate",
            "Enter the plate number using letters, digits, spaces and hyphens (4 to 30 characters)",
            422,
        )
    return plate


def add_years(moment: datetime, years: int) -> datetime:
    try:
        return moment.replace(year=moment.year + years)
    except ValueError:  # 29 February in a year that is not a leap year
        return moment.replace(year=moment.year + years, day=28)


def effective_status(profile: RiderProfile, now: datetime | None = None) -> str:
    """The status to show and enforce. An approval past its expiry date counts as expired,
    so no background job is needed."""
    now = now or utcnow()
    if profile.status == "approved" and profile.expires_at and profile.expires_at <= now:
        return "expired"
    return profile.status


# ---------- private document storage ----------

def detect_image_type(data: bytes) -> str | None:
    """Decide the type from the file's first bytes. The file name and the
    Content-Type header sent by the browser are not trusted."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return None


def store_document(data: bytes, university_id: int) -> str:
    if len(data) > MAX_DOCUMENT_BYTES:
        raise AppError("document_too_large", "The photo must be 5 MB or smaller", 413)
    image_type = detect_image_type(data)
    if image_type is None:
        raise AppError("invalid_document", "Upload a JPEG or PNG photo of the registration card", 400)

    # A random name: nothing the user typed ever becomes part of a file path
    relative = f"rider_docs/{university_id}/{uuid.uuid4().hex}.{image_type}"
    target = get_settings().upload_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return relative


def resolve_document(relative: str) -> Path | None:
    """Return the real file path, or None if it is missing or points outside the upload folder."""
    base = get_settings().upload_dir.resolve()
    target = (base / relative).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        return None
    return target


def delete_document(relative: str | None) -> None:
    if not relative:
        return
    target = resolve_document(relative)
    if target:
        target.unlink(missing_ok=True)


# ---------- student side ----------

def apply(
    db: Session,
    user: User,
    *,
    motorcycle_model: str,
    engine_class: str,
    plate_number: str,
    license_declared: bool,
    helmet_declared: bool,
    document_bytes: bytes,
) -> RiderProfile:
    if not (license_declared and helmet_declared):
        raise AppError(
            "declarations_required",
            "You must declare that you hold a valid license and will wear a helmet",
            422,
        )
    plate = normalize_plate(plate_number)
    model = " ".join(motorcycle_model.split())
    if len(model) < 2:
        raise AppError("invalid_model", "Enter your motorcycle model", 422)

    profile = db.scalar(select(RiderProfile).where(RiderProfile.user_id == user.id))
    if profile is not None:
        current = effective_status(profile)
        if current in ("pending", "approved"):
            raise AppError(
                "application_exists", "You already have a rider application in progress or approved", 409
            )
        if current == "suspended":
            raise AppError(
                "rider_suspended", "Your rider approval is suspended. Contact your university admin.", 409
            )

    taken = db.scalar(
        select(RiderProfile.id).where(
            RiderProfile.university_id == user.university_id,
            RiderProfile.plate_number == plate,
            RiderProfile.user_id != user.id,
        )
    )
    if taken:
        raise AppError("plate_taken", "This plate number is already registered", 409)

    new_path = store_document(document_bytes, user.university_id)
    old_path = profile.registration_doc_path if profile else None
    try:
        if profile is None:
            profile = RiderProfile(university_id=user.university_id, user_id=user.id)
            db.add(profile)
        profile.motorcycle_model = model
        profile.engine_class = engine_class
        profile.plate_number = plate
        profile.registration_doc_path = new_path
        profile.license_declared = license_declared
        profile.helmet_declared = helmet_declared
        # A re-application starts the review again from scratch
        profile.status = "pending"
        profile.reviewed_by = None
        profile.reviewed_at = None
        profile.rejection_reason = None
        profile.approved_at = None
        profile.expires_at = None
        db.commit()
    except IntegrityError:
        db.rollback()
        delete_document(new_path)
        raise AppError("plate_taken", "This plate number is already registered", 409)

    delete_document(old_path)  # the replaced photo is no longer needed
    return profile


def get_own_profile(db: Session, user: User) -> RiderProfile | None:
    return db.scalar(select(RiderProfile).where(RiderProfile.user_id == user.id))


def get_approved_profile(db: Session, user: User) -> RiderProfile | None:
    """The user's rider profile only if it is currently approved and not expired."""
    profile = get_own_profile(db, user)
    if profile and effective_status(profile) == "approved":
        return profile
    return None


# ---------- admin side (always scoped to the admin's own university) ----------

def _tenant_id(admin: User) -> int:
    if admin.university_id is None:
        raise AppError("forbidden", "You do not have permission to do this", 403)
    return admin.university_id


def _not_found() -> AppError:
    # Same answer for "does not exist" and "belongs to another university"
    return AppError("not_found", "Application not found", 404)


def list_applications(db: Session, admin: User, status: str | None = None) -> list[tuple[RiderProfile, User]]:
    query = (
        select(RiderProfile, User)
        .join(User, User.id == RiderProfile.user_id)
        .where(RiderProfile.university_id == _tenant_id(admin))
        .order_by(RiderProfile.created_at.desc(), RiderProfile.id.desc())
    )
    rows = db.execute(query).all()
    if status is None:
        return [(p, u) for p, u in rows]
    now = utcnow()
    return [(p, u) for p, u in rows if effective_status(p, now) == status]


def get_application(db: Session, admin: User, profile_id: int, *, lock: bool = False) -> tuple[RiderProfile, User]:
    query = (
        select(RiderProfile, User)
        .join(User, User.id == RiderProfile.user_id)
        .where(RiderProfile.id == profile_id, RiderProfile.university_id == _tenant_id(admin))
    )
    if lock:
        query = query.with_for_update(of=RiderProfile)
    row = db.execute(query).first()
    if row is None:
        raise _not_found()
    return row[0], row[1]


def _clean_reason(reason: str) -> str:
    reason = " ".join(reason.split())
    if not 3 <= len(reason) <= 255:
        raise AppError("reason_required", "Give a reason of 3 to 255 characters", 422)
    return reason


def _wrong_state(action: str, current: str) -> AppError:
    return AppError("invalid_state", f"Cannot {action} an application that is {current}", 409)


def approve(db: Session, admin: User, profile_id: int) -> tuple[RiderProfile, User]:
    profile, applicant = get_application(db, admin, profile_id, lock=True)
    current = effective_status(profile)
    if current not in ("pending", "suspended"):
        raise _wrong_state("approve", current)

    now = utcnow()
    profile.status = "approved"
    profile.reviewed_by = admin.id
    profile.reviewed_at = now
    profile.rejection_reason = None
    profile.approved_at = now
    profile.expires_at = add_years(now, APPROVAL_YEARS)
    if db.get(ReliabilityStats, profile.id) is None:
        db.add(ReliabilityStats(rider_profile_id=profile.id, university_id=profile.university_id))
    write_audit(
        db,
        actor=admin,
        action="rider_approved",
        target_type="rider_profile",
        target_id=profile.id,
        details={"expires_at": profile.expires_at.isoformat()},
    )
    db.commit()
    return profile, applicant


def reject(db: Session, admin: User, profile_id: int, reason: str) -> tuple[RiderProfile, User]:
    reason = _clean_reason(reason)
    profile, applicant = get_application(db, admin, profile_id, lock=True)
    current = effective_status(profile)
    if current != "pending":
        raise _wrong_state("reject", current)

    profile.status = "rejected"
    profile.reviewed_by = admin.id
    profile.reviewed_at = utcnow()
    profile.rejection_reason = reason
    write_audit(
        db, actor=admin, action="rider_rejected", target_type="rider_profile",
        target_id=profile.id, details={"reason": reason},
    )
    db.commit()
    return profile, applicant


def suspend(db: Session, admin: User, profile_id: int, reason: str) -> tuple[RiderProfile, User]:
    reason = _clean_reason(reason)
    profile, applicant = get_application(db, admin, profile_id, lock=True)
    current = effective_status(profile)
    if current != "approved":
        raise _wrong_state("suspend", current)

    profile.status = "suspended"
    profile.reviewed_by = admin.id
    profile.reviewed_at = utcnow()
    profile.rejection_reason = reason
    write_audit(
        db, actor=admin, action="rider_suspended", target_type="rider_profile",
        target_id=profile.id, details={"reason": reason},
    )
    db.commit()
    return profile, applicant


def document_for_admin(db: Session, admin: User, profile_id: int) -> tuple[Path, str]:
    """The registration card photo, for an admin of the same university only."""
    profile, _ = get_application(db, admin, profile_id)
    path = resolve_document(profile.registration_doc_path)
    if path is None:
        raise AppError("not_found", "Document not found", 404)
    # Viewing a personal document is itself recorded
    write_audit(
        db, actor=admin, action="rider_document_viewed", target_type="rider_profile",
        target_id=profile.id,
    )
    db.commit()
    return path, DOCUMENT_MEDIA_TYPES.get(path.suffix.lstrip("."), "application/octet-stream")


# ---------- response shapes ----------

def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def student_view(profile: RiderProfile) -> dict:
    return {
        "status": effective_status(profile),
        "motorcycle_model": profile.motorcycle_model,
        "engine_class": profile.engine_class,
        "plate_number": profile.plate_number,
        "license_declared": profile.license_declared,
        "helmet_declared": profile.helmet_declared,
        "reason": profile.rejection_reason,
        "approved_at": _iso(profile.approved_at),
        "expires_at": _iso(profile.expires_at),
        "submitted_at": _iso(profile.created_at),
    }


def admin_view(profile: RiderProfile, applicant: User) -> dict:
    return {
        "id": profile.id,
        "status": effective_status(profile),
        "applicant": {
            "id": applicant.id,
            "full_name": applicant.full_name,
            "email": applicant.email,
            "student_id_no": applicant.student_id_no,
        },
        "motorcycle_model": profile.motorcycle_model,
        "engine_class": profile.engine_class,
        "plate_number": profile.plate_number,
        "license_declared": profile.license_declared,
        "helmet_declared": profile.helmet_declared,
        "reason": profile.rejection_reason,
        "approved_at": _iso(profile.approved_at),
        "expires_at": _iso(profile.expires_at),
        "submitted_at": _iso(profile.created_at),
        "document_url": f"/api/v1/admin/rider-applications/{profile.id}/document",
    }
