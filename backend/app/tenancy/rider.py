"""Dependency for routes that only an approved rider may use (posting rides, accepting requests)."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.models import RiderProfile
from app.services import rider_service
from app.tenancy.context import TenantContext, require_role


def require_approved_rider(
    ctx: TenantContext = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> RiderProfile:
    profile = rider_service.get_approved_profile(db, ctx.user)
    if profile is None:
        raise AppError(
            "rider_not_approved",
            "You need an approved rider application to do this",
            403,
        )
    return profile
