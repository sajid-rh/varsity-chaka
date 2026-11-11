import jwt

from app.core.security import (
    ALGORITHM,
    check_password_strength,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_the_plain_password():
    hashed = hash_password("Sample1234")
    assert hashed != "Sample1234"
    assert hashed.startswith("$argon2")


def test_same_password_gives_different_hashes_because_of_salt():
    assert hash_password("Sample1234") != hash_password("Sample1234")


def test_verify_password_accepts_correct_and_rejects_wrong():
    hashed = hash_password("Sample1234")
    assert verify_password("Sample1234", hashed) is True
    assert verify_password("Wrong1234", hashed) is False


def test_verify_password_returns_false_for_garbage_hash():
    assert verify_password("Sample1234", "not-a-real-hash") is False


def test_strong_password_has_no_problems():
    assert check_password_strength("Sample1234") == []


def test_weak_passwords_report_problems():
    assert len(check_password_strength("short")) >= 3
    assert "Must contain a digit" in check_password_strength("NoDigitsHere")
    assert "Must contain an uppercase letter" in check_password_strength("lowercase123")


def test_token_round_trip_keeps_user_tenant_and_role():
    token = create_access_token(user_id=7, university_id=2, role="student")
    payload = decode_access_token(token)
    assert payload["sub"] == "7"
    assert payload["uid"] == 2
    assert payload["role"] == "student"


def test_super_admin_token_has_no_tenant():
    token = create_access_token(user_id=1, university_id=None, role="super_admin")
    assert decode_access_token(token)["uid"] is None


def test_expired_token_is_rejected():
    token = create_access_token(
        user_id=7, university_id=2, role="student", expires_minutes=-1
    )
    assert decode_access_token(token) is None


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode(
        {"sub": "7", "uid": 2, "role": "super_admin"},
        "some-other-secret-key-for-the-test!!",
        algorithm=ALGORITHM,
    )
    assert decode_access_token(forged) is None


def test_random_text_is_not_a_valid_token():
    assert decode_access_token("not.a.token") is None
