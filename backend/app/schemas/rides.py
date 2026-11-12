"""Pydantic schemas for ride offers and requests."""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CoordinateModel(BaseModel):
    lat: Decimal = Field(..., ge=-90, le=90)
    lng: Decimal = Field(..., ge=-180, le=180)


class RideOfferCreate(BaseModel):
    origin_lat: Decimal = Field(..., ge=-90, le=90)
    origin_lng: Decimal = Field(..., ge=-180, le=180)
    origin_label: str = Field(..., min_length=2, max_length=150)

    dest_lat: Decimal = Field(..., ge=-90, le=90)
    dest_lng: Decimal = Field(..., ge=-180, le=180)
    dest_label: str = Field(..., min_length=2, max_length=150)

    direction: Literal["to_campus", "from_campus"]
    departure_time: datetime
    route_distance_m: int | None = Field(default=None, ge=0)
    route_duration_s: int | None = Field(default=None, ge=0)

    @field_validator("origin_label", "dest_label")
    @classmethod
    def clean_labels(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if len(cleaned) < 2:
            raise ValueError("Label too short")
        return cleaned


class RideOfferUpdate(BaseModel):
    departure_time: datetime | None = None
    origin_label: str | None = Field(default=None, min_length=2, max_length=150)
    dest_label: str | None = Field(default=None, min_length=2, max_length=150)


class RideOfferOut(BaseModel):
    id: int
    university_id: int
    rider_id: int
    rider_name: str
    motorcycle_model: str
    plate_number: str
    engine_class: str
    origin_lat: Decimal
    origin_lng: Decimal
    origin_label: str
    dest_lat: Decimal
    dest_lng: Decimal
    dest_label: str
    direction: str
    departure_time: datetime
    route_distance_m: int | None
    route_duration_s: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class RideRequestCreate(BaseModel):
    pickup_lat: Decimal = Field(..., ge=-90, le=90)
    pickup_lng: Decimal = Field(..., ge=-180, le=180)
    pickup_label: str = Field(..., min_length=2, max_length=150)

    dest_lat: Decimal = Field(..., ge=-90, le=90)
    dest_lng: Decimal = Field(..., ge=-180, le=180)
    dest_label: str = Field(..., min_length=2, max_length=150)

    preferred_time: datetime

    @field_validator("pickup_label", "dest_label")
    @classmethod
    def clean_labels(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if len(cleaned) < 2:
            raise ValueError("Label too short")
        return cleaned


class RideRequestOut(BaseModel):
    id: int
    university_id: int
    passenger_id: int
    passenger_name: str
    pickup_lat: Decimal
    pickup_lng: Decimal
    pickup_label: str
    dest_lat: Decimal
    dest_lng: Decimal
    dest_label: str
    preferred_time: datetime
    status: str
    created_at: datetime
    updated_at: datetime
