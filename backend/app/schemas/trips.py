"""Pydantic schemas for trip management and state machine."""
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class TripCreate(BaseModel):
    offer_id: int
    request_id: int | None = None


class TripCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class TripDisputeRequest(BaseModel):
    reason: str = Field(..., min_length=5, max_length=500)


class TripParticipantView(BaseModel):
    user_id: int
    full_name: str
    phone: str | None = None  # None until confirmed state


class TripOut(BaseModel):
    id: int
    university_id: int
    status: str
    offer_id: int
    request_id: int | None

    # Rider & Passenger info
    rider: TripParticipantView
    passenger: TripParticipantView
    motorcycle_model: str
    plate_number: str

    origin_label: str
    dest_label: str
    departure_time: datetime

    # Match & Fare details
    match_score: Decimal | None
    match_explanation: str | None
    suggested_fare_min: Decimal | None
    suggested_fare_max: Decimal | None

    # Timestamps
    helmet_confirmed_at: datetime | None
    accepted_at: datetime | None
    confirmed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancelled_by: int | None
    cancellation_reason: str | None

    # Dual completion & disputes
    rider_confirmed_complete_at: datetime | None
    passenger_confirmed_complete_at: datetime | None
    disputed: bool
    dispute_reason: str | None

    created_at: datetime
    updated_at: datetime
