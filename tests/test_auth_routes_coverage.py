import pytest
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError
from itsdangerous import URLSafeTimedSerializer

from app.data.extensions import db
from app.data.models import User


from app.presentation.routes.auth import _make_reset_token


def test_login_already_authenticated(client, logged_in_admin):
    r = client.get("/login")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/") or "/" in r.headers["Location"]


def test_forgot_password_get(client):
    r = client.get("/forgot-password")
    assert r.status_code == 200
    assert b"Forgot password" in r.data or b"password" in r.data.lower()


def test_forgot_password_email_exception(app, client):
    with app.app_context():
        u = User(username="email-user", email="user@example.com", role="staff")
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()

    with patch("app.presentation.routes.auth.send_reset_email", side_effect=Exception("SMTP down")):
        r = client.post("/forgot-password", data={"email": "user@example.com"})
        assert r.status_code == 302
        r2 = client.get(r.headers["Location"])
        assert b"If an active account uses that email" in r2.data


def test_reset_password_invalid_or_expired_token(app, client):
    r = client.get("/reset-password/totally-invalid-token")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/forgot-password")

    r2 = client.post("/reset-password/totally-invalid-token", data={"password": "NewPassword123"})
    assert r2.status_code == 302
    assert r2.headers["Location"].endswith("/forgot-password")


def test_reset_password_deactivated_or_deleted_user(app, client):
    with app.app_context():
        u = User(username="deact-user", email="deact@example.com", role="staff", is_active=False)
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()
        token = _make_reset_token(u)

    r = client.get(f"/reset-password/{token}")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/forgot-password")


def test_reset_password_get_and_short_password(app, client):
    with app.app_context():
        u = User(username="active-reset-user", email="active_reset@example.com", role="staff", is_active=True)
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()
        token = _make_reset_token(u)

    # Valid GET renders reset page
    r = client.get(f"/reset-password/{token}")
    assert r.status_code == 200

    # Short password (< 8 chars) -> 400
    r = client.post(f"/reset-password/{token}", data={"password": "short", "confirm_password": "short"})
    assert r.status_code == 400


def test_create_user_validation_and_errors(client, logged_in_admin):
    # Duplicate email
    client.post("/users/create", data={
        "username": "user1",
        "email": "duplicate@example.com",
        "role": "staff",
        "password": "Password123",
    })
    r = client.post("/users/create", data={
        "username": "user2",
        "email": "duplicate@example.com",
        "role": "staff",
        "password": "Password123",
    })
    assert r.status_code == 409

    # Username > 80 chars -> 400
    r = client.post("/users/create", data={
        "username": "a" * 81,
        "email": "toolong@example.com",
        "role": "staff",
        "password": "Password123",
    })
    assert r.status_code == 400

    # Password empty -> 400
    r = client.post("/users/create", data={
        "username": "nopassuser",
        "email": "nopass@example.com",
        "role": "staff",
        "password": "   ",
    })
    assert r.status_code == 400

    # IntegrityError during commit -> 409
    with patch("app.data.extensions.db.session.commit", side_effect=IntegrityError("stmt", "params", "orig")):
        r = client.post("/users/create", data={
            "username": "integuser",
            "email": "integ@example.com",
            "role": "staff",
            "password": "Password123",
        })
        assert r.status_code == 409
        assert b"username is already taken" in r.data

    # Generic Exception during commit -> 500
    with patch("app.data.extensions.db.session.commit", side_effect=RuntimeError("db crash")):
        r = client.post("/users/create", data={
            "username": "erruser",
            "email": "err@example.com",
            "role": "staff",
            "password": "Password123",
        })
        assert r.status_code == 500
        assert b"account could not be created" in r.data


def test_edit_user_routes_coverage(app, client, logged_in_admin):
    with app.app_context():
        u1 = User(username="edit-target-1", email="target1@example.com", role="staff")
        u1.set_password("Password123")
        u2 = User(username="edit-target-2", email="target2@example.com", role="staff")
        u2.set_password("Password123")
        db.session.add_all([u1, u2])
        db.session.commit()
        u1_id = u1.id
        u2_id = u2.id

    # Nonexistent user -> 404
    r = client.get("/users/99999/edit")
    assert r.status_code == 404
    r = client.post("/users/99999/edit", data={"username": "new", "role": "staff"})
    assert r.status_code == 404

    # GET valid user -> 200
    r = client.get(f"/users/{u1_id}/edit")
    assert r.status_code == 200

    # Username empty or > 80 -> 400
    r = client.post(f"/users/{u1_id}/edit", data={"username": "", "role": "staff"})
    assert r.status_code == 400
    assert b"Enter a username of 1" in r.data

    # Invalid role -> 400
    r = client.post(f"/users/{u1_id}/edit", data={"username": "validname", "role": "superman"})
    assert r.status_code == 400
    assert b"Choose a valid role" in r.data

    # Username taken by another user -> 409
    r = client.post(f"/users/{u1_id}/edit", data={"username": "edit-target-2", "role": "staff"})
    assert r.status_code == 409
    assert b"username is already taken" in r.data

    # Email taken by another user -> 409
    r = client.post(f"/users/{u1_id}/edit", data={"username": "edit-target-1", "email": "target2@example.com", "role": "staff"})
    assert r.status_code == 409
    assert b"email is already in use" in r.data

    # IntegrityError on commit -> 409
    with patch("app.data.extensions.db.session.commit", side_effect=IntegrityError("stmt", "params", "orig")):
        r = client.post(f"/users/{u1_id}/edit", data={"username": "integ-edit", "role": "staff"})
        assert r.status_code == 409
        assert b"username is already taken" in r.data


def test_deactivate_and_reactivate_user(app, client, logged_in_admin):
    with app.app_context():
        u = User(username="deact-candidate", email="cand@example.com", role="staff", is_active=True)
        u.set_password("Password123")
        db.session.add(u)
        db.session.commit()
        u_id = u.id

    # Self deactivation rejected
    r = client.post(f"/users/{logged_in_admin.id}/deactivate")
    assert r.status_code == 302
    r_follow = client.get(r.headers["Location"])
    assert b"cannot deactivate your own account" in r_follow.data

    # Nonexistent user deactivation -> 404
    r = client.post("/users/99999/deactivate")
    assert r.status_code == 404

    # Deactivate u
    r = client.post(f"/users/{u_id}/deactivate")
    assert r.status_code == 302

    # Reactivate nonexistent user -> 404
    r = client.post("/users/99999/reactivate")
    assert r.status_code == 404

    # Reactivate valid user
    r = client.post(f"/users/{u_id}/reactivate")
    assert r.status_code == 302
    r_follow = client.get(r.headers["Location"])
    assert b"User reactivated" in r_follow.data

    with app.app_context():
        u_fresh = db.session.get(User, u_id)
        assert u_fresh.is_active is True
