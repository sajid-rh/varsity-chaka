"""Tests for the trip lifecycle state machine, single passenger capacity,
contact disclosure privacy, 30-minute auto-complete, disputes, and tenant isolation.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import ContactDisclosure, ReliabilityStats, RideOffer, RiderProfile, Trip, User
from app.models.types import utcnow
from app.services import trip_service

PASSWORD = "Sample1234"


@pytest.fixture()
def trip_world(db_session, universities):
    diu = universities["DIU"]
    aiub = universities["AIUB"]

    def make_user(email, uni, phone="01711223344"):
        u = User(
            university_id=uni.id,
            email=email,
            password_hash=hash_password(PASSWORD),
            full_name=email.split("@")[0].title(),
            student_id_no=f"ID-{email.split('@')[0]}",
            phone=phone,
            role="student",
            email_verified_at=utcnow(),
        )
        db_session.add(u)
        db_session.commit()
        return u

    r_diu = make_user("rider_diu@diu.edu.bd", diu, phone="01711111111")
    p_diu1 = make_user("pax1_diu@diu.edu.bd", diu, phone="01722222222")
    p_diu2 = make_user("pax2_diu@diu.edu.bd", diu, phone="01733333333")
    r_aiub = make_user("rider_aiub@aiub.edu", aiub, phone="01811111111")
    p_aiub = make_user("pax_aiub@aiub.edu", aiub, phone="01822222222")

    profile_diu = RiderProfile(
        university_id=diu.id,
        user_id=r_diu.id,
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
    profile_aiub = RiderProfile(
        university_id=aiub.id,
        user_id=r_aiub.id,
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
    db_session.add_all([profile_diu, profile_aiub])
    db_session.commit()

    rel_diu = ReliabilityStats(rider_profile_id=profile_diu.id, university_id=diu.id)
    rel_aiub = ReliabilityStats(rider_profile_id=profile_aiub.id, university_id=aiub.id)
    db_session.add_all([rel_diu, rel_aiub])
    db_session.commit()

    offer_diu = RideOffer(
        university_id=diu.id,
        rider_profile_id=profile_diu.id,
        rider_id=r_diu.id,
        origin_lat=Decimal("23.750800"),
        origin_lng=Decimal("90.370000"),
        origin_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU Main Gate",
        direction="to_campus",
        departure_time=utcnow() + timedelta(hours=2),
        status="open",
    )
    offer_aiub = RideOffer(
        university_id=aiub.id,
        rider_profile_id=profile_aiub.id,
        rider_id=r_aiub.id,
        origin_lat=Decimal("23.820000"),
        origin_lng=Decimal("90.420000"),
        origin_label="Kuril Flyover",
        dest_lat=Decimal("23.815000"),
        dest_lng=Decimal("90.425000"),
        dest_label="AIUB Campus",
        direction="to_campus",
        departure_time=utcnow() + timedelta(hours=2),
        status="open",
    )
    db_session.add_all([offer_diu, offer_aiub])
    db_session.commit()

    return {
        "rider_diu": r_diu,
        "pax_diu1": p_diu1,
        "pax_diu2": p_diu2,
        "rider_aiub": r_aiub,
        "pax_aiub": p_aiub,
        "offer_diu": offer_diu,
        "offer_aiub": offer_aiub,
        "profile_diu": profile_diu,
    }


def login_as(client, user):
    res = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200


def test_complete_trip_state_machine_flow(client, trip_world, db_session):
    rider = trip_world["rider_diu"]
    pax = trip_world["pax_diu1"]
    offer = trip_world["offer_diu"]

    # 1. Passenger books trip -> requested
    login_as(client, pax)
    book_res = client.post("/api/v1/trips/book", json={"offer_id": offer.id})
    assert book_res.status_code == 201
    trip_data = book_res.json()["data"]
    trip_id = trip_data["id"]
    assert trip_data["status"] == "requested"
    # Contact is NOT disclosed in requested state
    assert trip_data["rider"]["phone"] is None
    assert trip_data["passenger"]["phone"] is None

    # Verify offer is now booked
    db_session.refresh(offer)
    assert offer.status == "booked"

    # 2. Rider accepts trip -> accepted
    login_as(client, rider)
    accept_res = client.post(f"/api/v1/trips/{trip_id}/accept")
    assert accept_res.status_code == 200
    assert accept_res.json()["data"]["status"] == "accepted"
    # Still not disclosed in accepted
    assert accept_res.json()["data"]["rider"]["phone"] is None

    # 3. Passenger confirms trip -> confirmed
    login_as(client, pax)
    confirm_res = client.post(f"/api/v1/trips/{trip_id}/confirm")
    assert confirm_res.status_code == 200
    c_data = confirm_res.json()["data"]
    assert c_data["status"] == "confirmed"
    # Now contact details are revealed!
    assert c_data["rider"]["phone"] == "01711111111"

    # Verify contact disclosure logged
    disclosures = db_session.execute(
        select(ContactDisclosure).where(ContactDisclosure.trip_id == trip_id)
    ).scalars().all()
    assert len(disclosures) >= 1

    # 4. Rider starts trip with pre-ride helmet check -> in_progress
    login_as(client, rider)
    # Fails if helmet not confirmed
    fail_start = client.post(f"/api/v1/trips/{trip_id}/start", json={"helmet_confirmed": False})
    assert fail_start.status_code == 400
    assert fail_start.json()["error"]["code"] == "helmet_not_confirmed"

    start_res = client.post(f"/api/v1/trips/{trip_id}/start", json={"helmet_confirmed": True})
    assert start_res.status_code == 200
    assert start_res.json()["data"]["status"] == "in_progress"
    assert start_res.json()["data"]["helmet_confirmed_at"] is not None

    # 5. Dual completion confirmation -> completed
    # Rider marks complete first
    comp1 = client.post(f"/api/v1/trips/{trip_id}/complete")
    assert comp1.status_code == 200
    assert comp1.json()["data"]["status"] == "in_progress"  # still waiting for passenger

    # Passenger marks complete
    login_as(client, pax)
    comp2 = client.post(f"/api/v1/trips/{trip_id}/complete")
    assert comp2.status_code == 200
    assert comp2.json()["data"]["status"] == "completed"
    assert comp2.json()["data"]["completed_at"] is not None

    # Check offer closed and stats incremented
    db_session.refresh(offer)
    assert offer.status == "closed"
    stats = db_session.get(ReliabilityStats, trip_world["profile_diu"].id)
    assert stats.completed_count == 1


def test_single_passenger_capacity_enforcement(client, trip_world):
    pax1 = trip_world["pax_diu1"]
    pax2 = trip_world["pax_diu2"]
    offer = trip_world["offer_diu"]

    # First passenger books
    login_as(client, pax1)
    res1 = client.post("/api/v1/trips/book", json={"offer_id": offer.id})
    assert res1.status_code == 201

    # Second passenger attempts to book same offer -> rejected (capacity = 1)
    login_as(client, pax2)
    res2 = client.post("/api/v1/trips/book", json={"offer_id": offer.id})
    assert res2.status_code == 400
    assert res2.json()["error"]["code"] == "offer_not_available"


def test_cannot_book_own_ride(client, trip_world):
    rider = trip_world["rider_diu"]
    offer = trip_world["offer_diu"]

    login_as(client, rider)
    res = client.post("/api/v1/trips/book", json={"offer_id": offer.id})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "cannot_book_own_ride"


def test_rider_can_decline_and_reopen_offer(client, trip_world, db_session):
    pax = trip_world["pax_diu1"]
    rider = trip_world["rider_diu"]
    offer = trip_world["offer_diu"]

    login_as(client, pax)
    book_res = client.post("/api/v1/trips/book", json={"offer_id": offer.id})
    trip_id = book_res.json()["data"]["id"]

    # Rider declines
    login_as(client, rider)
    dec_res = client.post(f"/api/v1/trips/{trip_id}/decline", json={"reason": "Going another route"})
    assert dec_res.status_code == 200
    assert dec_res.json()["data"]["status"] == "cancelled"

    # Offer re-opened for other passengers
    db_session.refresh(offer)
    assert offer.status == "open"


def test_cancellation_from_any_pre_completion_state(client, trip_world, db_session):
    pax = trip_world["pax_diu1"]
    rider = trip_world["rider_diu"]
    offer = trip_world["offer_diu"]

    # Book & Accept
    login_as(client, pax)
    trip_id = client.post("/api/v1/trips/book", json={"offer_id": offer.id}).json()["data"]["id"]
    login_as(client, rider)
    client.post(f"/api/v1/trips/{trip_id}/accept")

    # Cancel from accepted state
    cancel_res = client.post(f"/api/v1/trips/{trip_id}/cancel", json={"reason": "Change of plans"})
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"]["status"] == "cancelled"
    assert cancel_res.json()["data"]["cancellation_reason"] == "Change of plans"


def test_30_minute_auto_completion_rule(client, trip_world, db_session):
    pax = trip_world["pax_diu1"]
    rider = trip_world["rider_diu"]
    offer = trip_world["offer_diu"]

    # Progress to in_progress
    login_as(client, pax)
    trip_id = client.post("/api/v1/trips/book", json={"offer_id": offer.id}).json()["data"]["id"]
    login_as(client, rider)
    client.post(f"/api/v1/trips/{trip_id}/accept")
    login_as(client, pax)
    client.post(f"/api/v1/trips/{trip_id}/confirm")
    login_as(client, rider)
    client.post(f"/api/v1/trips/{trip_id}/start", json={"helmet_confirmed": True})

    # Rider confirms completion
    client.post(f"/api/v1/trips/{trip_id}/complete")

    # Fast forward: rider confirmed 31 minutes ago, passenger remained silent
    trip = db_session.get(Trip, trip_id)
    trip.rider_confirmed_complete_at = utcnow() - timedelta(minutes=31)
    db_session.commit()

    # Trigger auto-complete check via trip details fetch
    detail_res = client.get(f"/api/v1/trips/{trip_id}")
    assert detail_res.status_code == 200
    # Auto-completed!
    assert detail_res.json()["data"]["status"] == "completed"


def test_trip_dispute(client, trip_world):
    pax = trip_world["pax_diu1"]
    rider = trip_world["rider_diu"]
    offer = trip_world["offer_diu"]

    login_as(client, pax)
    trip_id = client.post("/api/v1/trips/book", json={"offer_id": offer.id}).json()["data"]["id"]

    dispute_res = client.post(
        f"/api/v1/trips/{trip_id}/dispute",
        json={"reason": "Rider asked for extra unagreed fare"},
    )
    assert dispute_res.status_code == 200
    assert dispute_res.json()["data"]["disputed"] is True
    assert dispute_res.json()["data"]["dispute_reason"] == "Rider asked for extra unagreed fare"


def test_tenant_isolation_on_trips(client, trip_world):
    diu_pax = trip_world["pax_diu1"]
    aiub_rider = trip_world["rider_aiub"]
    aiub_pax = trip_world["pax_aiub"]
    aiub_offer = trip_world["offer_aiub"]

    # AIUB trip created
    login_as(client, aiub_pax)
    aiub_trip_id = client.post(
        "/api/v1/trips/book", json={"offer_id": aiub_offer.id}
    ).json()["data"]["id"]

    # DIU passenger tries to read, accept, or cancel AIUB trip -> 404
    login_as(client, diu_pax)
    assert client.get(f"/api/v1/trips/{aiub_trip_id}").status_code == 404
    assert client.post(f"/api/v1/trips/{aiub_trip_id}/accept").status_code == 404
    assert client.post(f"/api/v1/trips/{aiub_trip_id}/cancel").status_code == 404
