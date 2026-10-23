from app.data.extensions import db
from app.data.models import User


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
    assert b"Invalid username or password." in response.data


def test_unknown_username_is_rejected(client):
    response = client.post(
        "/login",
        data={
            "username": "unknown-user",
            "password": "anything",
        },
        follow_redirects=True,
    )
    assert b"Invalid username or password." in response.data

def test_create_user_page_requires_login(client):
    response = client.get("/users/create")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_create_user_success(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={"username": "new-staff", "password": "StrongPass123"},
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
        data={"username": "existing-user", "password": "AnotherPass123"},
        follow_redirects=True,
    )
    assert b"That username is already taken." in response.data
    assert User.query.filter_by(username="existing-user").count() == 1


def test_empty_username_is_rejected(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={"username": "   ", "password": "StrongPass123"},
        follow_redirects=True,
    )
    assert b"Username is required." in response.data


def test_short_password_is_rejected(client, logged_in_admin):
    response = client.post(
        "/users/create",
        data={"username": "short-pass", "password": "123"},
        follow_redirects=True,
    )
    assert b"Password must be at least 8 characters." in response.data


def test_staff_cannot_create_accounts(client, logged_in_staff):
    response = client.post(
        "/users/create",
        data={"username": "not-allowed", "password": "StrongPass123"},
    )
    assert response.status_code in (302, 403)
    assert User.query.filter_by(username="not-allowed").first() is None

def test_logout_redirects(client):
    response = client.post("/logout")
    assert response.status_code == 302