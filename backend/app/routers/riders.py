"""Rider application endpoints (students) and review endpoints (university admins)."""
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import ok
from app.models.rider import RIDER_STATUSES
from app.schemas.rider import EngineClass, ReasonRequest
from app.services import rider_service
from app.tenancy.context import TenantContext, require_role

router = APIRouter(prefix="/api/v1/riders", tags=["riders"])
admin_router = APIRouter(prefix="/api/v1/admin/rider-applications", tags=["admin: riders"])

student_only = require_role("student")
admin_only = require_role("university_admin")


@router.post("/apply", status_code=201)
def apply(
    motorcycle_model: str = Form(min_length=2, max_length=100),
    engine_class: EngineClass = Form(),
    plate_number: str = Form(min_length=4, max_length=30),
    license_declared: bool = Form(),
    helmet_declared: bool = Form(),
    registration_doc: UploadFile = File(),
    ctx: TenantContext = Depends(student_only),
    db: Session = Depends(get_db),
):
    # Read one byte more than the limit so an oversized file is detected without loading all of it
    data = registration_doc.file.read(rider_service.MAX_DOCUMENT_BYTES + 1)
    profile = rider_service.apply(
        db,
        ctx.user,
        motorcycle_model=motorcycle_model,
        engine_class=engine_class.value,
        plate_number=plate_number,
        license_declared=license_declared,
        helmet_declared=helmet_declared,
        document_bytes=data,
    )
    return ok(rider_service.student_view(profile))


@router.get("/me")
def my_application(ctx: TenantContext = Depends(student_only), db: Session = Depends(get_db)):
    profile = rider_service.get_own_profile(db, ctx.user)
    if profile is None:
        return ok({"status": "not_applied"})
    return ok(rider_service.student_view(profile))


# ---------------- university admin ----------------

@admin_router.get("")
def list_applications(
    status: str | None = Query(default=None, pattern="^(" + "|".join(RIDER_STATUSES) + ")$"),
    ctx: TenantContext = Depends(admin_only),
    db: Session = Depends(get_db),
):
    rows = rider_service.list_applications(db, ctx.user, status)
    return ok(
        {"count": len(rows), "items": [rider_service.admin_view(p, u) for p, u in rows]}
    )


@admin_router.get("/{profile_id}")
def get_application(profile_id: int, ctx: TenantContext = Depends(admin_only), db: Session = Depends(get_db)):
    profile, applicant = rider_service.get_application(db, ctx.user, profile_id)
    return ok(rider_service.admin_view(profile, applicant))


@admin_router.get("/{profile_id}/document")
def get_document(profile_id: int, ctx: TenantContext = Depends(admin_only), db: Session = Depends(get_db)):
    path, media_type = rider_service.document_for_admin(db, ctx.user, profile_id)
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


@admin_router.post("/{profile_id}/approve")
def approve(profile_id: int, ctx: TenantContext = Depends(admin_only), db: Session = Depends(get_db)):
    profile, applicant = rider_service.approve(db, ctx.user, profile_id)
    return ok(rider_service.admin_view(profile, applicant))


@admin_router.post("/{profile_id}/reject")
def reject(profile_id: int, payload: ReasonRequest, ctx: TenantContext = Depends(admin_only), db: Session = Depends(get_db)):
    profile, applicant = rider_service.reject(db, ctx.user, profile_id, payload.reason)
    return ok(rider_service.admin_view(profile, applicant))


@admin_router.post("/{profile_id}/suspend")
def suspend(profile_id: int, payload: ReasonRequest, ctx: TenantContext = Depends(admin_only), db: Session = Depends(get_db)):
    profile, applicant = rider_service.suspend(db, ctx.user, profile_id, payload.reason)
    return ok(rider_service.admin_view(profile, applicant))
