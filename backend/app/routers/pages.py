"""Browser pages for authentication. Like the API router, these contain no business logic:
they call the same services and render templates."""
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import AppError
from app.core.templates import templates
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services import auth_service
from app.tenancy.context import (
    ACCESS_COOKIE_NAME,
    TenantContext,
    get_tenant_context,
    set_auth_cookie,
)

# include_in_schema=False keeps these HTML pages out of the /docs API explorer
router = APIRouter(include_in_schema=False)


def current_context(request: Request, db: Session) -> TenantContext | None:
    """The logged-in context, or None for a visitor. Pages redirect instead of returning 401."""
    try:
        return get_tenant_context(request, db)
    except AppError:
        return None


def field_errors(exc: ValidationError) -> dict[str, str]:
    """Turn Pydantic errors into one plain message per field.
    The raw error objects can contain the submitted values, so they are never shown."""
    errors: dict[str, str] = {}
    for err in exc.errors():
        # An empty location means the rule that compares two fields (password confirmation)
        field = str(err["loc"][-1]) if err["loc"] else "confirm_password"
        message = err["msg"].removeprefix("Value error, ")
        errors.setdefault(field, message)
    return errors


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    target = "/dashboard" if current_context(request, db) else "/login"
    return RedirectResponse(target, status_code=303)


@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    if current_context(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request, "register.html", {"form": {}, "errors": {}, "error": None}
    )


@router.post("/register")
def register_submit(
    request: Request,
    email: str = Form(""),
    full_name: str = Form(""),
    phone: str = Form(""),
    student_id_no: str = Form(""),
    password: str = Form(""),
    confirm_password: str = Form(""),
    db: Session = Depends(get_db),
):
    # Passwords are never sent back to the page, even when validation fails
    form = {
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "student_id_no": student_id_no,
    }
    try:
        data = RegisterRequest(
            email=email,
            full_name=full_name,
            phone=phone,
            student_id_no=student_id_no,
            password=password,
            confirm_password=confirm_password,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"form": form, "errors": field_errors(exc), "error": None},
            status_code=422,
        )

    try:
        user = auth_service.register_user(db, data)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"form": form, "errors": {}, "error": exc.message},
            status_code=exc.status_code,
        )
    return templates.TemplateResponse(
        request, "register_done.html", {"email": user.email}, status_code=201
    )


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    if current_context(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"form": {}, "error": None})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    form = {"email": email}
    try:
        data = LoginRequest(email=email, password=password)
    except ValidationError:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"form": form, "error": auth_service.GENERIC_LOGIN_ERROR},
            status_code=401,
        )

    client_ip = request.client.host if request.client else "unknown"
    try:
        _, token = auth_service.login_user(db, data, client_ip)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"form": form, "error": exc.message},
            status_code=exc.status_code,
        )

    response = RedirectResponse("/dashboard", status_code=303)
    set_auth_cookie(response, token)
    return response


@router.post("/logout")
def logout_submit():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(key=ACCESS_COOKIE_NAME, path="/")
    return response


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    ctx = current_context(request, db)
    if ctx is None:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": ctx.user, "university": ctx.university},
    )


@router.get("/verify-email")
def verify_email_page(
    request: Request,
    token: str = Query("", max_length=200),
    db: Session = Depends(get_db),
):
    try:
        if len(token) < 10:
            raise AppError("invalid_token", "This verification link is invalid or has expired", 400)
        user = auth_service.verify_email(db, token)
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "verify_result.html",
            {"ok": False, "message": exc.message},
            status_code=exc.status_code,
        )
    return templates.TemplateResponse(
        request, "verify_result.html", {"ok": True, "email": user.email}
    )
