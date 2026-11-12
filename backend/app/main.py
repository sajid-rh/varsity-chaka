"""Varsity Chaka FastAPI application entry point."""
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.database import get_db
from app.core.errors import AppError
from app.core.responses import fail, ok
from app.core.templates import FRONTEND_DIR
from app.routers import auth, pages

app = FastAPI(
    title="Varsity Chaka API",
    description="Multi-university motorcycle ride-sharing prototype",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(pages.router)
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content=fail(exc.code, exc.message))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    # Build plain details ourselves. The raw error objects can contain values
    # (even the submitted password) that must not be echoed back.
    details = [
        {
            "field": ".".join(str(part) for part in err["loc"] if part != "body"),
            "message": err["msg"].removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=fail("validation_error", "Some fields are invalid", details),
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code, content=fail("http_error", str(exc.detail))
    )


@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    """Reports whether the API is up and whether MySQL answers a trivial query."""
    try:
        db.execute(text("SELECT 1"))
        database_status = "up"
    except SQLAlchemyError:
        database_status = "down"
    return ok({"status": "ok", "database": database_status})
