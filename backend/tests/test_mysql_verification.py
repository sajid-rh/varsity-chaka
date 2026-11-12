"""Comprehensive Phase 2 evidence verification against MySQL 8 and live engine logic."""
from datetime import datetime, timedelta
from decimal import Decimal
import os
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Block,
    ContactDisclosure,
    ReliabilityStats,
    RideOffer,
    RideRequest,
    RiderProfile,
    Trip,
    University,
    UniversitySettings,
    User,
)
from app.models.types import utcnow
from app.schemas.matching import MatchSearchRequest
from app.services import matching_service, trip_service


@pytest.fixture(scope="module")
def mysql_engine():
    """Create engine connecting to real MySQL instance using .env credentials."""
    from dotenv import dotenv_values
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    vals = dotenv_values(env_path)
    user = vals.get("MYSQL_USER", "Sajid")
    password = vals.get("MYSQL_PASSWORD", "59685968")
    host = vals.get("MYSQL_HOST", "127.0.0.1")
    port = vals.get("MYSQL_PORT", "3306")
    database = vals.get("MYSQL_DATABASE", "varsity_chaka")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"MySQL not reachable at {url}: {e}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def mysql_session_factory(mysql_engine):
    return sessionmaker(bind=mysql_engine, autoflush=False)


def test_mysql_active_offer_unique_constraint(mysql_session_factory):
    """Verify in MySQL 8 that active_offer_id strictly rejects simultaneous active bookings,
    allows NULLs, and releases upon cancellation/completion."""
    s1 = mysql_session_factory()
    s2 = mysql_session_factory()

    try:
        # Check tenant DIU
        diu = s1.execute(select(University).where(University.short_code == "DIU")).scalar_one()

        # Create test users with unique emails
        ts = int(datetime.now().timestamp())
        rider = User(
            university_id=diu.id,
            email=f"rider_concur_{ts}@diu.edu.bd",
            password_hash=hash_password("Pass1234"),
            full_name="Concurrent Rider",
            role="student",
            email_verified_at=utcnow(),
        )
        pax1 = User(
            university_id=diu.id,
            email=f"pax1_concur_{ts}@diu.edu.bd",
            password_hash=hash_password("Pass1234"),
            full_name="Concurrent Pax 1",
            role="student",
            email_verified_at=utcnow(),
        )
        pax2 = User(
            university_id=diu.id,
            email=f"pax2_concur_{ts}@diu.edu.bd",
            password_hash=hash_password("Pass1234"),
            full_name="Concurrent Pax 2",
            role="student",
            email_verified_at=utcnow(),
        )
        s1.add_all([rider, pax1, pax2])
        s1.commit()

        # Create approved rider profile
        profile = RiderProfile(
            university_id=diu.id,
            user_id=rider.id,
            motorcycle_model="Honda Hornet",
            engine_class="cc150_plus",
            plate_number=f"DHK-{ts % 10000}-CON",
            registration_doc_path="doc.jpg",
            license_declared=True,
            helmet_declared=True,
            status="approved",
            approved_at=utcnow(),
            expires_at=utcnow() + timedelta(days=730),
        )
        s1.add(profile)
        s1.commit()

        # Create ride offer
        offer = RideOffer(
            university_id=diu.id,
            rider_profile_id=profile.id,
            rider_id=rider.id,
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
        s1.add(offer)
        s1.commit()
        offer_id = offer.id

        # Transaction 1: pax1 reserves the offer
        trip1 = Trip(
            university_id=diu.id,
            ride_offer_id=offer_id,
            rider_profile_id=profile.id,
            rider_id=rider.id,
            passenger_id=pax1.id,
            status="requested",
            active_offer_id=offer_id,  # Claiming the capacity lock
        )
        s1.add(trip1)
        s1.commit()

        # Transaction 2 (simultaneous): pax2 tries to reserve same offer with active_offer_id
        trip2 = Trip(
            university_id=diu.id,
            ride_offer_id=offer_id,
            rider_profile_id=profile.id,
            rider_id=rider.id,
            passenger_id=pax2.id,
            status="requested",
            active_offer_id=offer_id,  # Colliding claim
        )
        s2.add(trip2)
        with pytest.raises(IntegrityError) as exc_info:
            s2.commit()
        s2.rollback()
        assert "Duplicate entry" in str(exc_info.value) or "active_offer_id" in str(exc_info.value)

        # Release capacity by cancelling trip 1
        trip1.status = "cancelled"
        trip1.active_offer_id = None
        s1.commit()

        # Now pax2 can successfully reserve the offer
        trip3 = Trip(
            university_id=diu.id,
            ride_offer_id=offer_id,
            rider_profile_id=profile.id,
            rider_id=rider.id,
            passenger_id=pax2.id,
            status="requested",
            active_offer_id=offer_id,
        )
        s2.add(trip3)
        s2.commit()
        assert trip3.id is not None
        assert trip3.active_offer_id == offer_id

        # Complete trip 3 and verify multiple NULLs are accepted in MySQL
        trip3.status = "completed"
        trip3.active_offer_id = None
        s2.commit()

        # Query all trips for this offer in MySQL with fresh transaction snapshot
        s1.rollback()
        all_trips = s1.execute(select(Trip).where(Trip.ride_offer_id == offer_id)).scalars().all()
        assert len(all_trips) == 2
        for t in all_trips:
            assert t.active_offer_id is None

    finally:
        s1.close()
        s2.close()


def test_matching_mathematics_controlled_verification():
    """Verify every mathematical component, normalization, and bounds in matching_service."""
    # 1. Haversine distance verification
    # Known reference: Dhanmondi 27 (23.7508, 90.3700) to DIU Ashulia (23.8760, 90.3200)
    # Direct great circle distance is approx 14.8 km (~14800 m)
    dist = matching_service.haversine_distance(23.7508, 90.3700, 23.8760, 90.3200)
    assert 14000 < dist < 16000

    # Test exact zero distance
    assert matching_service.haversine_distance(23.7508, 90.3700, 23.7508, 90.3700) == 0.0

    # 2. Trajectory alignment cosine similarity
    # Same vector -> cos = 1.0
    align_parallel = matching_service.route_vector_alignment(
        (23.0, 90.0), (24.0, 90.0), (23.2, 90.0), (23.8, 90.0)
    )
    assert abs(align_parallel - 1.0) < 1e-4

    # Opposite vector -> cos = -1.0
    align_opposite = matching_service.route_vector_alignment(
        (23.0, 90.0), (24.0, 90.0), (24.0, 90.0), (23.0, 90.0)
    )
    assert abs(align_opposite - (-1.0)) < 1e-4

    # 3. Bayesian reliability smoothing
    # Case A: Brand new rider (None stats)
    score_new, summary_new = matching_service.compute_smoothed_reliability(None)
    assert 0.80 <= score_new <= 0.90
    assert "New rider" in summary_new

    # Case B: Top rider (15 completed, 15 ratings of 5, 15 on-time)
    class FakeStats:
        completed_count = 15
        cancelled_count = 0
        rating_sum = 75
        rating_count = 15
        on_time_count = 15

    score_top, summary_top = matching_service.compute_smoothed_reliability(FakeStats())
    assert score_top > score_new
    assert score_top > 0.93
    assert "5.0★ rating" in summary_top

    # Case C: Troubled rider (2 completed, 8 cancelled, rating sum 4 from 2 ratings)
    class BadStats:
        completed_count = 2
        cancelled_count = 8
        rating_sum = 4
        rating_count = 2
        on_time_count = 1

    score_bad, summary_bad = matching_service.compute_smoothed_reliability(BadStats())
    assert score_bad < score_new
    assert score_bad < 0.65

    # 4. Explanation generation faithfulness
    explanation = matching_service.generate_explanation(
        pickup_m=180,
        detour_m=120,
        time_diff_min=3,
        overlap_score=0.92,
        reliability_summary="5.0★ rating (95% completion)",
    )
    assert "180 m" in explanation
    assert "exact departure match" in explanation
    assert "+120 m" in explanation
    assert "92% route overlap" in explanation
    assert "5.0★" in explanation
