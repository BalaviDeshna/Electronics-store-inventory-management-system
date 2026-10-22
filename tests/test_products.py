
from decimal import Decimal

from app.data.extensions import db
from app.data.models.product import Product


def test_create_product_page_loads(client):
    response = client.get("/products/create")

    assert response.status_code == 200
    assert b"Create Product" in response.data
    assert b"Product name" in response.data


def test_create_product_success(client):
    response = client.post(
        "/products/create",
        data={"name": "Wireless Mouse", "price": "799.99", "stock": "10"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    product = db.session.execute(
        db.select(Product).filter_by(name="Wireless Mouse")
    ).scalar_one()

    assert product.price == Decimal("799.99")
    assert product.stock == 10


def test_create_product_rejects_empty_name(client):
    response = client.post(
        "/products/create",
        data={"name": "  ", "price": "100.00", "stock": "5"},
    )

    assert response.status_code == 200
    assert b"Product name is required." in response.data
    assert db.session.execute(db.select(Product)).scalars().all() == []


def test_create_product_rejects_negative_price(client):
    response = client.post(
        "/products/create",
        data={"name": "Keyboard", "price": "-10", "stock": "5"},
    )

    assert response.status_code == 200
    assert b"Enter a valid, non-negative price." in response.data
    assert db.session.execute(db.select(Product)).scalars().all() == []


def test_create_product_rejects_negative_stock(client):
    response = client.post(
        "/products/create",
        data={"name": "Keyboard", "price": "100", "stock": "-1"},
    )

    assert response.status_code == 200
    assert b"Stock must be a non-negative whole number." in response.data
    assert db.session.execute(db.select(Product)).scalars().all() == []
