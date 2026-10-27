from decimal import Decimal
import pytest

from app.business.purchase_order import (
    PurchaseOrderValidationError,
    create_purchase_order,
    receive_purchase_order,
)
from app.data.extensions import db
from app.data.models import Product, ProductRestock, PurchaseOrder, Supplier


# ==========================================
# 1. Model & Business Logic Unit Tests
# ==========================================


def test_create_purchase_order_business_logic_success(app):
    with app.app_context():
        supplier = Supplier(name="Apex Tech Distro", contact_info="orders@apex.com")
        product1 = Product(name="Wireless Mouse", price=Decimal("29.99"), stock=10)
        product2 = Product(name="USB-C Hub", price=Decimal("19.99"), stock=5)
        db.session.add_all([supplier, product1, product2])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[
                {"product_id": product1.id, "quantity": 15},
                {"product_id": product2.id, "quantity": 25},
            ],
        )

        assert po is not None
        assert po.id is not None
        assert po.supplier_id == supplier.id
        assert po.supplier.name == "Apex Tech Distro"
        assert po.status == "Pending"
        assert len(po.items) == 2
        assert po.total_quantity == 40
        assert po.order_number == f"PO-{po.id:04d}"

        # CRITICAL: Verify stock did NOT change!
        reloaded_p1 = db.session.get(Product, product1.id)
        reloaded_p2 = db.session.get(Product, product2.id)
        assert reloaded_p1.stock == 10
        assert reloaded_p2.stock == 5


def test_create_purchase_order_combines_duplicate_products_in_same_order(app):
    with app.app_context():
        supplier = Supplier(name="Global Distro")
        product = Product(name="Keyboard", price=Decimal("50.00"), stock=8)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[
                {"product_id": product.id, "quantity": 10},
                {"product_id": product.id, "quantity": 15},
            ],
        )

        assert len(po.items) == 1
        assert po.items[0].quantity == 25
        assert product.stock == 8


def test_create_purchase_order_rejects_nonexistent_supplier(app):
    with app.app_context():
        product = Product(name="Monitor", price=Decimal("200.00"), stock=5)
        db.session.add(product)
        db.session.commit()

        with pytest.raises(
            PurchaseOrderValidationError, match="Selected supplier does not exist"
        ):
            create_purchase_order(
                supplier_id=999999,
                items=[{"product_id": product.id, "quantity": 5}],
            )


def test_create_purchase_order_rejects_empty_items(app):
    with app.app_context():
        supplier = Supplier(name="Empty Test Supplier")
        db.session.add(supplier)
        db.session.commit()

        with pytest.raises(PurchaseOrderValidationError, match="at least one product"):
            create_purchase_order(
                supplier_id=supplier.id,
                items=[],
            )


def test_create_purchase_order_rejects_nonexistent_product(app):
    with app.app_context():
        supplier = Supplier(name="Tech Supplier")
        db.session.add(supplier)
        db.session.commit()

        with pytest.raises(PurchaseOrderValidationError, match="does not exist"):
            create_purchase_order(
                supplier_id=supplier.id,
                items=[{"product_id": 999999, "quantity": 10}],
            )


@pytest.mark.parametrize(
    "invalid_qty",
    [0, -1, -50, "0", "-5", "abc", "2.5", True, False, None, ""],
)
def test_create_purchase_order_rejects_invalid_quantities(app, invalid_qty):
    with app.app_context():
        supplier = Supplier(name="Valid Supplier")
        product = Product(name="Valid Product", price=Decimal("15.00"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        with pytest.raises(PurchaseOrderValidationError):
            create_purchase_order(
                supplier_id=supplier.id,
                items=[{"product_id": product.id, "quantity": invalid_qty}],
            )


# ==========================================
# 2. Authorization / Access Control Tests
# ==========================================


def test_purchase_order_create_requires_authentication(client):
    response = client.get("/purchase-orders/create")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")

    post_resp = client.post(
        "/purchase-orders/create",
        data={"supplier_id": "1", "product_id": "1", "quantity": "5"},
    )
    assert post_resp.status_code == 302
    assert "/login" in post_resp.headers.get("Location", "")


def test_staff_cannot_create_purchase_order(client, logged_in_staff):
    response = client.get("/purchase-orders/create")
    assert response.status_code == 403

    post_resp = client.post(
        "/purchase-orders/create",
        data={"supplier_id": "1", "product_id": "1", "quantity": "5"},
    )
    assert post_resp.status_code == 403


def test_manager_can_access_create_purchase_order_page(client, logged_in_manager):
    response = client.get("/purchase-orders/create")
    assert response.status_code == 200
    assert b"Create Purchase Order" in response.data


def test_admin_can_access_create_purchase_order_page(client, logged_in_admin):
    response = client.get("/purchase-orders/create")
    assert response.status_code == 200
    assert b"Create Purchase Order" in response.data


# ==========================================
# 3. HTTP Route & Form Workflow Tests
# ==========================================


def test_manager_creates_purchase_order_success(client, logged_in_manager):
    supplier = Supplier(
        name="Direct Hardware Supplies", contact_info="direct@hardware.com"
    )
    product1 = Product(name="DisplayPort Cable", price=Decimal("12.50"), stock=20)
    product2 = Product(name="HDMI 2.1 Cable", price=Decimal("15.00"), stock=30)
    db.session.add_all([supplier, product1, product2])
    db.session.commit()

    initial_stock_p1 = product1.stock
    initial_stock_p2 = product2.stock

    response = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": str(supplier.id),
            "product_id": [str(product1.id), str(product2.id)],
            "quantity": ["50", "75"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Purchase order #" in response.data
    assert b"created successfully" in response.data
    assert b"Direct Hardware Supplies" in response.data
    assert b"Pending" in response.data
    assert b"DisplayPort Cable" in response.data
    assert b"50" in response.data
    assert b"HDMI 2.1 Cable" in response.data
    assert b"75" in response.data

    # Verify PO in database
    po = PurchaseOrder.query.first()
    assert po is not None
    assert po.supplier_id == supplier.id
    assert po.status == "Pending"
    assert len(po.items) == 2

    # Stock must remain completely unchanged!
    reloaded_p1 = db.session.get(Product, product1.id)
    reloaded_p2 = db.session.get(Product, product2.id)
    assert reloaded_p1.stock == initial_stock_p1
    assert reloaded_p2.stock == initial_stock_p2


def test_create_purchase_order_rejects_missing_supplier(client, logged_in_manager):
    product = Product(name="Ethernet Cable", price=Decimal("5.00"), stock=10)
    db.session.add(product)
    db.session.commit()

    response = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": "",
            "product_id": [str(product.id)],
            "quantity": ["10"],
        },
    )

    assert response.status_code == 400
    assert b"Supplier is required." in response.data
    assert PurchaseOrder.query.count() == 0


def test_create_purchase_order_rejects_nonexistent_supplier_http(
    client, logged_in_manager
):
    product = Product(name="USB Adapter", price=Decimal("8.00"), stock=10)
    db.session.add(product)
    db.session.commit()

    response = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": "999999",
            "product_id": [str(product.id)],
            "quantity": ["10"],
        },
    )

    assert response.status_code == 400
    assert b"Selected supplier does not exist." in response.data
    assert PurchaseOrder.query.count() == 0


def test_create_purchase_order_rejects_empty_items_http(client, logged_in_manager):
    supplier = Supplier(name="Supplier Co")
    db.session.add(supplier)
    db.session.commit()

    response = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": str(supplier.id),
        },
    )

    assert response.status_code == 400
    assert b"at least one product" in response.data
    assert PurchaseOrder.query.count() == 0


def test_create_purchase_order_rejects_zero_and_negative_quantities_http(
    client, logged_in_manager
):
    supplier = Supplier(name="Cable Supplier")
    product = Product(name="Power Cord", price=Decimal("10.00"), stock=20)
    db.session.add_all([supplier, product])
    db.session.commit()

    # Zero quantity
    res_zero = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": str(supplier.id),
            "product_id": [str(product.id)],
            "quantity": ["0"],
        },
    )
    assert res_zero.status_code == 400
    assert b"positive whole number" in res_zero.data

    # Negative quantity
    res_neg = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": str(supplier.id),
            "product_id": [str(product.id)],
            "quantity": ["-5"],
        },
    )
    assert res_neg.status_code == 400
    assert b"positive whole number" in res_neg.data

    # Decimal quantity
    res_dec = client.post(
        "/purchase-orders/create",
        data={
            "supplier_id": str(supplier.id),
            "product_id": [str(product.id)],
            "quantity": ["3.5"],
        },
    )
    assert res_dec.status_code == 400
    assert b"positive whole number" in res_dec.data

    assert PurchaseOrder.query.count() == 0


def test_create_purchase_order_via_json(client, logged_in_manager):
    supplier = Supplier(name="JSON Supplier")
    product = Product(name="Microphone", price=Decimal("80.00"), stock=5)
    db.session.add_all([supplier, product])
    db.session.commit()

    response = client.post(
        "/purchase-orders/create",
        json={
            "supplier_id": supplier.id,
            "items": [{"product_id": product.id, "quantity": 12}],
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["purchase_order"]["status"] == "Pending"
    assert data["purchase_order"]["items"][0]["quantity"] == 12
    assert product.stock == 5


def test_purchase_orders_list_page(client, logged_in_manager):
    supplier = Supplier(name="Sound Tech")
    product = Product(name="Speaker", price=Decimal("120.00"), stock=10)
    db.session.add_all([supplier, product])
    db.session.commit()

    create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 20}],
    )

    response = client.get("/purchase-orders")
    assert response.status_code == 200
    assert b"Purchase Orders" in response.data
    assert b"Sound Tech" in response.data
    assert b"Pending" in response.data
    assert b"20" in response.data


def test_view_purchase_order_details(client, logged_in_manager):
    supplier = Supplier(
        name="Display Inc",
        contact_info="rep@display.com",
        address="100 Screen Rd",
    )
    product = Product(
        name="OLED Monitor",
        sku="MON-OLED-27",
        price=Decimal("499.99"),
        stock=3,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 15}],
    )

    response = client.get(f"/purchase-orders/{po.id}")
    assert response.status_code == 200
    assert po.order_number.encode() in response.data
    assert b"Display Inc" in response.data
    assert b"rep@display.com" in response.data
    assert b"100 Screen Rd" in response.data
    assert b"OLED Monitor" in response.data
    assert b"MON-OLED-27" in response.data
    assert b"15" in response.data
    assert b"Pending" in response.data


def test_view_nonexistent_purchase_order_returns_404(client, logged_in_manager):
    response = client.get("/purchase-orders/999999")
    assert response.status_code == 404


# ==========================================
# 4. US-20: Receive Purchase Orders & Update Stock Tests
# ==========================================


def test_receive_purchase_order_business_logic_success(app):
    with app.app_context():
        supplier = Supplier(name="Apex Tech")
        product = Product(name="Gaming Mouse", price=Decimal("49.99"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 15}],
        )
        assert po.status == "Pending"
        assert product.stock == 10

        received_po = receive_purchase_order(po.id)

        assert received_po.status == "Received"
        assert received_po.items[0].received_quantity == 15

        # Product stock must have increased from 10 to 25
        reloaded_product = db.session.get(Product, product.id)
        assert reloaded_product.stock == 25

        # ProductRestock record created for audit trail
        restock = ProductRestock.query.filter_by(product_id=product.id).first()
        assert restock is not None
        assert restock.quantity == 15
        assert restock.reference == f"PO #{po.id}"


def test_receive_purchase_order_multi_product_stock_increase(app):
    with app.app_context():
        supplier = Supplier(name="Mega Supplies")
        p1 = Product(name="Item A", price=Decimal("10.00"), stock=5)
        p2 = Product(name="Item B", price=Decimal("20.00"), stock=12)
        p3 = Product(name="Item C", price=Decimal("30.00"), stock=0)
        db.session.add_all([supplier, p1, p2, p3])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[
                {"product_id": p1.id, "quantity": 20},
                {"product_id": p2.id, "quantity": 10},
                {"product_id": p3.id, "quantity": 35},
            ],
        )

        receive_purchase_order(po.id)

        assert db.session.get(Product, p1.id).stock == 25  # 5 + 20
        assert db.session.get(Product, p2.id).stock == 22  # 12 + 10
        assert db.session.get(Product, p3.id).stock == 35  # 0 + 35
        assert po.status == "Received"


def test_receive_purchase_order_rejects_already_received(app):
    with app.app_context():
        supplier = Supplier(name="Dupe Supplier")
        product = Product(name="Unique Keycap", price=Decimal("15.00"), stock=8)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        receive_purchase_order(po.id)
        assert db.session.get(Product, product.id).stock == 18

        # Second receive attempt must fail
        with pytest.raises(
            PurchaseOrderValidationError, match="already been received"
        ):
            receive_purchase_order(po.id)

        # Stock must NOT have increased a second time
        assert db.session.get(Product, product.id).stock == 18


def test_receive_purchase_order_rejects_nonexistent(app):
    with app.app_context():
        with pytest.raises(
            PurchaseOrderValidationError, match="does not exist"
        ):
            receive_purchase_order(999999)


def test_receive_purchase_order_database_failure_rolls_back(app, monkeypatch):
    with app.app_context():
        supplier = Supplier(name="Rollback Supplier")
        product = Product(name="Rollback Item", price=Decimal("12.00"), stock=20)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 15}],
        )

        def mock_commit():
            raise Exception("Simulated DB failure during receive commit")

        monkeypatch.setattr(db.session, "commit", mock_commit)

        with pytest.raises(Exception, match="Simulated DB failure"):
            receive_purchase_order(po.id)

        monkeypatch.undo()

        # Both stock changes and status update must be rolled back!
        reloaded_po = db.session.get(PurchaseOrder, po.id)
        assert reloaded_po.status == "Pending"
        reloaded_product = db.session.get(Product, product.id)
        assert reloaded_product.stock == 20


def test_receive_purchase_order_requires_authentication(client):
    response = client.post("/purchase-orders/1/receive")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_staff_cannot_receive_purchase_order(client, logged_in_staff):
    supplier = Supplier(name="Staff Test Supplier")
    product = Product(name="Staff Test Product", price=Decimal("20.00"), stock=10)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 10}],
    )

    response = client.post(f"/purchase-orders/{po.id}/receive")
    assert response.status_code == 403

    # Stock must remain unchanged
    assert db.session.get(Product, product.id).stock == 10
    assert db.session.get(PurchaseOrder, po.id).status == "Pending"


def test_manager_can_receive_purchase_order_via_http(client, logged_in_manager):
    supplier = Supplier(name="Manager Supplier")
    product = Product(name="Desk Mat", price=Decimal("25.00"), stock=14)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 20}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/receive",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"marked as received" in response.data
    assert b"Stock updated successfully" in response.data
    assert b"Received" in response.data

    # Product stock increased
    assert db.session.get(Product, product.id).stock == 34
    assert db.session.get(PurchaseOrder, po.id).status == "Received"


def test_admin_can_receive_purchase_order_via_http(client, logged_in_admin):
    supplier = Supplier(name="Admin Supplier")
    product = Product(name="Screen Cleaner", price=Decimal("9.99"), stock=50)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 30}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/receive",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"marked as received" in response.data
    assert db.session.get(Product, product.id).stock == 80
    assert db.session.get(PurchaseOrder, po.id).status == "Received"


def test_receive_nonexistent_purchase_order_returns_404(client, logged_in_manager):
    response = client.post("/purchase-orders/999999/receive")
    assert response.status_code == 404


def test_already_received_purchase_order_cannot_increase_stock_second_time_http(
    client, logged_in_manager
):
    supplier = Supplier(name="Single Supplier")
    product = Product(name="Single Item", price=Decimal("15.00"), stock=10)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 10}],
    )

    # First receive
    res1 = client.post(f"/purchase-orders/{po.id}/receive", follow_redirects=True)
    assert res1.status_code == 200
    assert db.session.get(Product, product.id).stock == 20

    # Second receive attempt
    res2 = client.post(f"/purchase-orders/{po.id}/receive", follow_redirects=True)
    assert res2.status_code == 200
    assert b"already been received" in res2.data

    # Stock remains 20, NOT 30
    assert db.session.get(Product, product.id).stock == 20


def test_receive_purchase_order_via_json(client, logged_in_manager):
    supplier = Supplier(name="API Supplier")
    product = Product(name="API Item", price=Decimal("35.00"), stock=10)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 25}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/receive",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["purchase_order"]["status"] == "Received"
    assert db.session.get(Product, product.id).stock == 35


def test_purchase_order_detail_view_shows_receive_button_when_pending_and_hides_when_received(
    client, logged_in_manager
):
    supplier = Supplier(name="UI Supplier")
    product = Product(name="UI Product", price=Decimal("19.99"), stock=5)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 10}],
    )

    # When pending: button is present
    res_pending = client.get(f"/purchase-orders/{po.id}")
    assert res_pending.status_code == 200
    assert b"Mark as Received" in res_pending.data
    assert f"/purchase-orders/{po.id}/receive".encode() in res_pending.data

    # Receive PO
    client.post(f"/purchase-orders/{po.id}/receive")

    # When received: button is NOT present
    res_received = client.get(f"/purchase-orders/{po.id}")
    assert res_received.status_code == 200
    assert b"Mark as Received" not in res_received.data
    assert b"This purchase order has been marked as Received" in res_received.data
