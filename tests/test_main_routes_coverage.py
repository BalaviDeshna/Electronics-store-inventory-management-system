import pytest
from decimal import Decimal
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError

from app.data.extensions import db
from app.data.models import Product, Supplier, Sale
from app.presentation.routes.main import parse_reorder_threshold, parse_supplier_id


def test_parse_reorder_threshold_and_supplier_id():
    # parse_reorder_threshold
    with pytest.raises(ValueError, match="Reorder threshold is required"):
        parse_reorder_threshold(None, required=True)
    with pytest.raises(ValueError, match="non-negative whole number"):
        parse_reorder_threshold(-5)
    with pytest.raises(ValueError, match="Reorder threshold is required"):
        parse_reorder_threshold("", required=True)
    assert parse_reorder_threshold("", required=False, default=10) == 10

    # parse_supplier_id
    assert parse_supplier_id("") is None
    assert parse_supplier_id("   ") is None
    with pytest.raises(ValueError, match="Please select a valid supplier"):
        parse_supplier_id("not_a_number")


def test_home_filter_low_stock(app, client, logged_in_staff):
    with app.app_context():
        p1 = Product(name="P Low", price=Decimal("10.00"), stock=3)
        p2 = Product(name="P Out", price=Decimal("10.00"), stock=0)
        p3 = Product(name="P High", price=Decimal("10.00"), stock=20)
        db.session.add_all([p1, p2, p3])
        db.session.commit()

    r = client.get("/?stock_status=low")
    assert r.status_code == 200
    assert b"P Low" in r.data


def test_create_sale_errors_and_exceptions(app, client, logged_in_staff):
    with app.app_context():
        p = Product(name="P Sale", price=Decimal("15.00"), stock=10)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    # Unequal product_ids and quantities -> line 197-198
    r = client.post("/sales", data={
        "product_id": [str(pid), "2"],
        "quantity": ["1"],
    })
    assert r.status_code == 302

    # Exception during sale creation -> line 211-215
    with patch("app.presentation.routes.main.create_sale", side_effect=RuntimeError("sale crash")):
        r = client.post("/sales", data={
            "product_id": [str(pid)],
            "quantity": ["1"],
        })
        assert r.status_code == 302


def test_create_product_validation_and_errors(app, client, logged_in_admin):
    # Name > 200 chars
    r = client.post("/products/create", data={
        "name": "N" * 201,
        "price": "10.00",
        "stock": "5",
    })
    assert r.status_code == 200

    # SKU > 100 chars
    r = client.post("/products/create", data={
        "name": "Valid Name",
        "sku": "S" * 101,
        "price": "10.00",
        "stock": "5",
    })
    assert r.status_code == 200

    # Category > 100 chars
    r = client.post("/products/create", data={
        "name": "Valid Name",
        "category": "C" * 101,
        "price": "10.00",
        "stock": "5",
    })
    assert r.status_code == 200

    # ValueError in threshold
    r = client.post("/products/create", data={
        "name": "Valid Name",
        "price": "10.00",
        "stock": "5",
        "reorder_threshold": "not_int",
    })
    assert r.status_code == 200

    # IntegrityError during commit
    with patch("app.data.extensions.db.session.commit", side_effect=IntegrityError("stmt", "params", "orig")):
        r = client.post("/products/create", data={
            "name": "Integ Product",
            "price": "10.00",
            "stock": "5",
        })
        assert r.status_code == 200

    # Generic Exception during commit
    with patch("app.data.extensions.db.session.commit", side_effect=RuntimeError("prod crash")):
        r = client.post("/products/create", data={
            "name": "Err Product",
            "price": "10.00",
            "stock": "5",
        })
        assert r.status_code == 200


def test_edit_product_validation_and_errors(app, client, logged_in_admin):
    with app.app_context():
        p = Product(name="Edit Base", price=Decimal("25.00"), stock=10)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    # SKU > 100 chars
    r = client.post(f"/products/{pid}/edit", data={
        "name": "Edit Base",
        "sku": "K" * 101,
        "price": "25.00",
        "stock": "10",
    })
    assert r.status_code == 200

    # Category > 100 chars
    r = client.post(f"/products/{pid}/edit", data={
        "name": "Edit Base",
        "category": "G" * 101,
        "price": "25.00",
        "stock": "10",
    })
    assert r.status_code == 200

    # ValueError in supplier
    r = client.post(f"/products/{pid}/edit", data={
        "name": "Edit Base",
        "price": "25.00",
        "stock": "10",
        "supplier_id": "not_an_int",
    })
    assert r.status_code == 200

    # IntegrityError
    with patch("app.data.extensions.db.session.commit", side_effect=IntegrityError("stmt", "params", "orig")):
        r = client.post(f"/products/{pid}/edit", data={
            "name": "Edit Base",
            "price": "25.00",
            "stock": "10",
        })
        assert r.status_code == 200

    # Generic Exception
    with patch("app.data.extensions.db.session.commit", side_effect=RuntimeError("edit crash")):
        r = client.post(f"/products/{pid}/edit", data={
            "name": "Edit Base",
            "price": "25.00",
            "stock": "10",
        })
        assert r.status_code == 200


def test_update_threshold_restock_return_exceptions(app, client, logged_in_admin):
    with app.app_context():
        p = Product(name="Action Prod", price=Decimal("10.00"), stock=10)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    # update_reorder_threshold exception
    with patch("app.data.extensions.db.session.commit", side_effect=RuntimeError("threshold crash")):
        r = client.post(f"/products/{pid}/reorder-threshold", data={"reorder_threshold": "5"})
        assert r.status_code == 302

    # restock exception
    with patch("app.presentation.routes.main.restock_product", side_effect=RuntimeError("restock crash")):
        r = client.post(f"/products/{pid}/restock", data={"quantity": "5"})
        assert r.status_code == 302

    # return exception
    with patch("app.presentation.routes.main.process_return", side_effect=RuntimeError("return crash")):
        r = client.post("/returns", data={"sale_item_id": "1", "quantity": "1"})
        assert r.status_code == 302


def test_reports_non_iso_date_handling(client, logged_in_manager):
    r1 = client.get("/reports/revenue?start_date=2026-1-1&end_date=2026-01-31")
    assert r1.status_code == 200

    r2 = client.get("/reports/sales?start_date=2026-1-1&end_date=2026-01-31")
    assert r2.status_code == 200

    r3 = client.get("/reports/stock?start_date=2026-1-1&end_date=2026-01-31")
    assert r3.status_code == 200
