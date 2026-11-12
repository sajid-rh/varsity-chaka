"""API endpoints for ride offers, requests, and explainable matching."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.schemas.matching import MatchSearchRequest
from app.schemas.rides import RideOfferCreate, RideOfferUpdate, RideRequestCreate
from app.services import matching_service, ride_service
from app.tenancy.context import TenantContext, require_role

router = APIRouter(prefix="/api/v1/rides", tags=["rides"])
student_only = require_role("student")


# ---------------- Rider Offers ----------------

@router.post("/offers", status_code=201)
def create_offer(
    payload: RideOfferCreate,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    offer = ride_service.create_offer(db, ctx.user, payload)
    return ok(ride_service.offer_to_dict(offer))


@router.get("/offers/mine")
def list_my_offers(
    status: str | None = Query(default=None),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    offers = ride_service.list_own_offers(db, ctx.user, status)
    return ok({"count": len(offers), "items": [ride_service.offer_to_dict(o) for o in offers]})


@router.get("/offers/{offer_id}")
def get_offer(
    offer_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    offer = ride_service.get_offer(db, ctx.user, offer_id)
    return ok(ride_service.offer_to_dict(offer))


@router.patch("/offers/{offer_id}")
def update_offer(
    offer_id: int,
    payload: RideOfferUpdate,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    offer = ride_service.update_offer(db, ctx.user, offer_id, payload)
    return ok(ride_service.offer_to_dict(offer))


@router.post("/offers/{offer_id}/cancel")
def cancel_offer(
    offer_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    offer = ride_service.cancel_offer(db, ctx.user, offer_id)
    return ok(ride_service.offer_to_dict(offer))


# ---------------- Passenger Requests ----------------

@router.post("/requests", status_code=201)
def create_request(
    payload: RideRequestCreate,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    request = ride_service.create_request(db, ctx.user, payload)
    return ok(ride_service.request_to_dict(request))


@router.get("/requests/mine")
def list_my_requests(
    status: str | None = Query(default=None),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    requests = ride_service.list_own_requests(db, ctx.user, status)
    return ok({"count": len(requests), "items": [ride_service.request_to_dict(r) for r in requests]})


@router.get("/requests/{request_id}")
def get_request(
    request_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    req = ride_service.get_request(db, ctx.user, request_id)
    return ok(ride_service.request_to_dict(req))


@router.post("/requests/{request_id}/cancel")
def cancel_request(
    request_id: int,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    req = ride_service.cancel_request(db, ctx.user, request_id)
    return ok(ride_service.request_to_dict(req))


# ---------------- Matching ----------------

@router.post("/matches/search")
def search_matches(
    payload: MatchSearchRequest,
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    matches = matching_service.find_matches_for_request(db, ctx.user, payload)
    return ok({"count": len(matches), "items": [m.model_dump() for m in matches]})
