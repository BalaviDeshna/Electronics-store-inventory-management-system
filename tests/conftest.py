import pytest
from app import create_app
from app.data.extensions import db


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def logged_in_admin(app, client):
    from app.data.models import User

    user = User(username="test-admin", role="admin")
    user.set_password("AdminPass123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login",
        data={
            "username": "test-admin",
            "password": "AdminPass123",
        },
    )
    return user


@pytest.fixture()
def logged_in_manager(app, client):
    from app.data.models import User

    user = User(username="test-manager", role="manager")
    user.set_password("ManagerPass123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login",
        data={
            "username": "test-manager",
            "password": "ManagerPass123",
        },
    )
    return user


@pytest.fixture()
def logged_in_staff(app, client):
    from app.data.models import User

    user = User(username="test-staff", role="staff")
    user.set_password("StaffPass123")
    db.session.add(user)
    db.session.commit()

    client.post(
        "/login",
        data={
            "username": "test-staff",
            "password": "StaffPass123",
        },
    )
    return user
