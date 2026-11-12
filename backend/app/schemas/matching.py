"""Pydantic schemas for the explainable matching service."""
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class MatchComponentScores(BaseModel):
    pickup_proximity: float
    route_overlap: float
    detour: float
    time_difference: float
    destination_compatibility: float
    reliability: float


class MatchMetrics(BaseModel):
    pickup_distance_m: int
    detour_m: int
    time_difference_min: int
    destination_distance_m: int


class RideMatchOut(BaseModel):
    offer_id: int
    rider_id: int
    rider_name: str
    motorcycle_model: str
    engine_class: str
    direction: str
    departure_time: datetime

    # Privacy preservation: before confirmation, only approximate origin and distance band are exposed
    approx_origin_label: str
    dest_label: str
    distance_band: str  # e.g. "< 300 m", "300 - 800 m", "> 800 m"

    # Explainable matching details
    match_score: float  # 0 to 100
    explanation: str
    components: MatchComponentScores
    metrics: MatchMetrics


class MatchSearchRequest(BaseModel):
    pickup_lat: Decimal
    pickup_lng: Decimal
    pickup_label: str
    dest_lat: Decimal
    dest_lng: Decimal
    dest_label: str
    preferred_time: datetime
    request_id: int | None = None
