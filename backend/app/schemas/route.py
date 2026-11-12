"""Pydantic schemas for route estimation."""
from decimal import Decimal
from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    origin_lat: Decimal = Field(..., ge=-90, le=90)
    origin_lng: Decimal = Field(..., ge=-180, le=180)
    dest_lat: Decimal = Field(..., ge=-90, le=90)
    dest_lng: Decimal = Field(..., ge=-180, le=180)


class RouteResult(BaseModel):
    distance_m: int
    distance_km: Decimal
    duration_s: int
    duration_min: Decimal
    source: str  # "osrm" or "haversine_fallback"
    is_fallback: bool
    notes: str
    geometry: dict | None = None  # GeoJSON LineString coordinates
