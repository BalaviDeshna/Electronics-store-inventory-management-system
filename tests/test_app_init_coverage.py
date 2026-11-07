import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch

from app import create_app, load_user
from app.data.models import Supplier


def test_load_user_invalid_ids():
    assert load_user(None) is None
    assert load_user("invalid_string") is None
    assert load_user(object()) is None


def test_create_app_legacy_sqlite_migrations(tmp_path):
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "CREATE TABLE products ("
        "id INTEGER PRIMARY KEY, "
        "name VARCHAR(100), "
        "price NUMERIC(10, 2), "
        "stock INTEGER)"
    )
    conn.execute(
        "CREATE TABLE product_returns ("
        "id INTEGER PRIMARY KEY, "
        "quantity INTEGER)"
    )
    conn.commit()
    conn.close()

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file.as_posix()}",
    })

    with app.app_context():
        from app.data.extensions import db
        from sqlalchemy import inspect
        insp = inspect(db.engine)
        p_cols = {c["name"] for c in insp.get_columns("products")}
        r_cols = {c["name"] for c in insp.get_columns("product_returns")}
        assert "reorder_threshold" in p_cols
        assert "supplier_id" in p_cols
        assert "refund_amount" in r_cols


def test_create_app_supporting_tables_failure():
    with patch.object(Supplier.__table__, "create", side_effect=RuntimeError("fail tables")):
        with pytest.raises(RuntimeError, match="fail tables"):
            create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def test_create_app_products_schema_failure():
    class FakeInspector:
        def get_table_names(self):
            return ["products"]
        def get_columns(self, name):
            raise RuntimeError("fail products columns")

    with patch("app.inspect", return_value=FakeInspector()):
        with pytest.raises(RuntimeError, match="fail products columns"):
            create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


def test_create_app_returns_schema_failure():
    class FakeInspector:
        def get_table_names(self):
            return ["product_returns"]
        def get_columns(self, name):
            raise RuntimeError("fail product_returns columns")

    with patch("app.inspect", return_value=FakeInspector()):
        with pytest.raises(RuntimeError, match="fail product_returns columns"):
            create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

