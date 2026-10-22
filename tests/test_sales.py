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

