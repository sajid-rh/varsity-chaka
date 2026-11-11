"""Varsity Chaka FastAPI application entry point."""
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db

app = FastAPI(
    title="Varsity Chaka API",
    description="Multi-university motorcycle ride-sharing prototype",
    version="0.1.0",
)


def ok(data):
    """Standard success envelope (see docs/02-architecture.md, section 8)."""
    return {"success": True, "data": data, "error": None}


@app.get("/api/v1/health")
def health(db: Session = Depends(get_db)):
    """Reports whether the API is up and whether MySQL answers a trivial query."""
    try:
        db.execute(text("SELECT 1"))
        database_status = "up"
    except SQLAlchemyError:
        database_status = "down"
    return ok({"status": "ok", "database": database_status})
