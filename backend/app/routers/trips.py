"""API endpoints for trip lifecycle, state transitions, and disputes."""
from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.schemas.trips import TripCancelRequest, TripCreate, TripDisputeRequest
from app.services import trip_service
from app.tenancy.context import TenantContext, require_role

router = APIRouter(prefix="/api/v1/trips", tags=["trips"])
student_only = require_role("student")


class HelmetConfirmPayload(BaseModel):
    helmet_confirmed: bool = Field(default=True)


class DeclinePayload(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


@router.post("/book", status_code=201)
def book_trip(
    payload: TripCreate,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.create_trip_booking(
        db, ctx.user, offer_id=payload.offer_id, request_id=payload.request_id
    )
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.get("/mine")
def list_my_trips(
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trips = trip_service.list_user_trips(db, ctx.user)
    return ok({
        "count": len(trips),
        "items": [trip_service.format_trip_view(db, t, ctx.user) for t in trips],
    })


@router.get("/{trip_id}")
def get_trip_details(
    trip_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.get_trip(db, ctx.user, trip_id)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/accept")
def accept_trip(
    trip_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.accept_trip(db, ctx.user, trip_id)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/decline")
def decline_trip(
    trip_id: int,
    payload: DeclinePayload = Body(default=DeclinePayload()),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.decline_trip(db, ctx.user, trip_id, reason=payload.reason)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/confirm")
def confirm_trip(
    trip_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.confirm_trip(db, ctx.user, trip_id)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/start")
def start_trip(
    trip_id: int,
    payload: HelmetConfirmPayload = Body(default=HelmetConfirmPayload()),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.start_trip(db, ctx.user, trip_id, helmet_confirmed=payload.helmet_confirmed)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/complete")
def complete_trip(
    trip_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.confirm_completion(db, ctx.user, trip_id)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/cancel")
def cancel_trip(
    trip_id: int,
    payload: TripCancelRequest = Body(default=TripCancelRequest()),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.cancel_trip(db, ctx.user, trip_id, reason=payload.reason)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))


@router.post("/{trip_id}/dispute")
def dispute_trip(
    trip_id: int,
    payload: TripDisputeRequest,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    trip = trip_service.dispute_trip(db, ctx.user, trip_id, reason=payload.reason)
    return ok(trip_service.format_trip_view(db, trip, ctx.user))
