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


def test_logout_redirects(client):
    response = client.post("/logout")
    assert response.status_code == 302