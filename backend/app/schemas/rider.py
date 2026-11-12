"""Request models for the rider endpoints."""
from enum import Enum

from pydantic import BaseModel, Field


class EngineClass(str, Enum):
    """Drives the default fuel efficiency used by the fare module later."""

    cc100 = "cc100"
    cc125_150 = "cc125_150"
    cc150_plus = "cc150_plus"


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)
