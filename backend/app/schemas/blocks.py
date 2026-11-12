"""Pydantic schemas for user blocks."""
from datetime import datetime
from pydantic import BaseModel, Field


class BlockCreate(BaseModel):
    blocked_user_id: int = Field(..., gt=0)


class BlockOut(BaseModel):
    id: int
    university_id: int
    blocker_id: int
    blocked_id: int
    created_at: datetime
