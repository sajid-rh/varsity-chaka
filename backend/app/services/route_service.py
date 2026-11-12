"""OSRM routing service with robust offline fallback.

Uses OSRM's HTTP Route API (car profile) to obtain distance, duration, and GeoJSON geometry.
Gracefully falls back to urban-adjusted Haversine calculations when OSRM is unreachable or disabled.

LIMITATION:
OSRM's default profile is calibrated for passenger cars. For motorcycles in dense urban traffic
(e.g., Dhaka), motorcycle travel duration differs due to traffic filtering and lane sharing.
This is explicitly marked as an approximation and is corrected by the ML ETA model in Feature C.
"""
import logging
from decimal import Decimal, ROUND_HALF_UP

import httpx

from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.route import RouteResult
from app.services.matching_service import haversine_distance

logger = logging.getLogger(__name__)

# Constants for urban motorcycle fallback approximation
URBAN_GRID_DETOUR_FACTOR = 1.35   # Road network factor over great-circle line
URBAN_MOTORCYCLE_SPEED_KMH = 24.0  # Average motorcycle speed in Dhaka urban traffic (approx. 6.67 m/s)


def calculate_route(
    origin_lat: Decimal | float,
    origin_lng: Decimal | float,
    dest_lat: Decimal | float,
    dest_lng: Decimal | float,
    timeout_seconds: float = 3.0,
) -> RouteResult:
    """Obtain route metrics and geometry via OSRM, with automatic fallback."""
    o_lat, o_lng = float(origin_lat), float(origin_lng)
    d_lat, d_lng = float(dest_lat), float(dest_lng)

    # 1. Coordinate sanity check
    if not (-90.0 <= o_lat <= 90.0 and -180.0 <= o_lng <= 180.0):
        raise AppError("invalid_coordinates", "Origin coordinates are out of bounds", 422)
    if not (-90.0 <= d_lat <= 90.0 and -180.0 <= d_lng <= 180.0):
        raise AppError("invalid_coordinates", "Destination coordinates are out of bounds", 422)

    if abs(o_lat - d_lat) < 1e-6 and abs(o_lng - d_lng) < 1e-6:
        raise AppError("identical_coordinates", "Origin and destination cannot be identical", 422)

    osrm_base = get_settings().osrm_base_url.rstrip("/")

    # 2. Attempt OSRM Route API
    try:
        url = f"{osrm_base}/route/v1/driving/{o_lng},{o_lat};{d_lng},{d_lat}?overview=full&geometries=geojson"
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.get(url)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok" and data.get("routes"):
                primary = data["routes"][0]
                dist_m = int(round(primary["distance"]))
                dur_s = int(round(primary["duration"]))
                geometry = primary.get("geometry")

                dist_km = (Decimal(dist_m) / Decimal("1000.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                dur_min = (Decimal(dur_s) / Decimal("60.0")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

                return RouteResult(
                    distance_m=dist_m,
                    distance_km=dist_km,
                    duration_s=dur_s,
                    duration_min=dur_min,
                    source="osrm",
                    is_fallback=False,
                    notes="OSRM car profile routing (motorcycle approximation)",
                    geometry=geometry,
                )
    except Exception as exc:
        logger.info("OSRM service unreachable (%s). Using fallback calculation.", exc)

    # 3. Deterministic Haversine Fallback
    return _haversine_fallback(o_lat, o_lng, d_lat, d_lng)


def _haversine_fallback(
    origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float
) -> RouteResult:
    """Deterministic fallback using Haversine distance with urban detour calibration."""
    great_circle_m = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
    road_distance_m = int(round(great_circle_m * URBAN_GRID_DETOUR_FACTOR))

    # Speed in m/s
    speed_ms = (URBAN_MOTORCYCLE_SPEED_KMH * 1000.0) / 3600.0
    duration_s = int(round(road_distance_m / max(1.0, speed_ms)))

    dist_km = (Decimal(road_distance_m) / Decimal("1000.0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    dur_min = (Decimal(duration_s) / Decimal("60.0")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    geometry = {
        "type": "LineString",
        "coordinates": [
            [origin_lng, origin_lat],
            [dest_lng, dest_lat],
        ],
    }

    return RouteResult(
        distance_m=road_distance_m,
        distance_km=dist_km,
        duration_s=duration_s,
        duration_min=dur_min,
        source="haversine_fallback",
        is_fallback=True,
        notes="OSRM unavailable; urban-calibrated Haversine fallback applied",
        geometry=geometry,
    )
