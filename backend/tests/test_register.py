from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import EmailVerificationToken, User
from app.models.types import utcnow
from app.services import auth_service

VALID = {
    "email": "student@diu.edu.bd",
    "full_name": "Test Student",
    "password": "Sample1234",
    "confirm_password": "Sample1234",
    "phone": "01712345678",
    "student_id_no": "221-15-0001",
}


@pytest.fixture()
def sent_tokens(monkeypatch):
    """Captures the verification token that would have been emailed."""
    captured = {}
    monkeypatch.setattr(
        auth_service,
        "send_verification_link",
        lambda email, raw_token: captured.update({email: raw_token}),
    )
    return captured


def register(client, **overrides):
    return client.post("/api/v1/auth/register", json={**VALID, **overrides})


def test_successful_registration(client, universities, db_session, sent_tokens):
    response = register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == "student@diu.edu.bd"
    assert "password" not in str(body).lower().replace("passwords", "")
    user = db_session.scalar(select(User).where(User.email == "student@diu.edu.bd"))
    assert user.role == "student"
    assert user.email_verified_at is None
    assert "student@diu.edu.bd" in sent_tokens


def test_password_is_stored_only_as_an_argon2_hash(client, universities, db_session):
    register(client)
    user = db_session.scalar(select(User))
    assert user.password_hash != "Sample1234"
    assert user.password_hash.startswith("$argon2")


def test_tenant_is_detected_from_the_email_domain(client, universities, db_session):
    register(client, email="x@diu.edu.bd")
    register(client, email="y@aiub.edu", student_id_no="A-1")
    diu_user = db_session.scalar(select(User).where(User.email == "x@diu.edu.bd"))
    aiub_user = db_session.scalar(select(User).where(User.email == "y@aiub.edu"))
    assert diu_user.university_id == universities["DIU"].id
    assert aiub_user.university_id == universities["AIUB"].id


def test_unknown_email_domain_is_rejected(client, universities):
    response = register(client, email="someone@gmail.com")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_email_domain"


def test_inactive_university_is_rejected(client, universities, db_session):
    universities["DIU"].is_active = False
    db_session.commit()
    response = register(client)
    assert response.json()["error"]["code"] == "unsupported_email_domain"


def test_duplicate_email_is_rejected_even_with_different_case(client, universities):
    assert register(client).status_code == 201
    response = register(client, email="STUDENT@diu.edu.bd", student_id_no="other")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_student_id_unique_within_a_university_but_not_across(client, universities):
    assert register(client, email="a@diu.edu.bd").status_code == 201
    same_tenant = register(client, email="b@diu.edu.bd")
    assert same_tenant.status_code == 409
    assert same_tenant.json()["error"]["code"] == "student_id_taken"
    other_tenant = register(client, email="c@aiub.edu")
    assert other_tenant.status_code == 201


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"password": "weak", "confirm_password": "weak"}, "password"),
        ({"confirm_password": "Different1234"}, "confirm_password"),
        ({"email": "not-an-email"}, "email"),
        ({"full_name": "A"}, "full_name"),
        ({"phone": "abc"}, "phone"),
    ],
)
def test_invalid_input_returns_422_with_field_details(client, universities, overrides, field):
    response = register(client, **overrides)
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "validation_error"
    assert any(field in d["field"] or d["field"] == "" for d in body["error"]["details"])


def test_validation_error_never_echoes_the_password(client, universities):
    response = register(client, password="Qq1xyz", confirm_password="Qq1xyz")
    assert response.status_code == 422
    assert "Qq1xyz" not in response.text


def test_verify_email_marks_the_user_verified(client, universities, db_session, sent_tokens):
    register(client)
    token = sent_tokens["student@diu.edu.bd"]

    response = client.get("/api/v1/auth/verify-email", params={"token": token})

    assert response.status_code == 200
    user = db_session.scalar(select(User).where(User.email == "student@diu.edu.bd"))
    assert user.email_verified_at is not None


def test_verification_link_works_only_once(client, universities, sent_tokens):
    register(client)
    token = sent_tokens["student@diu.edu.bd"]
    assert client.get("/api/v1/auth/verify-email", params={"token": token}).status_code == 200
    second = client.get("/api/v1/auth/verify-email", params={"token": token})
    assert second.status_code == 400
    assert second.json()["error"]["code"] == "invalid_token"


def test_expired_verification_link_is_rejected(client, universities, db_session, sent_tokens):
    register(client)
    token_row = db_session.scalar(select(EmailVerificationToken))
    token_row.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()
    response = client.get(
        "/api/v1/auth/verify-email", params={"token": sent_tokens["student@diu.edu.bd"]}
    )
    assert response.status_code == 400


def test_made_up_token_is_rejected(client, universities):
    response = client.get("/api/v1/auth/verify-email", params={"token": "x" * 40})
    assert response.status_code == 400


def test_raw_token_is_not_stored_in_the_database(client, universities, db_session, sent_tokens):
    register(client)
    token_row = db_session.scalar(select(EmailVerificationToken))
    assert token_row.token_hash != sent_tokens["student@diu.edu.bd"]
    assert len(token_row.token_hash) == 64
