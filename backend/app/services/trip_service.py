"""Trip lifecycle and state machine service.

State machine:
requested -> accepted -> confirmed -> in_progress -> completed
Cancellation is supported from any state before completed.

Enforces:
- 1-passenger capacity at the database level
- Server-side state transitions
- Contact detail disclosure only after confirmation
- Contact disclosure audit logging
- Dual-party completion confirmation with 30-minute auto-complete
- Dispute handling
"""
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    ContactDisclosure,
    ReliabilityStats,
    RideOffer,
    RideRequest,
    Trip,
    User,
)
from app.models.types import utcnow
from app.schemas.matching import MatchSearchRequest
from app.schemas.trips import TripParticipantView
from app.services import block_service, matching_service, rider_service
from app.services.audit_service import write_audit

VALID_TRANSITIONS = {
    "requested": {"accepted", "cancelled"},
    "accepted": {"confirmed", "cancelled"},
    "confirmed": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

AUTO_COMPLETE_MINUTES = 30


# ---------------- Trip Operations ----------------

def create_trip_booking(
    db: Session,
    passenger: User,
    offer_id: int,
    request_id: int | None = None,
) -> Trip:
    """Passenger books an open ride offer."""
    # 1. Fetch offer and verify tenant
    offer = db.execute(
        select(RideOffer).where(
            RideOffer.id == offer_id,
            RideOffer.university_id == passenger.university_id,
        )
    ).scalar_one_or_none()
    if offer is None:
        raise AppError("offer_not_found", "Ride offer not found", 404)

    # 2. Prevent booking own offer
    if offer.rider_id == passenger.id:
        raise AppError("cannot_book_own_ride", "You cannot book your own ride offer", 400)

    # 3. Check blocked status
    if block_service.are_users_blocked(db, passenger.id, offer.rider_id, passenger.university_id):
        raise AppError("user_blocked", "Cannot book ride due to user block restrictions", 403)

    # 4. Check offer status
    if offer.status != "open":
        raise AppError("offer_not_available", f"Ride offer is {offer.status}", 400)

    # 5. Check if offer is in the past
    if offer.departure_time <= utcnow():
        raise AppError("offer_expired", "This ride offer has already expired", 400)

    # 6. Check single-seat capacity at application layer before DB constraint
    existing_active = db.execute(
        select(Trip).where(
            Trip.ride_offer_id == offer.id,
            Trip.status.in_(("requested", "accepted", "confirmed", "in_progress")),
        )
    ).scalar_one_or_none()
    if existing_active is not None:
        raise AppError("seat_unavailable", "This ride already has an active booking", 400)

    # 7. Check if passenger already has an active trip
    passenger_active = db.execute(
        select(Trip).where(
            Trip.passenger_id == passenger.id,
            Trip.status.in_(("requested", "accepted", "confirmed", "in_progress")),
        )
    ).first()
    if passenger_active is not None:
        raise AppError(
            "active_trip_exists",
            "You already have an active trip. Complete or cancel it before booking another.",
            400,
        )

    # Fetch request if provided
    ride_request = None
    if request_id:
        ride_request = db.execute(
            select(RideRequest).where(
                RideRequest.id == request_id,
                RideRequest.university_id == passenger.university_id,
                RideRequest.passenger_id == passenger.id,
            )
        ).scalar_one_or_none()

    # Calculate match score & explanation for the booking
    search_req = MatchSearchRequest(
        pickup_lat=ride_request.pickup_lat if ride_request else offer.origin_lat,
        pickup_lng=ride_request.pickup_lng if ride_request else offer.origin_lng,
        pickup_label=ride_request.pickup_label if ride_request else offer.origin_label,
        dest_lat=ride_request.dest_lat if ride_request else offer.dest_lat,
        dest_lng=ride_request.dest_lng if ride_request else offer.dest_lng,
        dest_label=ride_request.dest_label if ride_request else offer.dest_label,
        preferred_time=ride_request.preferred_time if ride_request else offer.departure_time,
    )
    matches = matching_service.find_matches_for_request(db, passenger, search_req)
    match_score = None
    match_explanation = None
    for m in matches:
        if m.offer_id == offer.id:
            match_score = m.match_score
            match_explanation = m.explanation
            break

    # Calculate advisory fare range
    suggested_fare_min = None
    suggested_fare_max = None
    try:
        from app.services import fare_service
        fare_est = fare_service.calculate_fare_for_offer(db, passenger, offer.id)
        suggested_fare_min = fare_est.suggested_min
        suggested_fare_max = fare_est.suggested_max
    except Exception:
        pass

    trip = Trip(
        university_id=passenger.university_id,
        ride_offer_id=offer.id,
        ride_request_id=ride_request.id if ride_request else None,
        rider_profile_id=offer.rider_profile_id,
        rider_id=offer.rider_id,
        passenger_id=passenger.id,
        status="requested",
        active_offer_id=offer.id,  # Database-level unique capacity constraint
        match_score=match_score,
        match_explanation=match_explanation,
        suggested_fare_min=suggested_fare_min,
        suggested_fare_max=suggested_fare_max,
    )

    try:
        offer.status = "booked"
        if ride_request:
            ride_request.status = "matched"
        db.add(trip)
        db.commit()
        db.refresh(trip)
    except IntegrityError:
        db.rollback()
        raise AppError("seat_unavailable", "This ride was just booked by another user", 400)

    return trip


def accept_trip(db: Session, rider: User, trip_id: int) -> Trip:
    trip = _get_trip_scoped(db, rider.university_id, trip_id)
    if trip.rider_id != rider.id:
        raise AppError("forbidden", "Only the assigned rider can accept this trip", 403)

    if trip.status != "requested":
        raise AppError("invalid_state_transition", f"Cannot accept trip with status '{trip.status}'", 400)

    trip.status = "accepted"
    trip.accepted_at = utcnow()
    db.commit()
    db.refresh(trip)
    return trip


def decline_trip(db: Session, rider: User, trip_id: int, reason: str | None = None) -> Trip:
    trip = _get_trip_scoped(db, rider.university_id, trip_id)
    if trip.rider_id != rider.id:
        raise AppError("forbidden", "Only the assigned rider can decline this trip", 403)

    if trip.status != "requested":
        raise AppError("invalid_state_transition", f"Cannot decline trip with status '{trip.status}'", 400)

    return _cancel_internal(db, trip, cancelled_by=rider.id, reason=reason or "Declined by rider")


def confirm_trip(db: Session, user: User, trip_id: int) -> Trip:
    """Either rider or passenger confirms the accepted trip."""
    trip = _get_trip_scoped(db, user.university_id, trip_id)
    if user.id not in (trip.rider_id, trip.passenger_id):
        raise AppError("forbidden", "Only trip participants can confirm this trip", 403)

    if trip.status != "accepted":
        raise AppError("invalid_state_transition", f"Cannot confirm trip with status '{trip.status}'", 400)

    trip.status = "confirmed"
    trip.confirmed_at = utcnow()
    db.commit()
    db.refresh(trip)
    return trip


def start_trip(db: Session, rider: User, trip_id: int, helmet_confirmed: bool) -> Trip:
    """Rider starts the trip after confirming helmets."""
    trip = _get_trip_scoped(db, rider.university_id, trip_id)
    if trip.rider_id != rider.id:
        raise AppError("forbidden", "Only the assigned rider can start this trip", 403)

    if trip.status != "confirmed":
        raise AppError("invalid_state_transition", f"Cannot start trip with status '{trip.status}'", 400)

    if not helmet_confirmed:
        raise AppError(
            "helmet_not_confirmed",
            "Pre-ride safety check: Rider must confirm that both riders are wearing helmets",
            400,
        )

    trip.helmet_confirmed_at = utcnow()
    trip.started_at = utcnow()
    trip.status = "in_progress"
    db.commit()
    db.refresh(trip)
    return trip


def confirm_completion(db: Session, user: User, trip_id: int) -> Trip:
    """Either rider or passenger marks the trip as completed."""
    trip = _get_trip_scoped(db, user.university_id, trip_id)
    if user.id not in (trip.rider_id, trip.passenger_id):
        raise AppError("forbidden", "Only trip participants can confirm completion", 403)

    if trip.status != "in_progress":
        raise AppError("invalid_state_transition", f"Cannot complete trip with status '{trip.status}'", 400)

    now = utcnow()
    if user.id == trip.rider_id:
        trip.rider_confirmed_complete_at = now
    else:
        trip.passenger_confirmed_complete_at = now

    # If both participants have confirmed, finish the trip
    if trip.rider_confirmed_complete_at and trip.passenger_confirmed_complete_at:
        _finalize_completion(db, trip)

    db.commit()
    db.refresh(trip)
    return trip


def check_and_apply_auto_completion(db: Session, trip_id: int) -> Trip:
    """Apply the 30-minute auto-completion rule (FR-L5)."""
    trip = db.get(Trip, trip_id)
    if trip is None or trip.status != "in_progress":
        return trip

    now = utcnow()
    # If one confirmed and other was silent for >= 30 min
    cutoff = timedelta(minutes=AUTO_COMPLETE_MINUTES)
    one_confirmed_time = trip.rider_confirmed_complete_at or trip.passenger_confirmed_complete_at

    if one_confirmed_time and (now - one_confirmed_time >= cutoff):
        _finalize_completion(db, trip)
        db.commit()
        db.refresh(trip)

    return trip


def dispute_trip(db: Session, user: User, trip_id: int, reason: str) -> Trip:
    """Flag a trip dispute for university admin review."""
    trip = _get_trip_scoped(db, user.university_id, trip_id)
    if user.id not in (trip.rider_id, trip.passenger_id):
        raise AppError("forbidden", "Only trip participants can dispute a trip", 403)

    trip.disputed = True
    trip.dispute_reason = reason
    write_audit(
        db,
        actor=user,
        action="trip_disputed",
        target_type="trip",
        target_id=trip.id,
        details={"reason": reason, "disputed_by": user.id},
    )
    db.commit()
    db.refresh(trip)
    return trip


def cancel_trip(db: Session, user: User, trip_id: int, reason: str | None = None) -> Trip:
    """Cancel trip from any state before completed."""
    trip = _get_trip_scoped(db, user.university_id, trip_id)
    if user.id not in (trip.rider_id, trip.passenger_id):
        raise AppError("forbidden", "Only trip participants can cancel this trip", 403)

    if trip.status == "completed":
        raise AppError("cannot_cancel", "Completed trips cannot be cancelled", 400)

    if trip.status == "cancelled":
        return trip

    return _cancel_internal(db, trip, cancelled_by=user.id, reason=reason)


# ---------------- Helper Functions ----------------

def _finalize_completion(db: Session, trip: Trip) -> None:
    trip.status = "completed"
    trip.completed_at = utcnow()
    trip.active_offer_id = None  # Releases DB capacity lock

    if trip.offer:
        trip.offer.status = "closed"

    # Update rider's ReliabilityStats
    stats = db.get(ReliabilityStats, trip.rider_profile_id)
    if stats:
        stats.completed_count += 1
        stats.updated_at = utcnow()


def _cancel_internal(db: Session, trip: Trip, cancelled_by: int, reason: str | None) -> Trip:
    prior_status = trip.status
    trip.status = "cancelled"
    trip.cancelled_at = utcnow()
    trip.cancelled_by = cancelled_by
    trip.cancellation_reason = reason
    trip.active_offer_id = None  # Releases DB capacity lock

    # If cancelled before starting, re-open offer if still in future
    if prior_status in ("requested", "accepted", "confirmed") and trip.offer:
        if trip.offer.departure_time > utcnow():
            trip.offer.status = "open"
        else:
            trip.offer.status = "closed"

    if trip.request and trip.request.status == "matched":
        if trip.request.preferred_time > utcnow():
            trip.request.status = "open"
        else:
            trip.request.status = "cancelled"

    # If rider cancelled an already confirmed or in-progress trip, record in reliability stats
    if cancelled_by == trip.rider_id and prior_status in ("confirmed", "in_progress"):
        stats = db.get(ReliabilityStats, trip.rider_profile_id)
        if stats:
            stats.cancelled_count += 1
            stats.updated_at = utcnow()

    db.commit()
    db.refresh(trip)
    return trip


def _get_trip_scoped(db: Session, university_id: int, trip_id: int) -> Trip:
    trip = db.execute(
        select(Trip).where(
            Trip.id == trip_id,
            Trip.university_id == university_id,
        )
    ).scalar_one_or_none()
    if trip is None:
        raise AppError("trip_not_found", "Trip not found", 404)
    return trip


def get_trip(db: Session, user: User, trip_id: int) -> Trip:
    """Get trip scoped by university and verify viewer is participant or admin."""
    trip = _get_trip_scoped(db, user.university_id, trip_id)
    if user.role != "university_admin" and user.id not in (trip.rider_id, trip.passenger_id):
        raise AppError("forbidden", "You cannot view this trip", 403)

    # Check auto-complete rule
    check_and_apply_auto_completion(db, trip.id)
    return trip


def list_user_trips(db: Session, user: User) -> Sequence[Trip]:
    """List active and past trips for this user within tenant."""
    return db.execute(
        select(Trip)
        .where(
            Trip.university_id == user.university_id,
            or_(Trip.rider_id == user.id, Trip.passenger_id == user.id),
        )
        .order_by(Trip.created_at.desc())
    ).scalars().all()


def format_trip_view(db: Session, trip: Trip, viewer: User) -> dict:
    """Format trip for API response, enforcing contact privacy (FR-L6)."""
    rider = trip.rider
    passenger = trip.passenger
    profile = trip.offer.rider_profile if trip.offer else None

    # Contact details revealed ONLY after confirmation
    can_view_contact = trip.status in ("confirmed", "in_progress", "completed")

    rider_phone = None
    passenger_phone = None

    if can_view_contact:
        if viewer.id == trip.passenger_id or viewer.role == "university_admin":
            rider_phone = rider.phone if rider else None
            # Log contact disclosure
            _log_contact_disclosure(db, trip, viewer.id, trip.rider_id)

        if viewer.id == trip.rider_id or viewer.role == "university_admin":
            passenger_phone = passenger.phone if passenger else None
            _log_contact_disclosure(db, trip, viewer.id, trip.passenger_id)

    return {
        "id": trip.id,
        "university_id": trip.university_id,
        "status": trip.status,
        "offer_id": trip.ride_offer_id,
        "request_id": trip.ride_request_id,
        "rider": {
            "user_id": trip.rider_id,
            "full_name": rider.full_name if rider else "Rider",
            "phone": rider_phone,
        },
        "passenger": {
            "user_id": trip.passenger_id,
            "full_name": passenger.full_name if passenger else "Passenger",
            "phone": passenger_phone,
        },
        "motorcycle_model": profile.motorcycle_model if profile else "Motorcycle",
        "plate_number": profile.plate_number if profile else "",
        "origin_label": trip.offer.origin_label if trip.offer else "",
        "dest_label": trip.offer.dest_label if trip.offer else "",
        "departure_time": trip.offer.departure_time if trip.offer else trip.created_at,
        "match_score": trip.match_score,
        "match_explanation": trip.match_explanation,
        "suggested_fare_min": trip.suggested_fare_min,
        "suggested_fare_max": trip.suggested_fare_max,
        "helmet_confirmed_at": trip.helmet_confirmed_at,
        "accepted_at": trip.accepted_at,
        "confirmed_at": trip.confirmed_at,
        "started_at": trip.started_at,
        "completed_at": trip.completed_at,
        "cancelled_at": trip.cancelled_at,
        "cancelled_by": trip.cancelled_by,
        "cancellation_reason": trip.cancellation_reason,
        "rider_confirmed_complete_at": trip.rider_confirmed_complete_at,
        "passenger_confirmed_complete_at": trip.passenger_confirmed_complete_at,
        "disputed": trip.disputed,
        "dispute_reason": trip.dispute_reason,
        "created_at": trip.created_at,
        "updated_at": trip.updated_at,
    }


def _log_contact_disclosure(db: Session, trip: Trip, viewer_id: int, disclosed_user_id: int) -> None:
    """Log disclosure of contact information."""
    if viewer_id == disclosed_user_id:
        return

    # Check if already disclosed in this session/trip to prevent spamming the table
    existing = db.execute(
        select(ContactDisclosure.id).where(
            ContactDisclosure.trip_id == trip.id,
            ContactDisclosure.viewer_id == viewer_id,
            ContactDisclosure.disclosed_user_id == disclosed_user_id,
        )
    ).first()
    if existing is not None:
        return

    disclosure = ContactDisclosure(
        university_id=trip.university_id,
        trip_id=trip.id,
        viewer_id=viewer_id,
        disclosed_user_id=disclosed_user_id,
    )
    db.add(disclosure)
    db.commit()
