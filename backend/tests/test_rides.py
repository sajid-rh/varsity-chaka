"""Tests for ride offers and passenger ride requests with tenant isolation."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models import ReliabilityStats, RiderProfile, User
from app.models.types import utcnow

PASSWORD = "Sample1234"


@pytest.fixture()
def sample_users(db_session, universities):
    """Students and approved riders across DIU and AIUB."""
    diu = universities["DIU"]
    aiub = universities["AIUB"]

    def make_user(email, role, uni):
        u = User(
            university_id=uni.id,
            email=email,
            password_hash=hash_password(PASSWORD),
            full_name=email.split("@")[0].title(),
            student_id_no=f"ID-{email.split('@')[0]}",
            phone="01711000000",
            role=role,
            email_verified_at=utcnow(),
        )
        db_session.add(u)
        db_session.commit()
        return u

    diu_rider = make_user("rider1@diu.edu.bd", "student", diu)
    diu_pax = make_user("pax1@diu.edu.bd", "student", diu)
    diu_non_rider = make_user("regular@diu.edu.bd", "student", diu)
    aiub_rider = make_user("rider_aiub@aiub.edu", "student", aiub)
    aiub_pax = make_user("pax_aiub@aiub.edu", "student", aiub)

    # Approve DIU rider
    p_diu = RiderProfile(
        university_id=diu.id,
        user_id=diu_rider.id,
        motorcycle_model="Yamaha FZS",
        engine_class="cc150_plus",
        plate_number="DHK-11-2233",
        registration_doc_path="rider_docs/1/doc.jpg",
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
        registration_doc_path="rider_docs/2/doc.jpg",
        license_declared=True,
        helmet_declared=True,
        status="approved",
        approved_at=utcnow(),
        expires_at=utcnow() + timedelta(days=730),
    )
    db_session.add_all([p_diu, p_aiub])
    db_session.commit()

    rel_diu = ReliabilityStats(rider_profile_id=p_diu.id, university_id=diu.id)
    rel_aiub = ReliabilityStats(rider_profile_id=p_aiub.id, university_id=aiub.id)
    db_session.add_all([rel_diu, rel_aiub])
    db_session.commit()

    return {
        "diu_rider": diu_rider,
        "diu_pax": diu_pax,
        "diu_non_rider": diu_non_rider,
        "aiub_rider": aiub_rider,
        "aiub_pax": aiub_pax,
        "diu_profile": p_diu,
    }


def login_as(client, user):
    res = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200, res.text


def test_approved_rider_can_create_ride_offer(client, sample_users):
    rider = sample_users["diu_rider"]
    login_as(client, rider)

    dep_time = (utcnow() + timedelta(hours=2)).isoformat()
    payload = {
        "origin_lat": "23.750800",
        "origin_lng": "90.390000",
        "origin_label": "Dhanmondi 27",
        "dest_lat": "23.876000",
        "dest_lng": "90.320000",
        "dest_label": "DIU Main Gate",
        "direction": "to_campus",
        "departure_time": dep_time,
    }

    res = client.post("/api/v1/rides/offers", json=payload)
    assert res.status_code == 201
    body = res.json()
    assert body["success"] is True
    data = body["data"]
    assert data["origin_label"] == "Dhanmondi 27"
    assert data["dest_label"] == "DIU Main Gate"
    assert data["direction"] == "to_campus"
    assert data["status"] == "open"
    assert data["rider_id"] == rider.id
    assert data["motorcycle_model"] == "Yamaha FZS"


def test_non_approved_student_cannot_create_ride_offer(client, sample_users):
    non_rider = sample_users["diu_non_rider"]
    login_as(client, non_rider)

    dep_time = (utcnow() + timedelta(hours=2)).isoformat()
    payload = {
        "origin_lat": "23.750800",
        "origin_lng": "90.390000",
        "origin_label": "Dhanmondi 27",
        "dest_lat": "23.876000",
        "dest_lng": "90.320000",
        "dest_label": "DIU Main Gate",
        "direction": "to_campus",
        "departure_time": dep_time,
    }

    res = client.post("/api/v1/rides/offers", json=payload)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "rider_not_approved"


def test_expired_rider_cannot_create_ride_offer(client, sample_users, db_session):
    rider = sample_users["diu_rider"]
    profile = sample_users["diu_profile"]
    # Force expiry in the past
    profile.expires_at = utcnow() - timedelta(days=1)
    db_session.commit()

    login_as(client, rider)
    dep_time = (utcnow() + timedelta(hours=2)).isoformat()
    payload = {
        "origin_lat": "23.750800",
        "origin_lng": "90.390000",
        "origin_label": "Dhanmondi 27",
        "dest_lat": "23.876000",
        "dest_lng": "90.320000",
        "dest_label": "DIU Main Gate",
        "direction": "to_campus",
        "departure_time": dep_time,
    }

    res = client.post("/api/v1/rides/offers", json=payload)
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "rider_not_approved"


def test_departure_time_in_past_is_rejected(client, sample_users):
    rider = sample_users["diu_rider"]
    login_as(client, rider)

    past_time = (utcnow() - timedelta(minutes=10)).isoformat()
    payload = {
        "origin_lat": "23.750800",
        "origin_lng": "90.390000",
        "origin_label": "Dhanmondi 27",
        "dest_lat": "23.876000",
        "dest_lng": "90.320000",
        "dest_label": "DIU Main Gate",
        "direction": "to_campus",
        "departure_time": past_time,
    }

    res = client.post("/api/v1/rides/offers", json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_departure_time"


def test_rider_can_list_and_update_and_cancel_own_offer(client, sample_users):
    rider = sample_users["diu_rider"]
    login_as(client, rider)

    dep_time = (utcnow() + timedelta(hours=3)).isoformat()
    create_res = client.post(
        "/api/v1/rides/offers",
        json={
            "origin_lat": "23.750800",
            "origin_lng": "90.390000",
            "origin_label": "Dhanmondi 27",
            "dest_lat": "23.876000",
            "dest_lng": "90.320000",
            "dest_label": "DIU Main Gate",
            "direction": "to_campus",
            "departure_time": dep_time,
        },
    )
    offer_id = create_res.json()["data"]["id"]

    # List own
    list_res = client.get("/api/v1/rides/offers/mine")
    assert list_res.status_code == 200
    assert list_res.json()["data"]["count"] >= 1

    # Update label
    upd_res = client.patch(
        f"/api/v1/rides/offers/{offer_id}",
        json={"origin_label": "Dhanmondi 32 Bridge"},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["data"]["origin_label"] == "Dhanmondi 32 Bridge"

    # Cancel
    cancel_res = client.post(f"/api/v1/rides/offers/{offer_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"]["status"] == "cancelled"


def test_passenger_can_create_list_and_cancel_request(client, sample_users):
    pax = sample_users["diu_pax"]
    login_as(client, pax)

    pref_time = (utcnow() + timedelta(hours=2)).isoformat()
    payload = {
        "pickup_lat": "23.750000",
        "pickup_lng": "90.390000",
        "pickup_label": "Dhanmondi 27 Circle",
        "dest_lat": "23.876000",
        "dest_lng": "90.320000",
        "dest_label": "DIU Main Campus",
        "preferred_time": pref_time,
    }

    create_res = client.post("/api/v1/rides/requests", json=payload)
    assert create_res.status_code == 201
    req_id = create_res.json()["data"]["id"]
    assert create_res.json()["data"]["status"] == "open"

    # List
    list_res = client.get("/api/v1/rides/requests/mine")
    assert list_res.status_code == 200
    assert list_res.json()["data"]["count"] >= 1

    # Cancel
    cancel_res = client.post(f"/api/v1/rides/requests/{req_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["data"]["status"] == "cancelled"


def test_cross_tenant_isolation_on_offers_and_requests(client, sample_users):
    diu_rider = sample_users["diu_rider"]
    aiub_rider = sample_users["aiub_rider"]

    # AIUB rider creates offer
    login_as(client, aiub_rider)
    aiub_offer = client.post(
        "/api/v1/rides/offers",
        json={
            "origin_lat": "23.820000",
            "origin_lng": "90.420000",
            "origin_label": "Kuril Flyover",
            "dest_lat": "23.815000",
            "dest_lng": "90.425000",
            "dest_label": "AIUB Campus",
            "direction": "to_campus",
            "departure_time": (utcnow() + timedelta(hours=3)).isoformat(),
        },
    ).json()["data"]

    # DIU rider attempts to read or cancel AIUB offer -> 404 Not Found
    login_as(client, diu_rider)
    get_res = client.get(f"/api/v1/rides/offers/{aiub_offer['id']}")
    assert get_res.status_code == 404
    assert get_res.json()["error"]["code"] == "offer_not_found"

    cancel_res = client.post(f"/api/v1/rides/offers/{aiub_offer['id']}/cancel")
    assert cancel_res.status_code == 404
    assert cancel_res.json()["error"]["code"] == "offer_not_found"
