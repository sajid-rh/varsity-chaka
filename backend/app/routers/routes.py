"""API endpoints for route estimation and machine learning ETA prediction."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.responses import ok
from app.schemas.eta import ETAPredictionOut
from app.schemas.route import RouteRequest, RouteResult
from app.services import eta_service, route_service
from app.tenancy.context import TenantContext, require_role

router = APIRouter(prefix="/api/v1/routes", tags=["routes"])
student_only = require_role("student")


class RouteAndETAEstimateOut(BaseModel):
    route: RouteResult
    eta: ETAPredictionOut


@router.post("/estimate")
def estimate_route_and_eta(
    payload: RouteRequest,
    ctx: TenantContext = Depends(student_only),
):
    """Calculate driving route and machine learning predicted arrival interval."""
    # 1. Calculate OSRM route (or fallback)
    route_res = route_service.calculate_route(
        origin_lat=payload.origin_lat,
        origin_lng=payload.origin_lng,
        dest_lat=payload.dest_lat,
        dest_lng=payload.dest_lng,
    )

    # 2. Predict ETA using Random Forest model
    eta_res = eta_service.predict_eta(
        distance_km=route_res.distance_km,
        base_duration_s=route_res.duration_s,
    )

    return ok({
        "route": route_res.model_dump(),
        "eta": eta_res.model_dump(),
    })
