from datetime import timedelta

import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.config import get_settings
from app.core.rate_limit import login_limiter
from app.core.security import hash_password
from app.main import app
from app.models import AuditLog, ReliabilityStats, RiderProfile, User
from app.models.types import utcnow
from app.services import rider_service
from app.tenancy.rider import require_approved_rider

PASSWORD = "Sample1234"
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Each test gets its own upload folder and a fresh login limiter."""
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")
    login_limiter.clear()
    yield
    login_limiter.clear()


@pytest.fixture()
def people(db_session, universities):
    """Two DIU students, one AIUB student, an admin for each university and a super admin."""

    def make(email, role, university):
        user = User(
            university_id=university.id if university else None,
            email=email,
            password_hash=hash_password(PASSWORD),
            full_name=email.split("@")[0].title(),
            student_id_no=f"ID-{email.split('@')[0]}",
            role=role,
            email_verified_at=utcnow(),
        )
        db_session.add(user)
        db_session.commit()
        return user

    diu, aiub = universities["DIU"], universities["AIUB"]
    return {
        "diu_student": make("ana@diu.edu.bd", "student", diu),
        "diu_student2": make("ben@diu.edu.bd", "student", diu),
        "aiub_student": make("cam@aiub.edu", "student", aiub),
        "diu_admin": make("admin@diu.edu.bd", "university_admin", diu),
        "aiub_admin": make("admin@aiub.edu", "university_admin", aiub),
        "super": make("root@example.com", "super_admin", None),
    }


def login_as(client, user):
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def apply(client, *, plate="Dhaka Metro-Ha 12-3456", doc=("card.jpg", JPEG, "image/jpeg"), **overrides):
    data = {
        "motorcycle_model": "Yamaha FZS",
        "engine_class": "cc125_150",
        "plate_number": plate,
        "license_declared": "true",
        "helmet_declared": "true",
    }
    data.update(overrides)
    files = {"registration_doc": doc} if doc else None
    return client.post("/api/v1/riders/apply", data=data, files=files)


def submitted(client, db_session, people, who="diu_student", plate="Dhaka Metro-Ha 12-3456"):
    """Log in as a student, apply, and return the profile row."""
    login_as(client, people[who])
    assert apply(client, plate=plate).status_code == 201
    return db_session.scalar(select(RiderProfile).where(RiderProfile.user_id == people[who].id))


def admin_url(profile_id, suffix=""):
    return f"/api/v1/admin/rider-applications/{profile_id}{suffix}"


# ---------------- plate and helper rules ----------------

def test_plate_is_normalised_to_upper_case_with_single_spaces():
    assert rider_service.normalize_plate("  dhaka   metro-ha 12-3456 ") == "DHAKA METRO-HA 12-3456"


@pytest.mark.parametrize("bad", ["", "ab", "!!!!", "<script>", "x" * 31])
def test_invalid_plates_are_rejected(bad):
    with pytest.raises(Exception) as exc:
        rider_service.normalize_plate(bad)
    assert exc.value.code == "invalid_plate"


def test_adding_years_handles_leap_day():
    from datetime import datetime
    assert rider_service.add_years(datetime(2028, 2, 29, 10), 2) == datetime(2030, 2, 28, 10)
    assert rider_service.add_years(datetime(2026, 11, 12), 2) == datetime(2028, 11, 12)


# ---------------- student: applying ----------------

def test_student_can_apply_and_the_application_is_pending(client, db_session, people):
    login_as(client, people["diu_student"])
    response = apply(client)
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["plate_number"] == "DHAKA METRO-HA 12-3456"
    assert "registration_doc_path" not in str(response.json())  # the file path is never exposed


def test_the_photo_is_stored_privately_under_a_random_name(client, db_session, people):
    profile = submitted(client, db_session, people)
    stored = get_settings().upload_dir / profile.registration_doc_path
    assert stored.is_file()
    assert stored.read_bytes() == JPEG
    assert "card" not in stored.name  # the uploaded file name is not reused


def test_png_is_accepted(client, people):
    login_as(client, people["diu_student"])
    assert apply(client, doc=("card.png", PNG, "image/png")).status_code == 201


def test_apply_requires_login(client):
    assert apply(client).status_code == 401


def test_admin_cannot_apply(client, people):
    login_as(client, people["diu_admin"])
    assert apply(client).status_code == 403


def test_both_declarations_are_required(client, people):
    login_as(client, people["diu_student"])
    for field in ("license_declared", "helmet_declared"):
        response = apply(client, **{field: "false"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "declarations_required"


def test_missing_photo_is_rejected(client, people):
    login_as(client, people["diu_student"])
    assert apply(client, doc=None).status_code == 422


def test_a_text_file_renamed_to_jpg_is_rejected(client, people):
    login_as(client, people["diu_student"])
    response = apply(client, doc=("card.jpg", b"just some text, not an image", "image/jpeg"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_document"


def test_oversized_photo_is_rejected(client, people):
    login_as(client, people["diu_student"])
    big = JPEG + b"\x00" * rider_service.MAX_DOCUMENT_BYTES
    response = apply(client, doc=("card.jpg", big, "image/jpeg"))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "document_too_large"


def test_unknown_engine_class_is_rejected(client, people):
    login_as(client, people["diu_student"])
    assert apply(client, engine_class="cc999").status_code == 422


def test_invalid_plate_is_rejected_with_a_clear_code(client, people):
    login_as(client, people["diu_student"])
    response = apply(client, plate="<script>")
    assert response.status_code == 422


def test_cannot_apply_twice_while_pending(client, db_session, people):
    submitted(client, db_session, people)
    response = apply(client, plate="Dhaka Metro-Ha 99-9999")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "application_exists"


def test_plate_is_unique_within_a_university_but_not_across(client, db_session, people):
    submitted(client, db_session, people, "diu_student", "Dhaka Metro-Ha 12-3456")
    login_as(client, people["diu_student2"])
    same_tenant = apply(client, plate="dhaka metro-ha 12-3456")  # same plate, different case
    assert same_tenant.status_code == 409
    assert same_tenant.json()["error"]["code"] == "plate_taken"
    login_as(client, people["aiub_student"])
    assert apply(client, plate="Dhaka Metro-Ha 12-3456").status_code == 201


def test_my_application_before_and_after_applying(client, people):
    login_as(client, people["diu_student"])
    assert client.get("/api/v1/riders/me").json()["data"]["status"] == "not_applied"
    apply(client)
    assert client.get("/api/v1/riders/me").json()["data"]["status"] == "pending"


# ---------------- admin: access and tenant isolation ----------------

def test_student_cannot_use_admin_endpoints(client, db_session, people):
    profile = submitted(client, db_session, people)
    assert client.get("/api/v1/admin/rider-applications").status_code == 403
    assert client.post(admin_url(profile.id, "/approve")).status_code == 403


def test_super_admin_cannot_browse_student_applications(client, people):
    login_as(client, people["super"])
    assert client.get("/api/v1/admin/rider-applications").status_code == 403


def test_admin_sees_only_their_own_universitys_applications(client, db_session, people):
    submitted(client, db_session, people, "diu_student", "DHAKA METRO-HA 11-1111")
    submitted(client, db_session, people, "aiub_student", "DHAKA METRO-HA 22-2222")

    login_as(client, people["diu_admin"])
    items = client.get("/api/v1/admin/rider-applications").json()["data"]["items"]
    assert [i["plate_number"] for i in items] == ["DHAKA METRO-HA 11-1111"]

    login_as(client, people["aiub_admin"])
    items = client.get("/api/v1/admin/rider-applications").json()["data"]["items"]
    assert [i["plate_number"] for i in items] == ["DHAKA METRO-HA 22-2222"]


def test_admin_of_another_university_gets_404_for_everything(client, db_session, people):
    profile = submitted(client, db_session, people, "diu_student")
    login_as(client, people["aiub_admin"])
    for method, suffix, body in [
        ("get", "", None),
        ("get", "/document", None),
        ("post", "/approve", None),
        ("post", "/reject", {"reason": "not allowed"}),
        ("post", "/suspend", {"reason": "not allowed"}),
    ]:
        response = getattr(client, method)(admin_url(profile.id, suffix), **({"json": body} if body else {}))
        assert response.status_code == 404, (method, suffix)
    db_session.refresh(profile)
    assert profile.status == "pending"  # nothing changed


def test_admin_view_shows_applicant_details_but_not_the_file_path(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    body = client.get(admin_url(profile.id)).json()["data"]
    assert body["applicant"]["email"] == "ana@diu.edu.bd"
    assert body["document_url"].endswith("/document")
    assert "rider_docs" not in str(body)


def test_status_filter_and_bad_filter(client, db_session, people):
    submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    assert client.get("/api/v1/admin/rider-applications?status=pending").json()["data"]["count"] == 1
    assert client.get("/api/v1/admin/rider-applications?status=approved").json()["data"]["count"] == 0
    assert client.get("/api/v1/admin/rider-applications?status=bogus").status_code == 422


# ---------------- admin: documents ----------------

def test_admin_can_view_the_photo_with_private_headers_and_it_is_audited(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    response = client.get(admin_url(profile.id, "/document"))
    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["x-content-type-options"] == "nosniff"
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "rider_document_viewed"))
    assert log.actor_id == people["diu_admin"].id


def test_a_stored_path_pointing_outside_the_upload_folder_is_refused(client, db_session, people, tmp_path):
    profile = submitted(client, db_session, people)
    (tmp_path / "outside.txt").write_text("secret")
    profile.registration_doc_path = "../outside.txt"
    db_session.commit()
    login_as(client, people["diu_admin"])
    response = client.get(admin_url(profile.id, "/document"))
    assert response.status_code == 404
    assert "secret" not in response.text


# ---------------- admin: decisions ----------------

def test_approve_sets_a_two_year_expiry_creates_stats_and_writes_an_audit_log(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    response = client.post(admin_url(profile.id, "/approve"))

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "approved"
    db_session.refresh(profile)
    assert 729 <= (profile.expires_at - profile.approved_at).days <= 731
    assert profile.reviewed_by == people["diu_admin"].id
    assert db_session.get(ReliabilityStats, profile.id) is not None
    log = db_session.scalar(select(AuditLog).where(AuditLog.action == "rider_approved"))
    assert log.actor_id == people["diu_admin"].id
    assert log.university_id == people["diu_admin"].university_id
    assert log.target_id == profile.id


def test_cannot_approve_twice(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    client.post(admin_url(profile.id, "/approve"))
    again = client.post(admin_url(profile.id, "/approve"))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_state"


def test_reject_needs_a_reason(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    assert client.post(admin_url(profile.id, "/reject"), json={}).status_code == 422
    assert client.post(admin_url(profile.id, "/reject"), json={"reason": "no"}).status_code == 422
    db_session.refresh(profile)
    assert profile.status == "pending"


def test_rejected_student_sees_the_reason_and_can_apply_again(client, db_session, people):
    profile = submitted(client, db_session, people)
    old_file = get_settings().upload_dir / profile.registration_doc_path
    login_as(client, people["diu_admin"])
    assert client.post(admin_url(profile.id, "/reject"), json={"reason": "Photo is not readable"}).status_code == 200

    login_as(client, people["diu_student"])
    mine = client.get("/api/v1/riders/me").json()["data"]
    assert mine["status"] == "rejected"
    assert mine["reason"] == "Photo is not readable"

    assert apply(client, doc=("card.png", PNG, "image/png")).status_code == 201
    db_session.refresh(profile)
    assert profile.status == "pending"
    assert profile.rejection_reason is None
    assert not old_file.exists()  # the replaced photo was deleted


def test_suspend_only_from_approved_and_suspended_riders_cannot_reapply(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    assert client.post(admin_url(profile.id, "/suspend"), json={"reason": "Reported twice"}).status_code == 409
    client.post(admin_url(profile.id, "/approve"))
    assert client.post(admin_url(profile.id, "/suspend"), json={"reason": "Reported twice"}).status_code == 200

    login_as(client, people["diu_student"])
    assert client.get("/api/v1/riders/me").json()["data"]["status"] == "suspended"
    blocked = apply(client, plate="Dhaka Metro-Ha 77-7777")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "rider_suspended"


def test_admin_can_reinstate_a_suspended_rider(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    client.post(admin_url(profile.id, "/approve"))
    client.post(admin_url(profile.id, "/suspend"), json={"reason": "Reported twice"})
    assert client.post(admin_url(profile.id, "/approve")).json()["data"]["status"] == "approved"


def test_every_decision_is_audited(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    client.post(admin_url(profile.id, "/approve"))
    client.post(admin_url(profile.id, "/suspend"), json={"reason": "Reported twice"})
    actions = [row.action for row in db_session.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["rider_approved", "rider_suspended"]


# ---------------- expiry and the approved-rider dependency ----------------

probe = APIRouter()


@probe.get("/api/v1/_test/rider-only")
def rider_only(profile: RiderProfile = Depends(require_approved_rider)):
    return {"profile_id": profile.id}


app.include_router(probe)


def test_unapproved_student_cannot_use_rider_routes(client, db_session, people):
    submitted(client, db_session, people)
    response = client.get("/api/v1/_test/rider-only")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "rider_not_approved"


def test_approved_rider_can_use_rider_routes_and_a_non_applicant_cannot(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    client.post(admin_url(profile.id, "/approve"))

    login_as(client, people["diu_student"])
    assert client.get("/api/v1/_test/rider-only").json()["profile_id"] == profile.id

    login_as(client, people["diu_student2"])
    assert client.get("/api/v1/_test/rider-only").status_code == 403


def test_an_approval_older_than_two_years_expires_and_loses_rider_access(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    client.post(admin_url(profile.id, "/approve"))
    profile.expires_at = utcnow() - timedelta(days=1)  # time passes
    db_session.commit()

    login_as(client, people["diu_student"])
    assert client.get("/api/v1/riders/me").json()["data"]["status"] == "expired"
    assert client.get("/api/v1/_test/rider-only").status_code == 403

    login_as(client, people["diu_admin"])
    expired = client.get("/api/v1/admin/rider-applications?status=expired").json()["data"]
    assert expired["count"] == 1


def test_expired_rider_can_reapply_and_is_reviewed_again(client, db_session, people):
    profile = submitted(client, db_session, people)
    login_as(client, people["diu_admin"])
    client.post(admin_url(profile.id, "/approve"))
    profile.expires_at = utcnow() - timedelta(days=1)
    db_session.commit()

    login_as(client, people["diu_student"])
    assert apply(client).status_code == 201  # same plate is fine: it is their own row
    assert client.get("/api/v1/riders/me").json()["data"]["status"] == "pending"
    assert client.get("/api/v1/_test/rider-only").status_code == 403
