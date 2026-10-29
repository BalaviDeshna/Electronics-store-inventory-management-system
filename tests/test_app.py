def test_home_page_returns_success(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Electronics Store Inventory Management" in response.data
    assert b"Application Setup Successful" in response.data


def test_app_startup_fails_when_supporting_table_creation_fails(
    monkeypatch,
):
    from app import Supplier, create_app

    def fail_table_creation(*args, **kwargs):
        raise RuntimeError("Database setup failed")

    monkeypatch.setattr(
        Supplier.__table__,
        "create",
        fail_table_creation,
    )

    import pytest

    with pytest.raises(RuntimeError, match="Database setup failed"):
        create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        })
