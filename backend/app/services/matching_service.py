"""Explainable matching engine for Varsity Chaka.

Implements hard filtering, multi-factor weighted scoring, Bayesian reliability smoothing,
and automated human-readable explanation generation (FR-M1 through FR-M6).
"""
import math
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    ReliabilityStats,
    RideOffer,
    RideRequest,
    Trip,
    UniversitySettings,
    User,
)
from app.models.types import utcnow
from app.schemas.matching import (
    MatchComponentScores,
    MatchMetrics,
    MatchSearchRequest,
    RideMatchOut,
)
from app.services import block_service, rider_service

EARTH_RADIUS_M = 6371000.0


# ---------------- Geospatial Utilities ----------------

def haversine_distance(
    lat1: float | Decimal,
    lng1: float | Decimal,
    lat2: float | Decimal,
    lng2: float | Decimal,
) -> float:
    """Calculate the great-circle distance between two points on Earth in meters."""
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lng2) - float(lng1))

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_M * c


def route_vector_alignment(
    origin1: tuple[float, float],
    dest1: tuple[float, float],
    origin2: tuple[float, float],
    dest2: tuple[float, float],
) -> float:
    """Cosine similarity between the trajectory vectors of two routes."""
    dx1 = (dest1[1] - origin1[1]) * math.cos(math.radians((origin1[0] + dest1[0]) / 2.0))
    dy1 = dest1[0] - origin1[0]
    dx2 = (dest2[1] - origin2[1]) * math.cos(math.radians((origin2[0] + dest2[0]) / 2.0))
    dy2 = dest2[0] - origin2[0]

    mag1 = math.hypot(dx1, dy1)
    mag2 = math.hypot(dx2, dy2)
    if mag1 < 1e-7 or mag2 < 1e-7:
        return 1.0

    dot = (dx1 * dx2) + (dy1 * dy2)
    cos_theta = dot / (mag1 * mag2)
    # Clamp cosine similarity to [-1, 1]
    return max(-1.0, min(1.0, cos_theta))


# ---------------- Reliability Smoothing ----------------

def compute_smoothed_reliability(stats: ReliabilityStats | None) -> tuple[float, str]:
    """Bayesian smoothed reliability score from 0.0 to 1.0.

    Priors:
    - Prior Rating: 4.0 / 5.0 (weight M = 5)
    - Prior Completion Rate: 90% (weight M = 5)
    - Prior On-Time Rate: 85% (weight M = 5)
    """
    if stats is None:
        # Default neutral score for a new rider
        return 0.85, "New rider (baseline reliability)"

    m_prior = 5.0

    # 1. Smoothed Rating (0.0 to 1.0)
    rating_sum = stats.rating_sum
    rating_count = stats.rating_count
    smoothed_rating = (rating_sum + (4.0 * m_prior)) / (rating_count + m_prior)
    norm_rating = smoothed_rating / 5.0

    # 2. Smoothed Completion Rate (0.0 to 1.0)
    total_trips = stats.completed_count + stats.cancelled_count
    smoothed_completion = (stats.completed_count + (0.90 * m_prior)) / (
        total_trips + m_prior
    )

    # 3. Smoothed On-Time Rate (0.0 to 1.0)
    smoothed_ontime = (stats.on_time_count + (0.85 * m_prior)) / (
        stats.completed_count + m_prior
    )

    score = (
        (0.40 * norm_rating)
        + (0.35 * smoothed_completion)
        + (0.25 * smoothed_ontime)
    )
    score = max(0.0, min(1.0, score))

    if rating_count > 0:
        avg_rating = rating_sum / rating_count
        comp_pct = int(round(smoothed_completion * 100))
        summary = f"{avg_rating:.1f}★ rating ({comp_pct}% completion)"
    else:
        summary = "New rider with high baseline trust"

    return score, summary


# ---------------- Explanation Generation ----------------

def generate_explanation(
    pickup_m: int,
    detour_m: int,
    time_diff_min: int,
    overlap_score: float,
    reliability_summary: str,
) -> str:
    parts = []

    # Pickup distance commentary
    if pickup_m <= 300:
        parts.append(f"Very close pickup ({pickup_m} m, ~3 min walk)")
    elif pickup_m <= 700:
        parts.append(f"Nearby pickup ({pickup_m} m)")
    else:
        parts.append(f"Pickup within {pickup_m} m")

    # Time difference commentary
    if time_diff_min <= 5:
        parts.append("exact departure match")
    elif time_diff_min <= 15:
        parts.append(f"{time_diff_min} min departure difference")
    else:
        parts.append(f"{time_diff_min} min departure gap")

    # Detour & Overlap commentary
    overlap_pct = int(round(overlap_score * 100))
    if detour_m <= 300:
        parts.append(f"{overlap_pct}% route overlap with minimal detour (+{detour_m} m)")
    else:
        parts.append(f"{overlap_pct}% route match (+{detour_m} m detour)")

    # Reliability
    parts.append(reliability_summary)

    return ". ".join(parts) + "."


def get_distance_band(pickup_m: int) -> str:
    if pickup_m < 300:
        return "< 300 m"
    if pickup_m <= 800:
        return "300 - 800 m"
    return "> 800 m"


# ---------------- Core Matching Engine ----------------

def find_matches_for_request(
    db: Session,
    passenger: User,
    search: MatchSearchRequest,
) -> list[RideMatchOut]:
    """Find and rank all compatible ride offers for a passenger request."""
    # 1. Fetch tenant settings
    settings = db.get(UniversitySettings, passenger.university_id)
    if settings is None:
        raise AppError("tenant_error", "University settings not configured", 500)

    max_pickup_m = settings.match_max_pickup_m
    max_detour_m = settings.match_max_detour_m
    time_window_min = settings.match_time_window_min

    # 2. Get blocked user IDs
    blocked_ids = block_service.get_blocked_pair_user_ids(
        db, passenger.id, passenger.university_id
    )

    # 3. Candidate open offers for this university
    query = select(RideOffer).where(
        RideOffer.university_id == passenger.university_id,
        RideOffer.status == "open",
        RideOffer.rider_id != passenger.id,
    )
    if blocked_ids:
        query = query.where(RideOffer.rider_id.not_in(blocked_ids))

    candidate_offers = db.execute(query).scalars().all()

    # Pre-fetch active trips to verify seat availability
    active_offer_ids = set(
        db.execute(
            select(Trip.ride_offer_id).where(
                Trip.university_id == passenger.university_id,
                Trip.status.in_(("requested", "accepted", "confirmed", "in_progress")),
            )
        ).scalars().all()
    )

    # Pre-fetch reliability stats for candidate riders
    rider_profile_ids = [o.rider_profile_id for o in candidate_offers]
    stats_map = {}
    if rider_profile_ids:
        stats_rows = db.execute(
            select(ReliabilityStats).where(
                ReliabilityStats.rider_profile_id.in_(rider_profile_ids)
            )
        ).scalars().all()
        stats_map = {s.rider_profile_id: s for s in stats_rows}

    results: list[RideMatchOut] = []

    p_pickup = (float(search.pickup_lat), float(search.pickup_lng))
    p_dest = (float(search.dest_lat), float(search.dest_lng))
    p_time = search.preferred_time

    for offer in candidate_offers:
        # Hard Filter 1: Seat availability (capacity = 1)
        if offer.id in active_offer_ids:
            continue

        # Hard Filter 2: Approved & non-expired rider profile
        profile = offer.rider_profile
        if profile is None or rider_service.effective_status(profile) != "approved":
            continue

        # Hard Filter 3: Departure time window
        diff_seconds = abs((offer.departure_time - p_time).total_seconds())
        time_diff_min = int(round(diff_seconds / 60.0))
        if time_diff_min > time_window_min:
            continue

        # Hard Filter 4: Pickup distance limit
        r_origin = (float(offer.origin_lat), float(offer.origin_lng))
        r_dest = (float(offer.dest_lat), float(offer.dest_lng))
        pickup_distance_m = haversine_distance(r_origin[0], r_origin[1], p_pickup[0], p_pickup[1])
        if pickup_distance_m > max_pickup_m:
            continue

        # Hard Filter 5: Detour limit
        # Direct rider route vs combined route (origin -> passenger pickup -> passenger dest -> rider dest)
        direct_rider_dist = haversine_distance(r_origin[0], r_origin[1], r_dest[0], r_dest[1])
        leg1 = pickup_distance_m
        leg2 = haversine_distance(p_pickup[0], p_pickup[1], p_dest[0], p_dest[1])
        leg3 = haversine_distance(p_dest[0], p_dest[1], r_dest[0], r_dest[1])
        combined_dist = leg1 + leg2 + leg3
        detour_m = int(round(max(0.0, combined_dist - direct_rider_dist)))

        if detour_m > max_detour_m:
            continue

        # Destination distance
        dest_distance_m = int(round(haversine_distance(r_dest[0], r_dest[1], p_dest[0], p_dest[1])))

        # ---------------- Component Scores (0.0 to 1.0) ----------------
        # 1. Pickup proximity (1.0 at 0m, 0.0 at max_pickup_m)
        s_pickup = max(0.0, 1.0 - (pickup_distance_m / max_pickup_m))

        # 2. Time difference (1.0 at 0m, 0.0 at time_window_min)
        s_time = max(0.0, 1.0 - (time_diff_min / time_window_min))

        # 3. Detour score (1.0 at 0m, 0.0 at max_detour_m)
        s_detour = max(0.0, 1.0 - (detour_m / max_detour_m))

        # 4. Route overlap (Cosine vector alignment + shared distance factor)
        cos_align = route_vector_alignment(r_origin, r_dest, p_pickup, p_dest)
        # Transform alignment from [-1, 1] to [0, 1]
        align_factor = max(0.0, (cos_align + 1.0) / 2.0)
        overlap_factor = min(1.0, (leg2 / max(1.0, direct_rider_dist)) + 0.2)
        s_overlap = max(0.0, min(1.0, align_factor * overlap_factor))

        # 5. Destination compatibility (1.0 if <= 50m, 0.0 if >= 1000m)
        s_dest = max(0.0, min(1.0, 1.0 - (dest_distance_m / 1000.0)))

        # 6. Reliability (Bayesian smoothed)
        rel_stats = stats_map.get(offer.rider_profile_id)
        s_rel, rel_summary = compute_smoothed_reliability(rel_stats)

        # ---------------- Weighted Final Score ----------------
        w_pickup = float(settings.weight_pickup)
        w_overlap = float(settings.weight_overlap)
        w_detour = float(settings.weight_detour)
        w_time = float(settings.weight_time)
        w_dest = float(settings.weight_destination)
        w_rel = float(settings.weight_reliability)

        raw_score = (
            (w_pickup * s_pickup)
            + (w_overlap * s_overlap)
            + (w_detour * s_detour)
            + (w_time * s_time)
            + (w_dest * s_dest)
            + (w_rel * s_rel)
        )
        final_score = round(max(0.0, min(100.0, raw_score * 100.0)), 1)

        # Generate human-readable explanation
        explanation = generate_explanation(
            pickup_m=int(round(pickup_distance_m)),
            detour_m=detour_m,
            time_diff_min=time_diff_min,
            overlap_score=s_overlap,
            reliability_summary=rel_summary,
        )

        match_out = RideMatchOut(
            offer_id=offer.id,
            rider_id=offer.rider_id,
            rider_name=offer.rider.full_name if offer.rider else "Rider",
            motorcycle_model=profile.motorcycle_model,
            engine_class=profile.engine_class,
            direction=offer.direction,
            departure_time=offer.departure_time,
            approx_origin_label=offer.origin_label,
            dest_label=offer.dest_label,
            distance_band=get_distance_band(int(round(pickup_distance_m))),
            match_score=final_score,
            explanation=explanation,
            components=MatchComponentScores(
                pickup_proximity=round(s_pickup, 3),
                route_overlap=round(s_overlap, 3),
                detour=round(s_detour, 3),
                time_difference=round(s_time, 3),
                destination_compatibility=round(s_dest, 3),
                reliability=round(s_rel, 3),
            ),
            metrics=MatchMetrics(
                pickup_distance_m=int(round(pickup_distance_m)),
                detour_m=detour_m,
                time_difference_min=time_diff_min,
                destination_distance_m=dest_distance_m,
            ),
        )
        results.append(match_out)

    # Sort matches by match_score descending
    results.sort(key=lambda m: m.match_score, reverse=True)
    return results
