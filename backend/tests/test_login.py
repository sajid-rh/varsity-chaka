import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.rate_limit import login_limiter
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models import User
from app.models.types import utcnow
from app.tenancy.context import TenantContext, get_tenant_context, require_role

PASSWORD = "Sample1234"


@pytest.fixture(autouse=True)
def clear_limiter():
    login_limiter.clear()
    yield
    login_limiter.clear()


def make_user(db, university, email, role="student", verified=True, active=True):
    user = User(
        university_id=university.id if university else None,
        email=email,
        password_hash=hash_password(PASSWORD),
        full_name="Test User",
        role=role,
        email_verified_at=utcnow() if verified else None,
        is_active=active,
    )
    db.add(user)
    db.commit()
    return user


def login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_login_success_sets_an_httponly_cookie(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    response = login(client, "s@diu.edu.bd")

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["role"] == "student"
    assert "password" not in str(body)
    cookie = response.headers["set-cookie"].lower()
    assert "access_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_wrong_password_and_unknown_email_give_the_same_message(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    wrong_password = login(client, "s@diu.edu.bd", "Wrong12345")
    unknown_email = login(client, "nobody@diu.edu.bd")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_unverified_user_cannot_log_in(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd", verified=False)
    response = login(client, "s@diu.edu.bd")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "email_not_verified"


def test_disabled_user_cannot_log_in(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd", active=False)
    assert login(client, "s@diu.edu.bd").json()["error"]["code"] == "account_disabled"


def test_account_state_is_not_revealed_for_a_wrong_password(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd", verified=False)
    response = login(client, "s@diu.edu.bd", "Wrong12345")
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_too_many_failures_lock_the_login_even_for_the_right_password(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    for _ in range(5):
        assert login(client, "s@diu.edu.bd", "Wrong12345").status_code == 401
    blocked = login(client, "s@diu.edu.bd")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "too_many_attempts"


def test_successful_login_resets_the_email_counter(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    for _ in range(3):
        login(client, "s@diu.edu.bd", "Wrong12345")
    assert login(client, "s@diu.edu.bd").status_code == 200


def test_me_requires_login(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_returns_the_user_and_their_university(client, db_session, universities):
    make_user(db_session, universities["AIUB"], "s@aiub.edu")
    login(client, "s@aiub.edu")
    data = client.get("/api/v1/auth/me").json()["data"]
    assert data["email"] == "s@aiub.edu"
    assert data["university"]["short_code"] == "AIUB"


def test_logout_clears_the_session(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    login(client, "s@diu.edu.bd")
    assert client.get("/api/v1/auth/me").status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_a_forged_token_is_rejected(client, universities):
    client.cookies.set("access_token", "not.a.real.token")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_token_claiming_a_different_tenant_is_rejected(client, db_session, universities):
    user = make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    # A validly signed token, but it names the other university
    forged = create_access_token(user_id=user.id, university_id=universities["AIUB"].id, role="student")
    client.cookies.set("access_token", forged)
    assert client.get("/api/v1/auth/me").status_code == 401


def test_token_claiming_a_higher_role_does_not_grant_it(client, db_session, universities):
    user = make_user(db_session, universities["DIU"], "s@diu.edu.bd", role="student")
    token = create_access_token(user_id=user.id, university_id=user.university_id, role="super_admin")
    client.cookies.set("access_token", token)
    # The role in the token is ignored. The database says "student".
    assert client.get("/api/v1/auth/me").json()["data"]["role"] == "student"


def test_user_disabled_after_login_loses_access(client, db_session, universities):
    user = make_user(db_session, universities["DIU"], "s@diu.edu.bd")
    login(client, "s@diu.edu.bd")
    user.is_active = False
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


# ---- role checks: a throwaway admin-only route, registered for tests only ----
admin_test_router = APIRouter()


@admin_test_router.get("/api/v1/_test/admin-only")
def admin_only(ctx: TenantContext = Depends(require_role("university_admin"))):
    return {"university_id": ctx.university_id}


app.include_router(admin_test_router)


def test_student_cannot_use_an_admin_route(client, db_session, universities):
    make_user(db_session, universities["DIU"], "s@diu.edu.bd", role="student")
    login(client, "s@diu.edu.bd")
    response = client.get("/api/v1/_test/admin-only")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_admin_can_use_an_admin_route_and_gets_their_own_tenant(client, db_session, universities):
    make_user(db_session, universities["AIUB"], "a@aiub.edu", role="university_admin")
    login(client, "a@aiub.edu")
    response = client.get("/api/v1/_test/admin-only")
    assert response.status_code == 200
    assert response.json()["university_id"] == universities["AIUB"].id


def test_anonymous_request_to_an_admin_route_is_401(client):
    assert client.get("/api/v1/_test/admin-only").status_code == 401
