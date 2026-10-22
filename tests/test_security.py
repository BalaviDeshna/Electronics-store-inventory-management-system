import pytest

from app.business.security import hash_password, verify_password


def test_password_is_not_stored_as_plain_text():
    password = "ExamplePassword123"
    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("$2")


def test_correct_password_is_verified():
    password = "ExamplePassword123"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_incorrect_password_is_rejected():
    password_hash = hash_password("ExamplePassword123")

    assert verify_password("WrongPassword123", password_hash) is False


def test_same_password_produces_different_hashes():
    password = "ExamplePassword123"

    hash_one = hash_password(password)
    hash_two = hash_password(password)

    assert hash_one != hash_two
    assert verify_password(password, hash_one) is True
    assert verify_password(password, hash_two) is True


def test_invalid_hash_is_rejected():
    assert verify_password("ExamplePassword123", "not-a-valid-hash") is False


def test_password_over_bcrypt_limit_is_rejected():
    password = "a" * 73

    with pytest.raises(ValueError):
        hash_password(password)

    assert verify_password(password, "some-hash") is False