"""Tests for the explainable matching engine, hard filters, scoring, and explanations."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models import Block, ReliabilityStats, RideOffer, RiderProfile, Trip, User
from app.models.types import utcnow
from app.schemas.matching import MatchSearchRequest
from app.services import matching_service

PASSWORD = "Sample1234"


@pytest.fixture()
def match_world(db_session, universities):
    diu = universities["DIU"]
    aiub = universities["AIUB"]

    def make_user(email, uni):
        u = User(
            university_id=uni.id,
            email=email,
            password_hash=hash_password(PASSWORD),
            full_name=email.split("@")[0].title(),
            student_id_no=f"ID-{email.split('@')[0]}",
            role="student",
            email_verified_at=utcnow(),
        )
        db_session.add(u)
        db_session.commit()
        return u

    rider1 = make_user("rider1@diu.edu.bd", diu)
    pax1 = make_user("pax1@diu.edu.bd", diu)
    aiub_rider = make_user("aiub_rider@aiub.edu", aiub)

    # Approve DIU rider
    p_diu = RiderProfile(
        university_id=diu.id,
        user_id=rider1.id,
        motorcycle_model="Yamaha FZS",
        engine_class="cc150_plus",
        plate_number="DHK-11-2233",
        registration_doc_path="doc.jpg",
        license_declared=True,
        helmet_declared=True,
        status="approved",
        approved_at=utcnow(),
        expires_at=utcnow() + timedelta(days=730),
    )
    # Approve AIUB rider
    p_aiub = RiderProfile(
        university_id=aiub.id,
        user_id=aiub_rider.id,
        motorcycle_model="Honda CB",
        engine_class="cc125_150",
        plate_number="DHK-22-4455",
        registration_doc_path="doc.jpg",
        license_declared=True,
        helmet_declared=True,
        status="approved",
        approved_at=utcnow(),
        expires_at=utcnow() + timedelta(days=730),
    )
    db_session.add_all([p_diu, p_aiub])
    db_session.commit()

    rel_diu = ReliabilityStats(
        rider_profile_id=p_diu.id,
        university_id=diu.id,
        completed_count=10,
        rating_sum=48,
        rating_count=10,
        on_time_count=9,
    )
    db_session.add(rel_diu)
    db_session.commit()

    # Offer departing in 30 minutes from Dhanmondi 27 to DIU
    # Dhanmondi 27: (23.750800, 90.370000)
    # DIU Ashulia: (23.876000, 90.320000)
    dep_time = utcnow() + timedelta(minutes=30)
    offer_diu = RideOffer(
        university_id=diu.id,
        rider_profile_id=p_diu.id,
        rider_id=rider1.id,
        origin_lat=Decimal("23.750800"),
        origin_lng=Decimal("90.370000"),
        origin_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU Main Gate",
        direction="to_campus",
        departure_time=dep_time,
        status="open",
    )
    # Similar AIUB offer
    offer_aiub = RideOffer(
        university_id=aiub.id,
        rider_profile_id=p_aiub.id,
        rider_id=aiub_rider.id,
        origin_lat=Decimal("23.750800"),
        origin_lng=Decimal("90.370000"),
        origin_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="AIUB Campus",
        direction="to_campus",
        departure_time=dep_time,
        status="open",
    )
    db_session.add_all([offer_diu, offer_aiub])
    db_session.commit()

    return {
        "rider1": rider1,
        "pax1": pax1,
        "aiub_rider": aiub_rider,
        "offer_diu": offer_diu,
        "offer_aiub": offer_aiub,
        "profile_diu": p_diu,
        "dep_time": dep_time,
    }


def test_matching_finds_compatible_offer_with_explanation(db_session, match_world):
    pax = match_world["pax1"]
    dep_time = match_world["dep_time"]

    # Passenger request close to Dhanmondi 27 (200m away) departing 5 min after rider
    req = MatchSearchRequest(
        pickup_lat=Decimal("23.751500"),
        pickup_lng=Decimal("90.371000"),
        pickup_label="Dhanmondi 27 Rapa Plaza",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU Main Gate",
        preferred_time=dep_time + timedelta(minutes=5),
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 1
    m = matches[0]
    assert m.offer_id == match_world["offer_diu"].id
    assert m.match_score > 70.0
    assert m.distance_band == "< 300 m"
    assert m.metrics.time_difference_min == 5
    assert "DIU Main Gate" in m.dest_label
    assert "★ rating" in m.explanation
    assert m.components.pickup_proximity > 0.7
    assert m.components.reliability > 0.8


def test_cross_tenant_offers_strictly_excluded(db_session, match_world):
    pax = match_world["pax1"]  # DIU student
    dep_time = match_world["dep_time"]

    req = MatchSearchRequest(
        pickup_lat=Decimal("23.750800"),
        pickup_lng=Decimal("90.370000"),
        pickup_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="Campus",
        preferred_time=dep_time,
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    matched_offer_ids = {m.offer_id for m in matches}
    # AIUB offer must NOT be present
    assert match_world["offer_aiub"].id not in matched_offer_ids


def test_expired_and_unapproved_riders_are_excluded(db_session, match_world):
    pax = match_world["pax1"]
    dep_time = match_world["dep_time"]
    profile = match_world["profile_diu"]

    # 1. Expired rider
    profile.expires_at = utcnow() - timedelta(days=1)
    db_session.commit()

    req = MatchSearchRequest(
        pickup_lat=Decimal("23.750800"),
        pickup_lng=Decimal("90.370000"),
        pickup_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU",
        preferred_time=dep_time,
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 0

    # 2. Suspended rider
    profile.expires_at = utcnow() + timedelta(days=700)
    profile.status = "suspended"
    db_session.commit()

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 0


def test_blocked_pairs_never_match(db_session, match_world):
    pax = match_world["pax1"]
    rider = match_world["rider1"]
    dep_time = match_world["dep_time"]

    # Passenger blocks rider
    block = Block(
        university_id=pax.university_id,
        blocker_id=pax.id,
        blocked_id=rider.id,
    )
    db_session.add(block)
    db_session.commit()

    req = MatchSearchRequest(
        pickup_lat=Decimal("23.750800"),
        pickup_lng=Decimal("90.370000"),
        pickup_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU",
        preferred_time=dep_time,
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 0


def test_time_window_filtering(db_session, match_world):
    pax = match_world["pax1"]
    dep_time = match_world["dep_time"]

    # Request preferred time 45 min after departure (default window is 20 min)
    req = MatchSearchRequest(
        pickup_lat=Decimal("23.750800"),
        pickup_lng=Decimal("90.370000"),
        pickup_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU",
        preferred_time=dep_time + timedelta(minutes=45),
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 0


def test_pickup_distance_limit_filtering(db_session, match_world):
    pax = match_world["pax1"]
    dep_time = match_world["dep_time"]

    # Pickup far away in Mirpur (~8 km from Dhanmondi)
    req = MatchSearchRequest(
        pickup_lat=Decimal("23.805000"),
        pickup_lng=Decimal("90.360000"),
        pickup_label="Mirpur 10",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU",
        preferred_time=dep_time,
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 0


def test_booked_or_active_seat_excluded_from_matching(db_session, match_world):
    pax = match_world["pax1"]
    offer = match_world["offer_diu"]
    dep_time = match_world["dep_time"]

    # Simulate an active trip on this offer
    trip = Trip(
        university_id=offer.university_id,
        ride_offer_id=offer.id,
        rider_profile_id=offer.rider_profile_id,
        rider_id=offer.rider_id,
        passenger_id=pax.id,
        status="confirmed",
        active_offer_id=offer.id,
    )
    db_session.add(trip)
    db_session.commit()

    req = MatchSearchRequest(
        pickup_lat=Decimal("23.750800"),
        pickup_lng=Decimal("90.370000"),
        pickup_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU",
        preferred_time=dep_time,
    )

    matches = matching_service.find_matches_for_request(db_session, pax, req)
    assert len(matches) == 0
