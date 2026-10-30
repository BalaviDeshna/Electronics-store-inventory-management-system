from app.data.extensions import db
from app.data.models import User
from unittest.mock import patch
from itsdangerous import URLSafeTimedSerializer


def add_user():
    user = User(username="deshna-test")
    user.set_password("CorrectPassword123")
    db.session.add(user)
    db.session.commit()


def test_login_page_loads(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"Log In" in response.data


def test_correct_password_logs_in(client, app):
    with app.app_context():
        add_user()

    response = client.post(
        "/login",
        data={
            "username": "deshna-test",
            "password": "CorrectPassword123",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200


def test_wrong_password_is_rejected(client, app):
    with app.app_context():
        add_user()

    response = client.post(
        "/login",
        data={
            "username": "deshna-test",
            "password": "WrongPassword123",
        },
        follow_redirects=True,
    )
    assert b"Invalid username or password, or account deactivated." in response.data
    assert b'<p class="error" role="alert">' in response.data


def test_unknown_username_is_rejected(client):
    response = client.post(
        "/login",
        data={
            "username": "unknown-user",
            "password": "anything",
        },
        follow_redirects=True,
    )
    assert b"Invalid username or password, or account deactivated." in response.data

def test_create_user_page_requires_login(client):
    response = client.get("/users/create")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_create_user_success(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={"username": "new-staff",
              "password": "StrongPass123",
              "role": "staff",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"User account created successfully." in response.data
    user = User.query.filter_by(username="new-staff").one()
    assert user.password_hash != "StrongPass123"
    assert user.check_password("StrongPass123")


def test_duplicate_username_is_rejected(client, logged_in_admin):
    user = User(username="existing-user")
    user.set_password("StrongPass123")
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/users/create",
        data={"username": "existing-user",
              "password": "AnotherPass123",
              "role": "staff",
        },
        follow_redirects=True,
    )
    assert b"That username is already taken." in response.data
    assert User.query.filter_by(username="existing-user").count() == 1


def test_empty_username_is_rejected(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={"username": "   ",
              "password": "StrongPass123"
        },
        follow_redirects=True,
    )
    assert b"Username is required." in response.data


def test_short_password_is_rejected(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={"username": "short-pass",
              "password": "123"
        },
        follow_redirects=True,
    )
    assert b"Password must be at least 8 characters." in response.data

def test_staff_cannot_create_accounts(client, logged_in_staff):
    response = client.post(
        "/users/create",
        data={"username": "not-allowed",
              "password": "StrongPass123"
        },
    )
    assert response.status_code in (302, 403)
    assert User.query.filter_by(username="not-allowed").first() is None

def test_admin_can_create_staff_user(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={
            "username": "new-staff-role",
            "password": "StrongPass123",
            "role": "staff",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    user = User.query.filter_by(username="new-staff-role").one()
    assert user.role == "staff"


def test_admin_can_assign_admin_role(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={
            "username": "new-admin-role",
            "password": "StrongPass123",
            "role": "admin",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    user = User.query.filter_by(username="new-admin-role").one()
    assert user.role == "admin"


def test_invalid_role_is_rejected(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={
            "username": "bad-role-user",
            "password": "StrongPass123",
            "role": "superuser",
        },
    )
    assert response.status_code == 400
    assert User.query.filter_by(username="bad-role-user").first() is None

def test_logout_redirects(client):
    response = client.post("/logout")
    assert response.status_code == 302
    
def test_staff_cannot_list_users(client, logged_in_staff):
    response = client.get("/users")
    assert response.status_code == 403


def test_admin_can_edit_user_role(client, app, logged_in_admin):
    user = User(username="edit-me", role="staff")
    user.set_password("StrongPass123")
    db.session.add(user)
    db.session.commit()

    response = client.post(
        f"/users/{user.id}/edit",
        data={"username": "edit-me", "role": "admin"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert user.role == "admin"


def test_admin_can_deactivate_user(client, app, logged_in_admin):
    user = User(username="disable-me", role="staff")
    user.set_password("StrongPass123")
    db.session.add(user)
    db.session.commit()

    response = client.post(
        f"/users/{user.id}/deactivate",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert user.is_active is False


def test_deactivated_user_cannot_login(client, app):
    user = User(
        username="inactive-user",
        role="staff",
        is_active=False,
    )
    user.set_password("StrongPass123")
    db.session.add(user)
    db.session.commit()

    response = client.post(
        "/login",
        data={
            "username": "inactive-user",
            "password": "StrongPass123",
        },
        follow_redirects=True,
    )
    assert b"Invalid username or password" in response.data

def test_forgot_password_sends_email(client, app):
    with app.app_context():
        user = User(username="reset-user", email="reset@example.com")
        user.set_password("OldPassword123")
        db.session.add(user)
        db.session.commit()

    with patch("app.presentation.routes.auth.send_reset_email") as send:
        response = client.post(
            "/forgot-password",
            data={"email": "reset@example.com"},
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert b"If an active account uses that email" in response.data
    send.assert_called_once()
    assert "reset-password/" in send.call_args.args[1]


def test_forgot_password_unknown_email_same_message(client):
    response = client.post(
        "/forgot-password",
        data={"email": "nobody@example.com"},
        follow_redirects=True,
    )

    assert b"If an active account uses that email" in response.data


def test_reset_password_changes_password(client, app):
    with app.app_context():
        user = User(username="reset-user", email="reset@example.com")
        user.set_password("OldPassword123")
        db.session.add(user)
        db.session.commit()

        token = URLSafeTimedSerializer(
            app.config["SECRET_KEY"]
        ).dumps(
            {"user_id": user.id, "email": user.email},
            salt="password-reset-v1",
        )

    response = client.post(
        f"/reset-password/{token}",
        data={
            "password": "NewPassword123",
            "confirm_password": "NewPassword123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        user = User.query.filter_by(username="reset-user").one()
        assert user.check_password("NewPassword123")
        assert not user.check_password("OldPassword123")


def test_reset_password_rejects_mismatch(client, app):
    with app.app_context():
        user = User(username="reset-user", email="reset@example.com")
        user.set_password("OldPassword123")
        db.session.add(user)
        db.session.commit()

        token = URLSafeTimedSerializer(
            app.config["SECRET_KEY"]
        ).dumps(
            {"user_id": user.id, "email": user.email},
            salt="password-reset-v1",
        )

    response = client.post(
        f"/reset-password/{token}",
        data={
            "password": "NewPassword123",
            "confirm_password": "Different123",
        },
    )

    assert response.status_code == 400