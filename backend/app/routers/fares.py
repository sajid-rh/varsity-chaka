"""API endpoints for advisory fare calculation and tenant fare policies."""
from decimal import Decimal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.schemas.fare import TenantFarePolicyUpdate
from app.services import fare_service
from app.tenancy.context import TenantContext, require_role

router = APIRouter(prefix="/api/v1", tags=["fares"])
admin_router = APIRouter(prefix="/api/v1/admin/fare-policy", tags=["admin: fare-policy"])

student_only = require_role("student")
admin_only = require_role("university_admin")


@router.get("/fares/estimate")
def get_fare_estimate(
    distance_km: Decimal = Query(..., gt=0, le=200),
    duration_min: Decimal = Query(..., gt=0, le=600),
    engine_class: str = Query(default="cc125_150"),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    """Calculate an advisory fare breakdown and range for specified route parameters."""
    res = fare_service.calculate_fare(
        db=db,
        university_id=ctx.university_id,
        distance_km=distance_km,
        duration_min=duration_min,
        engine_class=engine_class,
    )
    return ok(res.model_dump())


@router.get("/rides/offers/{offer_id}/fare-estimate")
def get_fare_estimate_for_offer(
    offer_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    """Calculate advisory fare breakdown for a specific ride offer."""
    res = fare_service.calculate_fare_for_offer(db, ctx.user, offer_id)
    return ok(res.model_dump())


# ---------------- University Admin Fare Policy ----------------

@admin_router.get("")
def get_admin_fare_policy(
    ctx: TenantContext = Depends(admin_only),
    db: Session = Depends(get_db),
):
    policy = fare_service.get_tenant_fare_policy(db, ctx.university_id)
    return ok(policy.model_dump())


@admin_router.patch("")
def update_admin_fare_policy(
    payload: TenantFarePolicyUpdate,
    ctx: TenantContext = Depends(admin_only),
    db: Session = Depends(get_db),
):
    policy = fare_service.update_tenant_fare_policy(db, ctx.user, payload)
    return ok(policy.model_dump())
