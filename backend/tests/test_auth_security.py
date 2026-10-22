from app.auth.security import hash_password, verify_password


def test_password_is_stored_as_a_non_reversible_hash() -> None:
    password = "StrongPass123!"

    password_hash = hash_password(password)

    assert password_hash != password
    assert password_hash.startswith("scrypt$")
    assert verify_password(password, password_hash) is True
    assert verify_password("WrongPass123!", password_hash) is False


def test_same_password_gets_different_salts() -> None:
    password = "StrongPass123!"

    assert hash_password(password) != hash_password(password)
