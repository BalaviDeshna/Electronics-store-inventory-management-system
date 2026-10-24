import app.presentation.routes.main as sales_routes
from decimal import Decimal

import pytest

from app.business.sales import create_sale, SaleValidationError
from app.business.stock import (
    StockUpdateError,
    process_return,
    restock_inventory,
    restock_product,
)
from app.data.extensions import db
from app.data.models.sale import Sale, SaleItem
from app.data.models.stock import ProductRestock, ProductReturn

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




def test_successful_multi_product_sale_records_items_totals_and_stock(app, client):
    """Verify checkout records multiple products in one sale."""
    with app.app_context():
        keyboard = add_product("Keyboard", "25.00", 5)
        mouse = add_product("Mouse", "15.00", 4)
        keyboard_id = keyboard.id
        mouse_id = mouse.id

    response = client.post(
        "/sales",
        data={
            "product_id": [str(keyboard_id), str(mouse_id)],
            "quantity": ["2", "3"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Keyboard" in response.data
    assert b"Mouse" in response.data
    assert b"95.00" in response.data

    with app.app_context():
        sale = Sale.query.order_by(Sale.id.desc()).first()
        assert sale is not None
        assert sale.total_amount == Decimal("95.00")
        assert len(sale.items) == 2

        items = {item.product_id: item for item in sale.items}
        assert items[keyboard_id].quantity == 2
        assert items[keyboard_id].line_total == Decimal("50.00")
        assert items[mouse_id].quantity == 3
        assert items[mouse_id].line_total == Decimal("45.00")

        assert db.session.get(Product, keyboard_id).stock == 3
        assert db.session.get(Product, mouse_id).stock == 1
        assert Sale.query.count() == 1


def test_stock_auto_deducted_after_successful_sale(app):
    with app.app_context():
        product = add_product("Wireless Router", "69.99", 10)
        sale = create_sale(
            [{"product_id": product.id, "quantity": 4}],
            Product,
        )

        assert sale is not None
        assert db.session.get(Product, product.id).stock == 6


def test_stock_unchanged_after_failed_sale(app):
    with app.app_context():
        product = add_product("Gaming Console", "499.99", 3)

        with pytest.raises(SaleValidationError):
            create_sale(
                [{"product_id": product.id, "quantity": 4}],
                Product,
            )

        assert db.session.get(Product, product.id).stock == 3
        assert Sale.query.count() == 0


def test_stock_auto_increased_after_valid_return_by_sale_item(app):
    with app.app_context():
        product = add_product("Mechanical Keyboard", "80.00", 10)
        sale = create_sale(
            [{"product_id": product.id, "quantity": 3}],
            Product,
        )
        assert db.session.get(Product, product.id).stock == 7
        sale_item = sale.items[0]

        returned_product = process_return(
            sale_item_id=sale_item.id,
            quantity=2,
            return_id="RET-001",
            product_model=Product,
        )

        assert returned_product.stock == 9
        assert db.session.get(Product, product.id).stock == 9

        return_rec = ProductReturn.query.filter_by(return_id="RET-001").first()
        assert return_rec is not None
        assert return_rec.quantity == 2
        assert return_rec.product_id == product.id
        assert return_rec.sale_item_id == sale_item.id


def test_return_rejects_quantity_exceeding_purchased_amount(app):
    with app.app_context():
        product = add_product("Bluetooth Speaker", "40.00", 5)
        sale = create_sale(
            [{"product_id": product.id, "quantity": 2}],
            Product,
        )
        assert db.session.get(Product, product.id).stock == 3
        sale_item = sale.items[0]

        with pytest.raises(StockUpdateError) as exc_info:
            process_return(
                sale_item_id=sale_item.id,
                quantity=3,
                product_model=Product,
            )

        assert "Cannot return 3 units" in str(exc_info.value)
        assert db.session.get(Product, product.id).stock == 3


def test_return_prevents_duplicate_processing_via_return_id(app):
    with app.app_context():
        product = add_product("USB-C Hub", "25.00", 8)
        sale = create_sale(
            [{"product_id": product.id, "quantity": 2}],
            Product,
        )
        assert db.session.get(Product, product.id).stock == 6
        sale_item = sale.items[0]

        # First return succeeds
        process_return(
            sale_item_id=sale_item.id,
            quantity=1,
            return_id="RET-UNIQUE-101",
            product_model=Product,
        )
        assert db.session.get(Product, product.id).stock == 7

        # Duplicate return with same return_id fails
        with pytest.raises(StockUpdateError) as exc_info:
            process_return(
                sale_item_id=sale_item.id,
                quantity=1,
                return_id="RET-UNIQUE-101",
                product_model=Product,
            )

        assert "already been processed" in str(exc_info.value)
        # Stock must remain unchanged after duplicate attempt
        assert db.session.get(Product, product.id).stock == 7


def test_return_prevents_cumulative_returns_exceeding_sale_quantity(app):
    with app.app_context():
        product = add_product("Webcam", "50.00", 10)
        sale = create_sale(
            [{"product_id": product.id, "quantity": 2}],
            Product,
        )
        assert db.session.get(Product, product.id).stock == 8
        sale_item = sale.items[0]

        # Return 1 of 2
        process_return(
            sale_item_id=sale_item.id,
            quantity=1,
            return_id="RET-PART-1",
            product_model=Product,
        )
        assert db.session.get(Product, product.id).stock == 9

        # Return second of 2
        process_return(
            sale_item_id=sale_item.id,
            quantity=1,
            return_id="RET-PART-2",
            product_model=Product,
        )
        assert db.session.get(Product, product.id).stock == 10

        # Attempt third return exceeds purchased amount
        with pytest.raises(StockUpdateError):
            process_return(
                sale_item_id=sale_item.id,
                quantity=1,
                return_id="RET-PART-3",
                product_model=Product,
            )

        assert db.session.get(Product, product.id).stock == 10


def test_standalone_product_return_increases_stock(app):
    with app.app_context():
        product = add_product("Wireless Earbuds", "120.00", 4)

        returned = process_return(
            product_id=product.id,
            quantity=3,
            return_id="RET-STANDALONE-01",
            product_model=Product,
        )

        assert returned.stock == 7
        assert db.session.get(Product, product.id).stock == 7
        rec = ProductReturn.query.filter_by(return_id="RET-STANDALONE-01").first()
        assert rec is not None
        assert rec.quantity == 3


@pytest.mark.parametrize("invalid_qty", [0, -1, -5, "abc", 1.5, True, False])
def test_return_rejects_invalid_quantity(app, invalid_qty):
    with app.app_context():
        product = add_product("Monitor Stand", "30.00", 6)

        with pytest.raises(StockUpdateError):
            process_return(
                product_id=product.id,
                quantity=invalid_qty,
                product_model=Product,
            )

        assert db.session.get(Product, product.id).stock == 6


def test_return_rejects_invalid_product_reference(app):
    with app.app_context():
        with pytest.raises(StockUpdateError):
            process_return(
                product_id=999999,
                quantity=2,
                product_model=Product,
            )


def test_stock_auto_increased_after_restocking(app):
    with app.app_context():
        product = add_product("Microphone Stand", "25.00", 5)

        restocked = restock_product(
            product.id,
            15,
            reference="PO-2026-001",
            product_model=Product,
        )

        assert restocked.stock == 20
        assert db.session.get(Product, product.id).stock == 20

        rec = ProductRestock.query.filter_by(reference="PO-2026-001").first()
        assert rec is not None
        assert rec.quantity == 15
        assert rec.product_id == product.id


@pytest.mark.parametrize("invalid_qty", [0, -1, -20, "xyz", 3.14, True, False])
def test_restock_rejects_invalid_quantities(app, invalid_qty):
    with app.app_context():
        product = add_product("HDMI Adapter", "15.00", 8)

        with pytest.raises(StockUpdateError):
            restock_product(
                product.id,
                invalid_qty,
                product_model=Product,
            )

        assert db.session.get(Product, product.id).stock == 8
        assert ProductRestock.query.count() == 0


def test_restock_rejects_nonexistent_product(app):
    with app.app_context():
        with pytest.raises(StockUpdateError):
            restock_product(
                888888,
                10,
                product_model=Product,
            )


def test_batch_restock_atomic_success_and_failure(app):
    with app.app_context():
        p1 = add_product("Item A", "10.00", 5)
        p2 = add_product("Item B", "20.00", 2)
        p1_id, p2_id = p1.id, p2.id

        # Batch restock success
        restock_inventory(
            [
                {"product_id": p1_id, "quantity": 5},
                {"product_id": p2_id, "quantity": 8},
            ],
            product_model=Product,
        )

        assert db.session.get(Product, p1_id).stock == 10
        assert db.session.get(Product, p2_id).stock == 10

        # Batch restock failure leaves all stocks unchanged (atomic consistency)
        with pytest.raises(StockUpdateError):
            restock_inventory(
                [
                    {"product_id": p1_id, "quantity": 5},
                    {"product_id": 999999, "quantity": 10},
                ],
                product_model=Product,
            )

        assert db.session.get(Product, p1_id).stock == 10
        assert db.session.get(Product, p2_id).stock == 10


def test_restock_route_updates_stock_successfully(app, client):
    with app.app_context():
        product = add_product("USB Mouse", "12.00", 4)
        product_id = product.id

    response = client.post(
        f"/products/{product_id}/restock",
        data={"quantity": "8", "reference": "SHIPMENT-101"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Stock updated successfully." in response.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 12


def test_restock_route_rejects_invalid_quantity(app, client):
    with app.app_context():
        product = add_product("USB Mouse", "12.00", 4)
        product_id = product.id

    response = client.post(
        f"/products/{product_id}/restock",
        data={"quantity": "-5"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"greater than zero" in response.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 4


def test_return_route_updates_stock_and_blocks_duplicate(app, client):
    with app.app_context():
        product = add_product("Desk Lamp", "45.00", 3)
        product_id = product.id

    # First return via route succeeds
    res1 = client.post(
        "/returns",
        data={
            "product_id": str(product_id),
            "quantity": "2",
            "return_id": "WEB-RET-01",
        },
        follow_redirects=True,
    )
    assert res1.status_code == 200
    assert b"Return processed successfully" in res1.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 5

    # Second return via route with duplicate return_id is blocked
    res2 = client.post(
        "/returns",
        data={
            "product_id": str(product_id),
            "quantity": "2",
            "return_id": "WEB-RET-01",
        },
        follow_redirects=True,
    )
    assert res2.status_code == 200
    assert b"already been processed" in res2.data

    with app.app_context():
        assert db.session.get(Product, product_id).stock == 5
