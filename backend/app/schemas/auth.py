"""Request models for the authentication endpoints. Pydantic validates every field."""
import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.security import check_password_strength

PHONE_PATTERN = re.compile(r"^\+?\d{10,15}$")


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    # max_length stops absurdly long inputs from making the hasher do needless work
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)
    phone: str | None = None
    student_id_no: str | None = Field(default=None, max_length=50)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Name is too short")
        return value

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        cleaned = re.sub(r"[\s-]", "", value)
        if not PHONE_PATTERN.match(cleaned):
            raise ValueError("Enter a valid phone number (10 to 15 digits)")
        return cleaned

    @field_validator("student_id_no")
    @classmethod
    def clean_student_id(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        return value.strip()

    @field_validator("password")
    @classmethod
    def strong_password(cls, value: str) -> str:
        problems = check_password_strength(value)
        if problems:
            raise ValueError("; ".join(problems))
        return value

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    # No strength rules here: login only compares against the stored hash
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.strip().lower()
