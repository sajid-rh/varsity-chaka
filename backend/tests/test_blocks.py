"""Tests for safety blocking and unblocking between students."""
import pytest

from app.core.security import hash_password
from app.models import User
from app.models.types import utcnow

PASSWORD = "Sample1234"


@pytest.fixture()
def block_users(db_session, universities):
    diu = universities["DIU"]
    aiub = universities["AIUB"]

    def make(email, uni):
        u = User(
            university_id=uni.id,
            email=email,
            password_hash=hash_password(PASSWORD),
            full_name=email.split("@")[0].title(),
            student_id_no=f"ID-{email.split('@')[0]}",
            role="student",
            email_verified_at=utcnow(),
        )
        db_session.add(u)
        db_session.commit()
        return u

    return {
        "student1": make("s1@diu.edu.bd", diu),
        "student2": make("s2@diu.edu.bd", diu),
        "student_aiub": make("s_aiub@aiub.edu", aiub),
    }


def login_as(client, user):
    res = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert res.status_code == 200


def test_student_can_block_and_list_and_unblock(client, block_users):
    s1 = block_users["student1"]
    s2 = block_users["student2"]

    login_as(client, s1)

    # 1. Block student 2
    res = client.post("/api/v1/blocks", json={"blocked_user_id": s2.id})
    assert res.status_code == 201
    assert res.json()["data"]["blocked_id"] == s2.id

    # 2. List blocks
    list_res = client.get("/api/v1/blocks")
    assert list_res.status_code == 200
    assert list_res.json()["data"]["count"] == 1
    assert list_res.json()["data"]["items"][0]["blocked_id"] == s2.id

    # 3. Unblock student 2
    del_res = client.delete(f"/api/v1/blocks/{s2.id}")
    assert del_res.status_code == 200
    assert del_res.json()["data"]["unblocked"] is True

    # 4. List again is empty
    list_res2 = client.get("/api/v1/blocks")
    assert list_res2.json()["data"]["count"] == 0


def test_cannot_block_self(client, block_users):
    s1 = block_users["student1"]
    login_as(client, s1)

    res = client.post("/api/v1/blocks", json={"blocked_user_id": s1.id})
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "cannot_block_self"


def test_cannot_block_user_from_different_tenant(client, block_users):
    s1 = block_users["student1"]
    s_aiub = block_users["student_aiub"]
    login_as(client, s1)

    # Cross-tenant target returns 404
    res = client.post("/api/v1/blocks", json={"blocked_user_id": s_aiub.id})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "user_not_found"
