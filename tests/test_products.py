
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


def test_edit_product_page_loads(client):
    product = Product(name="Gaming Mouse", price=Decimal("120.00"), stock=15)
    db.session.add(product)
    db.session.commit()

    response = client.get(f"/products/{product.id}/edit")

    assert response.status_code == 200
    assert b"Edit Product" in response.data
    assert b"Gaming Mouse" in response.data
    assert b"120.00" in response.data
    assert b"15" in response.data


def test_update_product_success(client):
    product = Product(name="Gaming Mouse", price=Decimal("120.00"), stock=15)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Pro Gaming Mouse", "price": "149.99", "stock": "20"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated_product = db.session.get(Product, product_id)
    assert updated_product.name == "Pro Gaming Mouse"
    assert updated_product.price == Decimal("149.99")
    assert updated_product.stock == 20


def test_update_product_preserves_id_and_does_not_create_duplicate(client):
    product = Product(name="Headphones", price=Decimal("89.99"), stock=8)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Wireless Headphones", "price": "99.99", "stock": "10"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    all_products = db.session.execute(db.select(Product)).scalars().all()
    assert len(all_products) == 1
    assert all_products[0].id == product_id
    assert all_products[0].name == "Wireless Headphones"


def test_update_product_rejects_empty_name(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "   ", "price": "55.00", "stock": "7"},
    )

    assert response.status_code == 200
    assert b"Product name is required." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_name_exceeding_max_length(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "A" * 201, "price": "55.00", "stock": "7"},
    )

    assert response.status_code == 200
    assert b"Product name must be 200 characters or fewer." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_negative_price(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Mechanical Keyboard", "price": "-20.00", "stock": "5"},
    )

    assert response.status_code == 200
    assert b"Enter a valid, non-negative price." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_negative_stock(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Mechanical Keyboard", "price": "60.00", "stock": "-1"},
    )

    assert response.status_code == 200
    assert b"Stock must be a non-negative whole number." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_invalid_price_and_stock(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    resp_price = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Keyboard", "price": "not-a-price", "stock": "5"},
    )
    assert resp_price.status_code == 200
    assert b"Enter a valid, non-negative price." in resp_price.data

    resp_stock = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Keyboard", "price": "50.00", "stock": "not-an-int"},
    )
    assert resp_stock.status_code == 200
    assert b"Stock must be a non-negative whole number." in resp_stock.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_nonexistent_product_returns_404(client):
    resp_get = client.get("/products/999999/edit")
    assert resp_get.status_code == 404
    assert b"Product not found." in resp_get.data

    resp_post = client.post(
        "/products/999999/edit",
        data={"name": "Ghost", "price": "10.00", "stock": "1"},
    )
    assert resp_post.status_code == 404
    assert b"Product not found." in resp_post.data


def test_update_product_via_update_route(client):
    product = Product(name="Webcam", price=Decimal("45.00"), stock=6)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    resp_get = client.get(f"/products/{product_id}/update")
    assert resp_get.status_code == 200
    assert b"Webcam" in resp_get.data

    resp_post = client.post(
        f"/products/{product_id}/update",
        data={"name": "HD Webcam", "price": "55.00", "stock": "10"},
        follow_redirects=True,
    )
    assert resp_post.status_code == 200
    assert b"Product updated successfully." in resp_post.data

    updated = db.session.get(Product, product_id)
    assert updated.name == "HD Webcam"
    assert updated.price == Decimal("55.00")
    assert updated.stock == 10
