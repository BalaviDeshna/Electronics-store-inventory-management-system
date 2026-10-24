import app.presentation.routes.main as sales_routes
from decimal import Decimal

import pytest

from app.data.extensions import db
from app.data.models.sale import Sale, SaleItem
from app.business.sales import create_sale, SaleValidationError
import app.presentation.routes.main as sales_routes

class Product(db.Model):
    """Test-only product model; not the team's production model."""

    __tablename__ = "test_products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False)



@pytest.fixture(autouse=True)
def use_test_product_model(monkeypatch):
    monkeypatch.setattr(sales_routes, "Product", Product)

def add_product(name, price, stock):
    product = Product(
        name=name,
        price=Decimal(price),
        stock=stock,
    )
    db.session.add(product)
    db.session.commit()
    return product


def test_successful_sale_calculates_total_and_deducts_stock(app):
    with app.app_context():
        product = add_product("Keyboard", "25.50", 10)

        sale = create_sale(
            [{"product_id": product.id, "quantity": 2}],
            Product,
        )

        assert sale.total_amount == Decimal("51.00")
        assert len(sale.items) == 1
        assert sale.items[0].line_total == Decimal("51.00")
        assert db.session.get(Product, product.id).stock == 8


def test_insufficient_stock_does_not_create_sale(app):
    with app.app_context():
        product = add_product("Mouse", "15.00", 1)

        with pytest.raises(SaleValidationError, match="Insufficient stock"):
            create_sale(
                [{"product_id": product.id, "quantity": 2}],
                Product,
            )

        assert Sale.query.count() == 0
        assert SaleItem.query.count() == 0
        assert db.session.get(Product, product.id).stock == 1


def test_failed_multi_item_sale_rolls_back_stock_and_sale(app):
    with app.app_context():
        keyboard = add_product("Keyboard", "25.00", 5)
        monitor = add_product("Monitor", "200.00", 0)

        with pytest.raises(SaleValidationError, match="Insufficient stock"):
            create_sale(
                [
                    {"product_id": keyboard.id, "quantity": 2},
                    {"product_id": monitor.id, "quantity": 1},
                ],
                Product,
            )

        assert Sale.query.count() == 0
        assert SaleItem.query.count() == 0
        assert db.session.get(Product, keyboard.id).stock == 5
        assert db.session.get(Product, monitor.id).stock == 0


@pytest.mark.parametrize("quantity", [0, -1])
def test_invalid_quantity_is_rejected(app, quantity):
    with app.app_context():
        product = add_product("USB Cable", "5.00", 10)

        with pytest.raises(SaleValidationError):
            create_sale(
                [{"product_id": product.id, "quantity": quantity}],
                Product,
            )

        assert Sale.query.count() == 0
        assert db.session.get(Product, product.id).stock == 10


def test_invoice_page_displays_sale_details(app, client):
    with app.app_context():
        product = add_product("Keyboard", "25.50", 5)
        sale = create_sale(
            [{"product_id": product.id, "quantity": 2}],
            Product,
        )
        sale_id = sale.id

    response = client.get(f"/sales/{sale_id}/invoice")

    assert response.status_code == 200
    assert b"Sales Invoice" in response.data
    assert b"Transaction ID:" in response.data
    assert f"INV-{sale_id}".encode() in response.data
    assert b"Date:" in response.data
    assert b"Product" in response.data
    assert b"Quantity" in response.data
    assert b"Unit price" in response.data
    assert b"Line total" in response.data
    assert b"Grand total:" in response.data
    assert b"Print Invoice" in response.data
    assert b"Keyboard" in response.data
    assert b"51.00" in response.data

def test_invoice_returns_404_for_unknown_sale(client):
    response = client.get("/sales/999999/invoice")
    assert response.status_code == 404
@pytest.mark.parametrize("quantity", [1.5, "1.5", True])
def test_non_integer_quantity_is_rejected(app, quantity):
    with app.app_context():
        product = add_product("USB Cable", "5.00", 10)

        with pytest.raises(SaleValidationError):
            create_sale(
                [{"product_id": product.id, "quantity": quantity}],
                Product,
            )

        assert Sale.query.count() == 0
        assert db.session.get(Product, product.id).stock == 10


def test_create_sale_route_redirects_to_invoice(app, client):
    with app.app_context():
        product = add_product("Keyboard", "25.50", 5)
        product_id = product.id

    response = client.post(
        "/sales",
        data={
            "product_id": [str(product_id)],
            "quantity": ["2"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Sales Invoice" in response.data
    assert b"Keyboard" in response.data
    assert b"51.00" in response.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 3
        assert Sale.query.count() == 1


def test_create_sale_route_rejects_invalid_quantity(app, client):
    with app.app_context():
        product = add_product("Mouse", "15.00", 5)
        product_id = product.id

    response = client.post(
        "/sales",
        data={
            "product_id": [str(product_id)],
            "quantity": ["0"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"positive" in response.data.lower()

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 5
        assert Sale.query.count() == 0


def test_create_sale_route_rejects_insufficient_stock(app, client):
    with app.app_context():
        product = add_product("Monitor", "200.00", 1)
        product_id = product.id

    response = client.post(
        "/sales",
        data={
            "product_id": [str(product_id)],
            "quantity": ["2"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Insufficient stock" in response.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 1
        assert Sale.query.count() == 0


def test_sale_exact_stock_succeeds(app):
    with app.app_context():
        product = add_product("Earphones", "29.99", 5)

        sale = create_sale(
            [{"product_id": product.id, "quantity": 5}],
            Product,
        )

        assert sale.total_amount == Decimal("149.95")
        assert len(sale.items) == 1
        assert db.session.get(Product, product.id).stock == 0
        assert Sale.query.count() == 1


def test_sale_rejects_quantity_greater_than_stock_by_one(app):
    with app.app_context():
        product = add_product("Speaker", "89.00", 5)

        with pytest.raises(SaleValidationError) as exc_info:
            create_sale(
                [{"product_id": product.id, "quantity": 6}],
                Product,
            )

        assert "Insufficient stock" in str(exc_info.value)
        assert "Available: 5" in str(exc_info.value)
        assert "requested: 6" in str(exc_info.value)
        assert db.session.get(Product, product.id).stock == 5
        assert Sale.query.count() == 0
        assert SaleItem.query.count() == 0


def test_sale_rejects_purchase_when_stock_is_zero(app):
    with app.app_context():
        product = add_product("Laptop Stand", "35.00", 0)

        with pytest.raises(SaleValidationError) as exc_info:
            create_sale(
                [{"product_id": product.id, "quantity": 1}],
                Product,
            )

        assert "Insufficient stock" in str(exc_info.value)
        assert "Available: 0" in str(exc_info.value)
        assert "requested: 1" in str(exc_info.value)
        assert db.session.get(Product, product.id).stock == 0
        assert Sale.query.count() == 0


def test_sale_aggregates_multiple_lines_for_same_product_exceeding_stock(app):
    with app.app_context():
        product = add_product("Mousepad", "12.00", 4)

        with pytest.raises(SaleValidationError) as exc_info:
            create_sale(
                [
                    {"product_id": product.id, "quantity": 2},
                    {"product_id": product.id, "quantity": 3},
                ],
                Product,
            )

        assert "Insufficient stock" in str(exc_info.value)
        assert "Available: 4" in str(exc_info.value)
        assert "requested: 5" in str(exc_info.value)
        assert db.session.get(Product, product.id).stock == 4
        assert Sale.query.count() == 0


def test_multi_product_sale_fails_if_any_product_exceeds_stock_and_reverts_all(app):
    with app.app_context():
        p1 = add_product("Item One", "10.00", 10)
        p2 = add_product("Item Two", "20.00", 1)
        p3 = add_product("Item Three", "30.00", 5)

        with pytest.raises(SaleValidationError) as exc_info:
            create_sale(
                [
                    {"product_id": p1.id, "quantity": 2},
                    {"product_id": p2.id, "quantity": 3},
                    {"product_id": p3.id, "quantity": 1},
                ],
                Product,
            )

        assert "Insufficient stock" in str(exc_info.value)
        assert "Item Two" in str(exc_info.value)
        assert db.session.get(Product, p1.id).stock == 10
        assert db.session.get(Product, p2.id).stock == 1
        assert db.session.get(Product, p3.id).stock == 5
        assert Sale.query.count() == 0
        assert SaleItem.query.count() == 0


def test_create_sale_route_blocks_overselling_shows_clear_error_and_preserves_stock(app, client):
    with app.app_context():
        product = add_product("Smartwatch", "199.99", 3)
        product_id = product.id

    response = client.post(
        "/sales",
        data={
            "product_id": [str(product_id)],
            "quantity": ["4"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Insufficient stock" in response.data
    assert b"Smartwatch" in response.data
    assert b"Available: 3" in response.data
    assert b"requested: 4" in response.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 3
        assert Sale.query.count() == 0


def test_create_sale_route_multi_item_blocks_overselling(app, client):
    with app.app_context():
        keyboard = add_product("Keyboard Pro", "45.00", 10)
        mouse = add_product("Wireless Mouse", "25.00", 2)
        k_id = keyboard.id
        m_id = mouse.id

    response = client.post(
        "/sales",
        data={
            "product_id": [str(k_id), str(m_id)],
            "quantity": ["2", "5"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Insufficient stock" in response.data
    assert b"Wireless Mouse" in response.data

    with app.app_context():
        assert db.session.get(Product, k_id).stock == 10
        assert db.session.get(Product, m_id).stock == 2
        assert Sale.query.count() == 0


def test_create_sale_route_rejects_empty_items(client):
    response = client.post(
        "/sales",
        data={
            "product_id": ["", "   "],
            "quantity": ["", "   "],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"at least one item" in response.data or b"Invalid sale form" in response.data
    assert Sale.query.count() == 0
