"""Automated tests for OSRM route service, coordinate validations, and offline fallback."""
from decimal import Decimal
import pytest
import httpx

from app.core.errors import AppError
from app.services import route_service


def test_coordinate_validation():
    # Out of bounds lat
    with pytest.raises(AppError) as exc:
        route_service.calculate_route(95.0, 90.0, 23.0, 90.0)
    assert exc.value.code == "invalid_coordinates"

    # Out of bounds lng
    with pytest.raises(AppError) as exc:
        route_service.calculate_route(23.0, 195.0, 23.0, 90.0)
    assert exc.value.code == "invalid_coordinates"

    # Identical coordinates
    with pytest.raises(AppError) as exc:
        route_service.calculate_route(23.7500, 90.3800, 23.7500, 90.3800)
    assert exc.value.code == "identical_coordinates"


def test_osrm_successful_mocked_route(monkeypatch):
    """Verify parsing when OSRM returns a valid driving route."""
    fake_osrm_json = {
        "code": "Ok",
        "routes": [
            {
                "distance": 12450.6,
                "duration": 1420.2,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[90.3700, 23.7500], [90.3200, 23.8760]],
                },
            }
        ],
    }

    class FakeResponse:
        status_code = 200
        def json(self):
            return fake_osrm_json

    def fake_get(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    res = route_service.calculate_route(23.7500, 90.3700, 23.8760, 90.3200)
    assert res.source == "osrm"
    assert res.is_fallback is False
    assert res.distance_m == 12451
    assert res.distance_km == Decimal("12.45")
    assert res.duration_s == 1420
    assert res.duration_min == Decimal("23.7")
    assert res.geometry["type"] == "LineString"


def test_osrm_unreachable_triggers_deterministic_fallback(monkeypatch):
    """Verify fallback executes when OSRM server connection fails or times out."""
    def fake_timeout(*args, **kwargs):
        raise httpx.ConnectTimeout("OSRM connection timed out")

    monkeypatch.setattr(httpx.Client, "get", fake_timeout)

    res = route_service.calculate_route(23.7508, 90.3700, 23.8760, 90.3200)
    assert res.source == "haversine_fallback"
    assert res.is_fallback is True
    assert "fallback applied" in res.notes
    assert res.distance_m > 0
    assert res.duration_s > 0
    assert res.geometry["type"] == "LineString"
    assert len(res.geometry["coordinates"]) == 2


def test_osrm_malformed_response_triggers_fallback(monkeypatch):
    """Verify fallback executes when OSRM returns 500 or error code."""
    class FakeBadResponse:
        status_code = 500
        def json(self):
            return {"code": "InternalError"}

    monkeypatch.setattr(httpx.Client, "get", lambda *a, **kw: FakeBadResponse())

    res = route_service.calculate_route(23.7508, 90.3700, 23.8760, 90.3200)
    assert res.source == "haversine_fallback"
    assert res.is_fallback is True
