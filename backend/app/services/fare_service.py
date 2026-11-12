"""Advisory cost-sharing fare calculation service.

Enforces:
- Transparent, non-commercial cost-sharing formula based on distance and fuel efficiency.
- Engine class fuel efficiencies (cc100, cc125_150, cc150_plus).
- Tenant-specific fuel prices and per-km ceiling enforcement.
- Capped, explainable demand adjustments (FR-F1, FR-F2, FR-F3, FR-F4).
- Advisory fare range (min, max, midpoint).
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import RideOffer, RideRequest, UniversitySettings, User
from app.models.types import utcnow
from app.schemas.fare import FareBreakdown, FareEstimateOut, TenantFarePolicyOut, TenantFarePolicyUpdate

# Known motorcycle fuel efficiencies by engine displacement class
ENGINE_EFFICIENCIES: dict[str, Decimal] = {
    "cc100": Decimal("55.0"),       # e.g., Hero Splendor (approx. 55 km/L)
    "cc125_150": Decimal("45.0"),   # e.g., Honda Shine / Yamaha FZS (approx. 45 km/L)
    "cc150_plus": Decimal("35.0"),  # e.g., Suzuki Gixxer / Yamaha R15 (approx. 35 km/L)
}

MIN_ADVISORY_BASE_FARE = Decimal("20.00")  # Minimum voluntary student cost-share


def get_engine_efficiency(engine_class: str) -> Decimal:
    return ENGINE_EFFICIENCIES.get(engine_class, Decimal("45.0"))


def estimate_demand_adjustment(
    db: Session,
    university_id: int,
    cap_percent: int,
    departure_time: datetime | None = None,
) -> Decimal:
    """Calculate a bounded demand adjustment percentage (-cap to +cap).
    
    Uses the ratio of open requests to open offers within the tenant.
    Returns Decimal percentage (e.g., Decimal("5.0") for +5%).
    """
    if cap_percent <= 0:
        return Decimal("0.0")

    # Count open offers and requests in this tenant
    open_offers = db.scalar(
        select(RideOffer.id).where(
            RideOffer.university_id == university_id,
            RideOffer.status == "open",
        )
    )
    open_requests = db.scalar(
        select(RideRequest.id).where(
            RideRequest.university_id == university_id,
            RideRequest.status == "open",
        )
    )

    # In case of no activity or insufficient data, return neutral 0%
    if open_offers is None and open_requests is None:
        # Time-of-day mild heuristic for peak university commuting hours
        now = departure_time or utcnow()
        hour = now.hour
        # Morning rush: 7:30 - 9:30 AM; Afternoon rush: 4:30 - 6:30 PM
        if (7 <= hour <= 9) or (16 <= hour <= 18):
            return min(Decimal(cap_percent), Decimal("5.0"))
        return Decimal("0.0")

    req_count = db.query(RideRequest).filter(
        RideRequest.university_id == university_id, RideRequest.status == "open"
    ).count()
    offer_count = db.query(RideOffer).filter(
        RideOffer.university_id == university_id, RideOffer.status == "open"
    ).count()

    if offer_count == 0 and req_count == 0:
        return Decimal("0.0")

    ratio = req_count / max(1, offer_count)

    # Convert ratio into percentage adjustment
    if ratio >= 2.0:
        pct = Decimal(cap_percent)
    elif ratio >= 1.3:
        pct = Decimal(cap_percent) * Decimal("0.5")
    elif ratio <= 0.5:
        pct = Decimal(-cap_percent) * Decimal("0.5")
    elif ratio <= 0.3:
        pct = Decimal(-cap_percent)
    else:
        pct = Decimal("0.0")

    return max(Decimal(-cap_percent), min(Decimal(cap_percent), pct))


def calculate_fare(
    db: Session,
    university_id: int,
    distance_km: Decimal | float,
    duration_min: Decimal | float,
    engine_class: str = "cc125_150",
    departure_time: datetime | None = None,
) -> FareEstimateOut:
    """Core advisory fare estimation algorithm respecting university policy."""
    settings = db.get(UniversitySettings, university_id)
    if settings is None:
        raise AppError("tenant_settings_missing", "University fare settings not found", 500)

    dist = Decimal(str(distance_km)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    dur = Decimal(str(duration_min)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    if dist <= Decimal("0"):
        raise AppError("invalid_distance", "Distance must be greater than zero", 422)

    # 1. Base fuel cost
    eff = get_engine_efficiency(engine_class)
    fuel_price = settings.fuel_price_per_litre
    fuel_consumed = (dist / eff).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    total_fuel_cost = (fuel_consumed * fuel_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 2. 50% Passenger fuel cost-share
    passenger_fuel_share = (total_fuel_cost * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 3. Nominal maintenance / wear contribution (0.40 BDT per km)
    maintenance_allowance = (dist * Decimal("0.40")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    base_cost = passenger_fuel_share + maintenance_allowance

    # 4. Demand adjustment
    demand_pct = Decimal("0.0")
    if settings.demand_adjustment_enabled:
        demand_pct = estimate_demand_adjustment(
            db, university_id, settings.demand_cap_percent, departure_time
        )
    demand_amount = (base_cost * (demand_pct / Decimal("100.0"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    gross_fare = base_cost + demand_amount

    # 5. Enforce tenant per-km ceiling
    max_rate = settings.max_rate_per_km
    ceiling_amount = (dist * max_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    capped = False
    if gross_fare > ceiling_amount:
        gross_fare = ceiling_amount
        capped = True

    # 6. Advisory range around midpoint
    midpoint = gross_fare.quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
    if midpoint < MIN_ADVISORY_BASE_FARE and ceiling_amount >= MIN_ADVISORY_BASE_FARE:
        midpoint = MIN_ADVISORY_BASE_FARE

    s_min = (midpoint * Decimal("0.90")).quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
    s_max = (midpoint * Decimal("1.10")).quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)

    # Ensure ceiling is strictly respected across all range boundaries
    if s_max > ceiling_amount:
        s_max = ceiling_amount.quantize(Decimal("1.00"), rounding=ROUND_HALF_UP)
    if s_min > s_max:
        s_min = s_max

    # Human-readable explanation
    demand_desc = f"{'+' if demand_pct > 0 else ''}{demand_pct}% demand adjustment" if demand_pct != 0 else "neutral demand"
    cap_desc = f" (capped by {max_rate} BDT/km ceiling)" if capped else ""
    explanation = (
        f"Advisory cost-sharing for {dist} km (~{dur} min). "
        f"Based on {eff} km/L ({engine_class}) at {fuel_price} BDT/L fuel price. "
        f"Includes 50% fuel share, nominal wear allowance, and {demand_desc}{cap_desc}."
    )

    breakdown = FareBreakdown(
        distance_km=dist,
        duration_min=dur,
        fuel_price_per_litre=fuel_price,
        engine_class=engine_class,
        fuel_efficiency_km_l=eff,
        base_fuel_cost=total_fuel_cost,
        passenger_cost_share=passenger_fuel_share,
        demand_adjustment_pct=demand_pct,
        demand_adjustment_amount=demand_amount,
        maintenance_allowance=maintenance_allowance,
        gross_fare=gross_fare,
        capped_by_ceiling=capped,
        per_km_ceiling=max_rate,
    )

    return FareEstimateOut(
        suggested_min=s_min,
        suggested_max=s_max,
        suggested_midpoint=midpoint,
        breakdown=breakdown,
        explanation=explanation,
    )


def calculate_fare_for_offer(db: Session, user: User, offer_id: int) -> FareEstimateOut:
    """Calculate fare estimate for an existing ride offer."""
    offer = db.execute(
        select(RideOffer).where(
            RideOffer.id == offer_id,
            RideOffer.university_id == user.university_id,
        )
    ).scalar_one_or_none()
    if offer is None:
        raise AppError("offer_not_found", "Ride offer not found", 404)

    # Use route_distance_m if available, or approximate using Haversine
    dist_km = Decimal("10.0")
    if offer.route_distance_m and offer.route_distance_m > 0:
        dist_km = (Decimal(offer.route_distance_m) / Decimal("1000.0")).quantize(Decimal("0.01"))
    else:
        from app.services.matching_service import haversine_distance
        h_dist = haversine_distance(offer.origin_lat, offer.origin_lng, offer.dest_lat, offer.dest_lng)
        # Apply standard 1.35 urban road factor if using great circle
        dist_km = (Decimal(str(h_dist * 1.35)) / Decimal("1000.0")).quantize(Decimal("0.01"))

    dur_min = Decimal("25.0")
    if offer.route_duration_s and offer.route_duration_s > 0:
        dur_min = (Decimal(offer.route_duration_s) / Decimal("60.0")).quantize(Decimal("0.1"))
    else:
        dur_min = (dist_km * Decimal("2.5")).quantize(Decimal("0.1"))

    engine_class = offer.rider_profile.engine_class if offer.rider_profile else "cc125_150"

    return calculate_fare(
        db=db,
        university_id=user.university_id,
        distance_km=dist_km,
        duration_min=dur_min,
        engine_class=engine_class,
        departure_time=offer.departure_time,
    )


def get_tenant_fare_policy(db: Session, university_id: int) -> TenantFarePolicyOut:
    settings = db.get(UniversitySettings, university_id)
    if settings is None:
        raise AppError("tenant_settings_missing", "University settings not found", 404)

    return TenantFarePolicyOut(
        university_id=university_id,
        fuel_price_per_litre=settings.fuel_price_per_litre,
        max_rate_per_km=settings.max_rate_per_km,
        demand_adjustment_enabled=settings.demand_adjustment_enabled,
        demand_cap_percent=settings.demand_cap_percent,
        engine_class_efficiencies=ENGINE_EFFICIENCIES,
    )


def update_tenant_fare_policy(
    db: Session, admin_user: User, payload: TenantFarePolicyUpdate
) -> TenantFarePolicyOut:
    if admin_user.role != "university_admin":
        raise AppError("forbidden", "Only university administrators can update fare policy", 403)

    settings = db.get(UniversitySettings, admin_user.university_id)
    if settings is None:
        raise AppError("tenant_settings_missing", "University settings not found", 404)

    if payload.fuel_price_per_litre is not None:
        settings.fuel_price_per_litre = payload.fuel_price_per_litre
    if payload.max_rate_per_km is not None:
        settings.max_rate_per_km = payload.max_rate_per_km
    if payload.demand_adjustment_enabled is not None:
        settings.demand_adjustment_enabled = payload.demand_adjustment_enabled
    if payload.demand_cap_percent is not None:
        settings.demand_cap_percent = payload.demand_cap_percent

    db.commit()
    db.refresh(settings)

    return get_tenant_fare_policy(db, admin_user.university_id)
