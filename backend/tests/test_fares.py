"""Automated tests for advisory fare calculation and tenant policy management."""
from datetime import timedelta
from decimal import Decimal
import pytest

from app.core.security import hash_password
from app.models import RiderProfile, RideOffer, UniversitySettings, User
from app.models.types import utcnow
from app.services import fare_service

PASSWORD = "Sample1234"


@pytest.fixture()
def fare_world(db_session, universities):
    diu = universities["DIU"]
    aiub = universities["AIUB"]

    def make(email, uni, role="student"):
        u = User(
            university_id=uni.id,
            email=email,
            password_hash=hash_password(PASSWORD),
            full_name=email.split("@")[0].title(),
            student_id_no=f"ID-{email.split('@')[0]}",
            role=role,
            email_verified_at=utcnow(),
        )
        db_session.add(u)
        db_session.commit()
        return u

    diu_student = make("diu_student@diu.edu.bd", diu)
    diu_admin = make("diu_admin@diu.edu.bd", diu, role="university_admin")
    aiub_admin = make("aiub_admin@aiub.edu", aiub, role="university_admin")

    profile = RiderProfile(
        university_id=diu.id,
        user_id=diu_student.id,
        motorcycle_model="Honda Shine",
        engine_class="cc125_150",
        plate_number="DHK-11-2244",
        registration_doc_path="doc.jpg",
        license_declared=True,
        helmet_declared=True,
        status="approved",
        approved_at=utcnow(),
        expires_at=utcnow() + timedelta(days=730),
    )
    db_session.add(profile)
    db_session.commit()

    offer = RideOffer(
        university_id=diu.id,
        rider_profile_id=profile.id,
        rider_id=diu_student.id,
        origin_lat=Decimal("23.750800"),
        origin_lng=Decimal("90.370000"),
        origin_label="Dhanmondi 27",
        dest_lat=Decimal("23.876000"),
        dest_lng=Decimal("90.320000"),
        dest_label="DIU Main Gate",
        direction="to_campus",
        departure_time=utcnow() + timedelta(hours=2),
        route_distance_m=15000,
        route_duration_s=1800,
        status="open",
    )
    db_session.add(offer)
    db_session.commit()

    return {
        "diu_student": diu_student,
        "diu_admin": diu_admin,
        "aiub_admin": aiub_admin,
        "offer": offer,
        "diu": diu,
        "aiub": aiub,
    }


def login_as(client, user):
    res = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200


def test_fuel_cost_calculation_across_engine_classes(db_session, fare_world):
    diu = fare_world["diu"]
    dist = Decimal("10.0")  # 10 km
    dur = Decimal("20.0")

    # Fuel price is 130.00 BDT/L in fixture
    # 1. cc100 (55 km/L): fuel = 10/55 = 0.1818 L -> total = 23.63 BDT -> 50% = 11.82 BDT
    res_100 = fare_service.calculate_fare(db_session, diu.id, dist, dur, engine_class="cc100")
    # 2. cc150_plus (35 km/L): fuel = 10/35 = 0.2857 L -> total = 37.14 BDT -> 50% = 18.57 BDT
    res_150 = fare_service.calculate_fare(db_session, diu.id, dist, dur, engine_class="cc150_plus")

    assert res_100.breakdown.fuel_efficiency_km_l == Decimal("55.0")
    assert res_150.breakdown.fuel_efficiency_km_l == Decimal("35.0")
    assert res_150.breakdown.passenger_cost_share > res_100.breakdown.passenger_cost_share
    assert res_100.suggested_min >= Decimal("15.00")
    assert res_150.suggested_max > res_100.suggested_max


def test_per_km_ceiling_enforcement(db_session, fare_world):
    diu = fare_world["diu"]
    settings = db_session.get(UniversitySettings, diu.id)
    # Set a strict ceiling: 1.20 BDT/km (below gross fare of ~1.75 BDT/km)
    settings.max_rate_per_km = Decimal("1.20")
    db_session.commit()

    # 10 km trip -> absolute maximum permitted fare is 12.00 BDT
    res = fare_service.calculate_fare(db_session, diu.id, Decimal("10.0"), Decimal("25.0"))
    assert res.breakdown.capped_by_ceiling is True
    assert res.breakdown.gross_fare <= Decimal("12.00")
    assert res.suggested_max <= Decimal("12.00")


def test_demand_adjustment_and_neutral_fallback(db_session, fare_world):
    diu = fare_world["diu"]
    settings = db_session.get(UniversitySettings, diu.id)
    settings.demand_cap_percent = 15
    db_session.commit()

    # In clean state with 1 offer and 0 requests, ratio is 0 -> demand adjustment is bounded
    adj = fare_service.estimate_demand_adjustment(db_session, diu.id, settings.demand_cap_percent)
    assert -15 <= adj <= 15


def test_invalid_distance_rejected(db_session, fare_world):
    diu = fare_world["diu"]
    with pytest.raises(Exception):
        fare_service.calculate_fare(db_session, diu.id, Decimal("0.0"), Decimal("10.0"))
    with pytest.raises(Exception):
        fare_service.calculate_fare(db_session, diu.id, Decimal("-5.0"), Decimal("10.0"))


def test_fare_estimate_api_endpoint(client, fare_world):
    student = fare_world["diu_student"]
    login_as(client, student)

    res = client.get("/api/v1/fares/estimate?distance_km=12.5&duration_min=28&engine_class=cc125_150")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["suggested_min"] > 0
    assert data["suggested_midpoint"] >= data["suggested_min"]
    assert data["suggested_max"] >= data["suggested_midpoint"]
    assert "Voluntary advisory" in data["disclaimer"]
    assert "12.50 km" in data["explanation"]


def test_fare_estimate_for_existing_offer_api(client, fare_world):
    student = fare_world["diu_student"]
    offer = fare_world["offer"]
    login_as(client, student)

    res = client.get(f"/api/v1/rides/offers/{offer.id}/fare-estimate")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["breakdown"]["distance_km"] == Decimal("15.00")


def test_admin_fare_policy_get_and_update(client, fare_world):
    admin = fare_world["diu_admin"]
    student = fare_world["diu_student"]

    # Student cannot access admin fare policy -> 403
    login_as(client, student)
    assert client.get("/api/v1/admin/fare-policy").status_code == 403

    # Admin accesses and updates policy
    login_as(client, admin)
    get_res = client.get("/api/v1/admin/fare-policy")
    assert get_res.status_code == 200
    assert float(get_res.json()["data"]["fuel_price_per_litre"]) == 130.0

    patch_res = client.patch(
        "/api/v1/admin/fare-policy",
        json={"fuel_price_per_litre": "142.50", "max_rate_per_km": "18.00", "demand_cap_percent": 12},
    )
    assert patch_res.status_code == 200
    assert float(patch_res.json()["data"]["fuel_price_per_litre"]) == 142.50
    assert float(patch_res.json()["data"]["max_rate_per_km"]) == 18.00
    assert patch_res.json()["data"]["demand_cap_percent"] == 12


def test_cross_tenant_admin_policy_isolation(client, fare_world):
    diu_admin = fare_world["diu_admin"]
    aiub_admin = fare_world["aiub_admin"]

    # AIUB admin updates their fuel price to 155.00
    login_as(client, aiub_admin)
    client.patch("/api/v1/admin/fare-policy", json={"fuel_price_per_litre": "155.00"})

    # DIU admin checks their own fuel price: must remain unchanged
    login_as(client, diu_admin)
    res = client.get("/api/v1/admin/fare-policy")
    assert res.status_code == 200
    assert res.json()["data"]["fuel_price_per_litre"] != "155.00"
