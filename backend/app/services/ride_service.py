"""Ride offers and requests service. Enforces university-level scoping and rider approval."""
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import RideOffer, RideRequest, Trip, User
from app.models.types import utcnow
from app.schemas.rides import RideOfferCreate, RideOfferUpdate, RideRequestCreate
from app.services import rider_service


def create_offer(db: Session, user: User, payload: RideOfferCreate) -> RideOffer:
    """Approved riders create a ride offer."""
    profile = rider_service.get_approved_profile(db, user)
    if profile is None:
        raise AppError(
            "rider_not_approved",
            "Only approved riders with active credentials can post a ride offer",
            403,
        )

    # Departure time must be in the future
    now = utcnow()
    if payload.departure_time <= now:
        raise AppError(
            "invalid_departure_time",
            "Departure time must be in the future",
            422,
        )

    # Check for duplicate open offer at similar time
    existing = db.execute(
        select(RideOffer).where(
            RideOffer.rider_id == user.id,
            RideOffer.status == "open",
            RideOffer.departure_time == payload.departure_time,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise AppError(
            "duplicate_offer",
            "You already have an open ride offer departing at this time",
            400,
        )

    offer = RideOffer(
        university_id=user.university_id,
        rider_profile_id=profile.id,
        rider_id=user.id,
        origin_lat=payload.origin_lat,
        origin_lng=payload.origin_lng,
        origin_label=payload.origin_label,
        dest_lat=payload.dest_lat,
        dest_lng=payload.dest_lng,
        dest_label=payload.dest_label,
        direction=payload.direction,
        departure_time=payload.departure_time,
        route_distance_m=payload.route_distance_m,
        route_duration_s=payload.route_duration_s,
        status="open",
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def get_offer(db: Session, user: User, offer_id: int) -> RideOffer:
    """Retrieve an offer scoped strictly by tenant."""
    offer = db.execute(
        select(RideOffer).where(
            RideOffer.id == offer_id,
            RideOffer.university_id == user.university_id,
        )
    ).scalar_one_or_none()

    if offer is None:
        raise AppError("offer_not_found", "Ride offer not found", 404)
    return offer


def list_own_offers(
    db: Session, user: User, status: str | None = None
) -> Sequence[RideOffer]:
    query = (
        select(RideOffer)
        .where(
            RideOffer.university_id == user.university_id,
            RideOffer.rider_id == user.id,
        )
        .order_by(RideOffer.departure_time.desc())
    )
    if status:
        query = query.where(RideOffer.status == status)
    return db.execute(query).scalars().all()


def update_offer(
    db: Session, user: User, offer_id: int, payload: RideOfferUpdate
) -> RideOffer:
    offer = get_offer(db, user, offer_id)
    if offer.rider_id != user.id:
        raise AppError("forbidden", "You cannot edit another rider's offer", 403)

    if offer.status != "open":
        raise AppError(
            "offer_not_editable",
            f"Cannot update offer with status '{offer.status}'",
            400,
        )

    if payload.departure_time is not None:
        if payload.departure_time <= utcnow():
            raise AppError(
                "invalid_departure_time",
                "Departure time must be in the future",
                422,
            )
        offer.departure_time = payload.departure_time

    if payload.origin_label is not None:
        offer.origin_label = payload.origin_label
    if payload.dest_label is not None:
        offer.dest_label = payload.dest_label

    db.commit()
    db.refresh(offer)
    return offer


def cancel_offer(db: Session, user: User, offer_id: int) -> RideOffer:
    offer = get_offer(db, user, offer_id)
    if offer.rider_id != user.id:
        raise AppError("forbidden", "You cannot cancel another rider's offer", 403)

    if offer.status == "cancelled":
        return offer

    if offer.status in ("closed", "booked"):
        # Check if there is an active trip on this offer
        active_trip = db.execute(
            select(Trip).where(
                Trip.ride_offer_id == offer.id,
                Trip.status.in_(("confirmed", "in_progress")),
            )
        ).scalar_one_or_none()
        if active_trip is not None:
            raise AppError(
                "trip_in_progress",
                "Cannot cancel offer while a trip is active. Cancel the trip first.",
                400,
            )

    offer.status = "cancelled"
    db.commit()
    db.refresh(offer)
    return offer


# ---------------- Passenger Requests ----------------

def create_request(
    db: Session, user: User, payload: RideRequestCreate
) -> RideRequest:
    now = utcnow()
    if payload.preferred_time <= now:
        raise AppError(
            "invalid_preferred_time",
            "Preferred time must be in the future",
            422,
        )

    request = RideRequest(
        university_id=user.university_id,
        passenger_id=user.id,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        pickup_label=payload.pickup_label,
        dest_lat=payload.dest_lat,
        dest_lng=payload.dest_lng,
        dest_label=payload.dest_label,
        preferred_time=payload.preferred_time,
        status="open",
    )
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def get_request(db: Session, user: User, request_id: int) -> RideRequest:
    request = db.execute(
        select(RideRequest).where(
            RideRequest.id == request_id,
            RideRequest.university_id == user.university_id,
        )
    ).scalar_one_or_none()

    if request is None:
        raise AppError("request_not_found", "Ride request not found", 404)
    return request


def list_own_requests(
    db: Session, user: User, status: str | None = None
) -> Sequence[RideRequest]:
    query = (
        select(RideRequest)
        .where(
            RideRequest.university_id == user.university_id,
            RideRequest.passenger_id == user.id,
        )
        .order_by(RideRequest.preferred_time.desc())
    )
    if status:
        query = query.where(RideRequest.status == status)
    return db.execute(query).scalars().all()


def cancel_request(db: Session, user: User, request_id: int) -> RideRequest:
    request = get_request(db, user, request_id)
    if request.passenger_id != user.id:
        raise AppError("forbidden", "You cannot cancel another user's request", 403)

    if request.status == "cancelled":
        return request

    if request.status == "matched":
        # Check active trips
        active_trip = db.execute(
            select(Trip).where(
                Trip.ride_request_id == request.id,
                Trip.status.in_(("confirmed", "in_progress")),
            )
        ).scalar_one_or_none()
        if active_trip is not None:
            raise AppError(
                "trip_in_progress",
                "Cannot cancel request while a trip is active. Cancel the trip first.",
                400,
            )

    request.status = "cancelled"
    db.commit()
    db.refresh(request)
    return request


# ---------------- View Helpers ----------------

def offer_to_dict(offer: RideOffer) -> dict:
    profile = offer.rider_profile
    rider = offer.rider
    return {
        "id": offer.id,
        "university_id": offer.university_id,
        "rider_id": offer.rider_id,
        "rider_name": rider.full_name if rider else "Rider",
        "motorcycle_model": profile.motorcycle_model if profile else "Motorcycle",
        "plate_number": profile.plate_number if profile else "",
        "engine_class": profile.engine_class if profile else "cc100",
        "origin_lat": offer.origin_lat,
        "origin_lng": offer.origin_lng,
        "origin_label": offer.origin_label,
        "dest_lat": offer.dest_lat,
        "dest_lng": offer.dest_lng,
        "dest_label": offer.dest_label,
        "direction": offer.direction,
        "departure_time": offer.departure_time,
        "route_distance_m": offer.route_distance_m,
        "route_duration_s": offer.route_duration_s,
        "status": offer.status,
        "created_at": offer.created_at,
        "updated_at": offer.updated_at,
    }


def request_to_dict(req: RideRequest) -> dict:
    passenger = req.passenger
    return {
        "id": req.id,
        "university_id": req.university_id,
        "passenger_id": req.passenger_id,
        "passenger_name": passenger.full_name if passenger else "Passenger",
        "pickup_lat": req.pickup_lat,
        "pickup_lng": req.pickup_lng,
        "pickup_label": req.pickup_label,
        "dest_lat": req.dest_lat,
        "dest_lng": req.dest_lng,
        "dest_label": req.dest_label,
        "preferred_time": req.preferred_time,
        "status": req.status,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
    }
