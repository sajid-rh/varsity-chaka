import pytest
from sqlalchemy import select

from app.core.rate_limit import login_limiter
from app.core.security import hash_password
from app.models import User
from app.models.types import utcnow
from app.services import auth_service

PASSWORD = "Sample1234"


@pytest.fixture(autouse=True)
def clear_limiter():
    login_limiter.clear()
    yield
    login_limiter.clear()


@pytest.fixture()
def sent_tokens(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        auth_service,
        "send_verification_link",
        lambda email, raw_token: captured.update({email: raw_token}),
    )
    return captured


def add_user(db, university, email, name="Test User", verified=True):
    user = User(
        university_id=university.id,
        email=email,
        password_hash=hash_password(PASSWORD),
        full_name=name,
        role="student",
        email_verified_at=utcnow() if verified else None,
    )
    db.add(user)
    db.commit()
    return user


def post_login(client, email, password=PASSWORD):
    return client.post(
        "/login", data={"email": email, "password": password}, follow_redirects=False
    )


REGISTER_FORM = {
    "email": "page@diu.edu.bd",
    "full_name": "Page Student",
    "phone": "01712345678",
    "student_id_no": "221-15-0009",
    "password": PASSWORD,
    "confirm_password": PASSWORD,
}


def test_login_and_register_pages_render(client):
    assert "Log in" in client.get("/login").text
    assert "Create your account" in client.get("/register").text


def test_visitor_is_redirected_from_home_and_dashboard_to_login(client):
    for path in ("/", "/dashboard"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_login_redirects_to_the_dashboard_and_shows_the_user(client, db_session, universities):
    add_user(db_session, universities["DIU"], "s@diu.edu.bd", name="Rahim Uddin")
    response = post_login(client, "s@diu.edu.bd")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Rahim Uddin" in dashboard.text
    assert "Daffodil International University" in dashboard.text


def test_wrong_password_shows_the_generic_message_and_keeps_the_email(client, db_session, universities):
    add_user(db_session, universities["DIU"], "s@diu.edu.bd")
    response = post_login(client, "s@diu.edu.bd", "Wrong12345")
    assert response.status_code == 401
    assert "Incorrect email or password" in response.text
    assert 'value="s@diu.edu.bd"' in response.text
    assert "Wrong12345" not in response.text


def test_logout_returns_to_login_and_ends_the_session(client, db_session, universities):
    add_user(db_session, universities["DIU"], "s@diu.edu.bd")
    post_login(client, "s@diu.edu.bd")
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_logged_in_user_is_sent_away_from_the_login_page(client, db_session, universities):
    add_user(db_session, universities["DIU"], "s@diu.edu.bd")
    post_login(client, "s@diu.edu.bd")
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_registration_form_creates_an_unverified_user(client, universities, db_session, sent_tokens):
    response = client.post("/register", data=REGISTER_FORM)
    assert response.status_code == 201
    assert "Account created" in response.text
    user = db_session.scalar(select(User).where(User.email == "page@diu.edu.bd"))
    assert user is not None and user.email_verified_at is None
    assert "page@diu.edu.bd" in sent_tokens


def test_registration_errors_are_shown_per_field_and_the_password_is_not_echoed(client, universities):
    bad = {**REGISTER_FORM, "password": "weakpass1", "confirm_password": "weakpass1"}
    response = client.post("/register", data=bad)
    assert response.status_code == 422
    assert "Must contain an uppercase letter" in response.text
    assert 'value="page@diu.edu.bd"' in response.text  # other fields are kept
    assert "weakpass1" not in response.text  # the password is never sent back


def test_mismatched_confirmation_is_reported(client, universities):
    bad = {**REGISTER_FORM, "confirm_password": "Different1234"}
    response = client.post("/register", data=bad)
    assert response.status_code == 422
    assert "Passwords do not match" in response.text


def test_unknown_domain_message_appears_on_the_page(client, universities):
    response = client.post("/register", data={**REGISTER_FORM, "email": "me@gmail.com"})
    assert response.status_code == 400
    assert "Use your university email" in response.text


def test_verification_link_page_works_once(client, universities, sent_tokens):
    client.post("/register", data=REGISTER_FORM)
    token = sent_tokens["page@diu.edu.bd"]

    first = client.get("/verify-email", params={"token": token})
    assert first.status_code == 200
    assert "is verified" in first.text

    second = client.get("/verify-email", params={"token": token})
    assert second.status_code == 400
    assert "invalid or has expired" in second.text


def test_unverified_user_sees_a_clear_message_on_login(client, db_session, universities):
    add_user(db_session, universities["DIU"], "s@diu.edu.bd", verified=False)
    response = post_login(client, "s@diu.edu.bd")
    assert response.status_code == 403
    assert "Verify your email" in response.text


def test_user_names_are_html_escaped(client, db_session, universities):
    add_user(db_session, universities["DIU"], "s@diu.edu.bd", name="<script>alert(1)</script>")
    post_login(client, "s@diu.edu.bd")
    page = client.get("/dashboard").text
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_static_stylesheet_is_served(client):
    response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert "--primary" in response.text
