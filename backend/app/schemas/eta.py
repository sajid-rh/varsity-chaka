"""Pydantic schemas for ETA prediction."""
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class ETAPredictionOut(BaseModel):
    base_duration_s: int
    predicted_duration_s: int
    predicted_duration_min: Decimal
    eta_lower_bound: datetime
    eta_upper_bound: datetime
    eta_range_text: str  # e.g. "8:18 AM - 8:26 AM"
    spread_seconds: int
    prediction_method: str  # "random_forest_ml" or "rule_based_fallback"
    model_version: str | None = None
    is_fallback: bool
    notes: str = (
        "ETA prediction uses a Random Forest regression model trained on synthetic university "
        "commute data. Range represents 10th-90th percentiles of decision tree predictions."
    )


class ETARequest(BaseModel):
    distance_km: Decimal = Field(..., gt=0, le=200)
    base_duration_s: int = Field(..., gt=0, le=36000)
    departure_time: datetime | None = None
