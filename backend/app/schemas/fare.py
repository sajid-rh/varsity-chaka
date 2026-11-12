"""Pydantic schemas for advisory fare calculation and tenant fare policies."""
from decimal import Decimal
from pydantic import BaseModel, Field


class FareBreakdown(BaseModel):
    distance_km: Decimal
    duration_min: Decimal
    fuel_price_per_litre: Decimal
    engine_class: str
    fuel_efficiency_km_l: Decimal
    base_fuel_cost: Decimal
    passenger_cost_share: Decimal
    demand_adjustment_pct: Decimal
    demand_adjustment_amount: Decimal
    maintenance_allowance: Decimal
    gross_fare: Decimal
    capped_by_ceiling: bool
    per_km_ceiling: Decimal


class FareEstimateOut(BaseModel):
    currency: str = "BDT"
    suggested_min: Decimal
    suggested_max: Decimal
    suggested_midpoint: Decimal
    breakdown: FareBreakdown
    explanation: str
    disclaimer: str = (
        "Voluntary advisory cost-sharing recommendation for student ride-sharing. "
        "Varsity Chaka does not collect fees or process payments."
    )


class FareEstimateRequest(BaseModel):
    distance_km: Decimal = Field(..., gt=0, le=200)
    duration_min: Decimal = Field(..., gt=0, le=600)
    engine_class: str = Field(default="cc125_150")
    departure_hour: int | None = Field(default=None, ge=0, le=23)
    departure_day_of_week: int | None = Field(default=None, ge=0, le=6)


class TenantFarePolicyUpdate(BaseModel):
    fuel_price_per_litre: Decimal | None = Field(default=None, gt=0, le=500)
    max_rate_per_km: Decimal | None = Field(default=None, gt=0, le=100)
    demand_adjustment_enabled: bool | None = None
    demand_cap_percent: int | None = Field(default=None, ge=0, le=50)


class TenantFarePolicyOut(BaseModel):
    university_id: int
    fuel_price_per_litre: Decimal
    max_rate_per_km: Decimal
    demand_adjustment_enabled: bool
    demand_cap_percent: int
    engine_class_efficiencies: dict[str, Decimal]
