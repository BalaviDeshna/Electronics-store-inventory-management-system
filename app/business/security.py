import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt and return the hash as a string."""
    if not isinstance(password, str):
        raise TypeError("Password must be a string.")

    password_bytes = password.encode("utf-8")

    # bcrypt supports passwords up to 72 bytes.
    if len(password_bytes) > 72:
        raise ValueError("Password must not exceed 72 UTF-8 bytes.")

    hashed_password = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt()
    )

    return hashed_password.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the password matches the stored bcrypt hash."""
    if not isinstance(password, str):
        return False

    if not isinstance(password_hash, str):
        return False

    password_bytes = password.encode("utf-8")

    if len(password_bytes) > 72:
        return False

    try:
        return bcrypt.checkpw(
            password_bytes,
            password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
