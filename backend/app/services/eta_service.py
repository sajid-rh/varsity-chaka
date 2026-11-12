"""Machine learning ETA prediction service using Random Forest Regression.

Features:
- OSRM base travel duration and distance
- Hour of the day and day of the week
- Weekend indicator (Friday/Saturday in Bangladesh context)
- Commuter peak hour indicator (morning 7-9 AM, evening 4-7 PM)

Returns:
- Predicted duration in minutes and seconds
- Estimated arrival window (10th to 90th percentiles across decision trees)
- Deterministic rule-based fallback when model is unavailable or corrupted
"""
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.models.types import utcnow
from app.schemas.eta import ETAPredictionOut

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = REPO_ROOT / "ml" / "models" / "eta_rf_model.joblib"

_CACHED_BUNDLE: dict[str, Any] | None = None


def get_model_bundle() -> dict[str, Any] | None:
    """Load model bundle with in-memory caching."""
    global _CACHED_BUNDLE
    if _CACHED_BUNDLE is not None:
        return _CACHED_BUNDLE

    if not MODEL_PATH.exists():
        logger.warning("ETA model not found at %s. Will use rule-based fallback.", MODEL_PATH)
        return None

    try:
        bundle = joblib.load(MODEL_PATH)
        if isinstance(bundle, dict) and "model" in bundle and "features" in bundle:
            _CACHED_BUNDLE = bundle
            return _CACHED_BUNDLE
    except Exception as exc:
        logger.error("Failed to load ETA model bundle (%s). Will use fallback.", exc)

    return None


def predict_eta(
    distance_km: Decimal | float,
    base_duration_s: int,
    departure_time: datetime | None = None,
) -> ETAPredictionOut:
    """Predict travel duration and arrival window."""
    dep_time = departure_time or utcnow()
    dist = float(distance_km)
    base_s = max(60, int(base_duration_s))

    bundle = get_model_bundle()
    if bundle is not None:
        try:
            return _ml_predict(bundle, dist, base_s, dep_time)
        except Exception as exc:
            logger.error("ML ETA prediction failed (%s). Reverting to fallback.", exc)

    return _rule_based_fallback(dist, base_s, dep_time)


def _ml_predict(
    bundle: dict[str, Any], dist_km: float, base_s: int, dep_time: datetime
) -> ETAPredictionOut:
    rf = bundle["model"]
    feature_names = bundle["features"]

    hour = dep_time.hour
    dow = dep_time.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    is_weekend = 1 if dow in (4, 5) else 0

    is_morning_peak = 1 if (7 <= hour <= 9) else 0
    is_evening_peak = 1 if (16 <= hour <= 19) else 0
    is_peak = 1 if (is_morning_peak or is_evening_peak) and not is_weekend else 0

    # Build input feature vector in exact order
    feature_map = {
        "distance_km": dist_km,
        "osrm_duration_s": base_s,
        "hour_of_day": hour,
        "day_of_week": dow,
        "is_weekend": is_weekend,
        "is_peak_hour": is_peak,
    }
    x_sample = np.array([[feature_map[col] for col in feature_names]])

    # Obtain predictions from all individual decision trees in the ensemble
    tree_preds = np.array([float(tree.predict(x_sample)[0]) for tree in rf.estimators_])

    # Tree spread: 10th and 90th percentiles for arrival interval
    p10 = int(round(float(np.percentile(tree_preds, 10))))
    p90 = int(round(float(np.percentile(tree_preds, 90))))
    pred_s = int(round(float(np.mean(tree_preds))))

    # Bounds sanity checks
    p10 = max(60, min(p10, pred_s))
    p90 = max(p10 + 60, p90)
    pred_s = max(60, pred_s)

    lower_dt = dep_time + timedelta(seconds=p10)
    upper_dt = dep_time + timedelta(seconds=p90)
    spread = p90 - p10

    pred_min = (Decimal(pred_s) / Decimal("60.0")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    range_text = f"{lower_dt.strftime('%I:%M %p').lstrip('0')} - {upper_dt.strftime('%I:%M %p').lstrip('0')}"

    return ETAPredictionOut(
        base_duration_s=base_s,
        predicted_duration_s=pred_s,
        predicted_duration_min=pred_min,
        eta_lower_bound=lower_dt,
        eta_upper_bound=upper_dt,
        eta_range_text=range_text,
        spread_seconds=spread,
        prediction_method="random_forest_ml",
        model_version=bundle.get("version", "1.0.0"),
        is_fallback=False,
    )


def _rule_based_fallback(
    dist_km: float, base_s: int, dep_time: datetime
) -> ETAPredictionOut:
    """Deterministic time-of-day multiplier when ML model is unavailable."""
    hour = dep_time.hour
    dow = dep_time.weekday()
    is_weekend = dow in (4, 5)

    if not is_weekend and ((7 <= hour <= 9) or (16 <= hour <= 19)):
        mult = 1.35  # Peak weekday rush
    elif is_weekend:
        mult = 0.95  # Weekend fluid flow
    else:
        mult = 1.10  # Standard urban traffic

    pred_s = int(round(base_s * mult))
    pred_s = max(60, pred_s)

    # 15% spread around prediction
    p10 = max(60, int(round(pred_s * 0.90)))
    p90 = int(round(pred_s * 1.15))

    lower_dt = dep_time + timedelta(seconds=p10)
    upper_dt = dep_time + timedelta(seconds=p90)
    spread = p90 - p10

    pred_min = (Decimal(pred_s) / Decimal("60.0")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    range_text = f"{lower_dt.strftime('%I:%M %p').lstrip('0')} - {upper_dt.strftime('%I:%M %p').lstrip('0')}"

    return ETAPredictionOut(
        base_duration_s=base_s,
        predicted_duration_s=pred_s,
        predicted_duration_min=pred_min,
        eta_lower_bound=lower_dt,
        eta_upper_bound=upper_dt,
        eta_range_text=range_text,
        spread_seconds=spread,
        prediction_method="rule_based_fallback",
        model_version=None,
        is_fallback=True,
        notes="OSRM rule-based fallback applied because ML model was not available.",
    )
