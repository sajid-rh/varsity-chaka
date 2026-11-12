"""Automated tests for machine learning ETA prediction, synthetic data, and tree spread intervals."""
from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.core.security import hash_password
from app.models import User
from app.models.types import utcnow
from app.services import eta_service
from ml.data.generate_synthetic_trips import generate_synthetic_dataset

PASSWORD = "Sample1234"


def test_synthetic_dataset_generation_reproducibility():
    """Verify fixed random seed produces identical dataset for scientific reproducibility."""
    df1 = generate_synthetic_dataset(num_samples=100, random_seed=42)
    df2 = generate_synthetic_dataset(num_samples=100, random_seed=42)
    assert df1.equals(df2)
    assert len(df1) == 100
    assert "distance_km" in df1.columns
    assert "actual_duration_s" in df1.columns
    assert (df1["actual_duration_s"] >= 120).all()


def test_eta_prediction_with_model():
    """Verify ML ETA prediction using trained Random Forest bundle."""
    dep_time = datetime(2026, 11, 16, 8, 30, tzinfo=timezone.utc)  # Monday 8:30 AM (peak hour)
    res = eta_service.predict_eta(
        distance_km=Decimal("12.5"),
        base_duration_s=1200,  # 20 min base duration
        departure_time=dep_time,
    )

    assert res.prediction_method == "random_forest_ml"
    assert res.is_fallback is False
    assert res.model_version == "1.0.0"
    assert res.predicted_duration_s >= 60
    assert res.eta_lower_bound < res.eta_upper_bound
    assert res.spread_seconds > 0
    assert "-" in res.eta_range_text
    assert res.predicted_duration_min > 0


def test_eta_fallback_when_model_missing(monkeypatch):
    """Verify deterministic rule-based fallback when model bundle cannot be loaded."""
    monkeypatch.setattr(eta_service, "get_model_bundle", lambda: None)

    dep_time = datetime(2026, 11, 16, 8, 30, tzinfo=timezone.utc)  # Monday rush
    res = eta_service.predict_eta(
        distance_km=Decimal("10.0"),
        base_duration_s=1000,
        departure_time=dep_time,
    )

    assert res.prediction_method == "rule_based_fallback"
    assert res.is_fallback is True
    assert res.predicted_duration_s >= 1000  # Peak multiplier >= 1.0
    assert res.eta_lower_bound <= res.eta_upper_bound


def test_route_and_eta_endpoint(client, db_session, universities):
    """Test full integration endpoint POST /api/v1/routes/estimate."""
    diu = universities["DIU"]
    student = User(
        university_id=diu.id,
        email="route_student@diu.edu.bd",
        password_hash=hash_password(PASSWORD),
        full_name="Route Student",
        role="student",
        email_verified_at=utcnow(),
    )
    db_session.add(student)
    db_session.commit()

    # Login
    client.post("/api/v1/auth/login", json={"email": student.email, "password": PASSWORD})

    res = client.post(
        "/api/v1/routes/estimate",
        json={
            "origin_lat": "23.750800",
            "origin_lng": "90.370000",
            "dest_lat": "23.876000",
            "dest_lng": "90.320000",
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert "route" in data
    assert "eta" in data
    assert data["route"]["distance_m"] > 0
    assert data["eta"]["predicted_duration_s"] > 0
    assert data["eta"]["eta_range_text"] is not None
