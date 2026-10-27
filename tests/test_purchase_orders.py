from decimal import Decimal
import pytest

from app.business.purchase_order import (
    PurchaseOrderValidationError,
    create_purchase_order,
    create_purchase_order_from_low_stock,
    receive_purchase_order,
    record_partial_delivery,
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


# ==========================================
# 5. US-21: Partial Purchase Order Deliveries Tests
# ==========================================


def test_partial_delivery_single_product_business_logic(app):
    with app.app_context():
        supplier = Supplier(name="Delta Electronics")
        product = Product(name="Smart Watch", price=Decimal("199.99"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 15}],
        )
        assert po.status == "Pending"
        assert product.stock == 10

        # Deliver 5 units out of 15
        updated_po = record_partial_delivery(
            po.id,
            [{"product_id": product.id, "quantity": 5}],
        )

        assert updated_po.status == "Partially Received"
        assert updated_po.items[0].quantity == 15
        assert updated_po.items[0].received_quantity == 5
        assert updated_po.items[0].pending_quantity == 10
        assert updated_po.total_received_quantity == 5
        assert updated_po.total_pending_quantity == 10

        # Stock must increase ONLY by delivered quantity (10 + 5 = 15)
        reloaded_product = db.session.get(Product, product.id)
        assert reloaded_product.stock == 15

        # Restock audit entry created
        restock = ProductRestock.query.filter_by(product_id=product.id).first()
        assert restock is not None
        assert restock.quantity == 5
        assert f"PO #{po.id}" in restock.reference


def test_partial_delivery_multi_product_business_logic(app):
    with app.app_context():
        supplier = Supplier(name="Multi Distro")
        p1 = Product(name="Item 1", price=Decimal("10.00"), stock=20)
        p2 = Product(name="Item 2", price=Decimal("20.00"), stock=30)
        db.session.add_all([supplier, p1, p2])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[
                {"product_id": p1.id, "quantity": 10},
                {"product_id": p2.id, "quantity": 20},
            ],
        )

        # Deliver 4 of P1 and 12 of P2
        record_partial_delivery(
            po.id,
            [
                {"product_id": p1.id, "quantity": 4},
                {"product_id": p2.id, "quantity": 12},
            ],
        )

        assert db.session.get(Product, p1.id).stock == 24  # 20 + 4
        assert db.session.get(Product, p2.id).stock == 42  # 30 + 12
        assert po.status == "Partially Received"

        item1 = next(it for it in po.items if it.product_id == p1.id)
        item2 = next(it for it in po.items if it.product_id == p2.id)
        assert item1.received_quantity == 4
        assert item1.pending_quantity == 6
        assert item2.received_quantity == 12
        assert item2.pending_quantity == 8


def test_multiple_partial_deliveries_fulfill_order(app):
    with app.app_context():
        supplier = Supplier(name="Step Supplier")
        product = Product(name="Step Item", price=Decimal("15.00"), stock=50)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        # 1st delivery: 3
        record_partial_delivery(po.id, [{"product_id": product.id, "quantity": 3}])
        assert db.session.get(Product, product.id).stock == 53
        assert po.status == "Partially Received"
        assert po.items[0].received_quantity == 3
        assert po.items[0].pending_quantity == 7

        # 2nd delivery: 4
        record_partial_delivery(po.id, [{"product_id": product.id, "quantity": 4}])
        assert db.session.get(Product, product.id).stock == 57
        assert po.status == "Partially Received"
        assert po.items[0].received_quantity == 7
        assert po.items[0].pending_quantity == 3

        # 3rd delivery: 3 (fulfills entire order)
        record_partial_delivery(po.id, [{"product_id": product.id, "quantity": 3}])
        assert db.session.get(Product, product.id).stock == 60
        assert po.status == "Received"
        assert po.items[0].received_quantity == 10
        assert po.items[0].pending_quantity == 0

        # Further delivery rejected because PO is now Received
        with pytest.raises(
            PurchaseOrderValidationError, match="already been received"
        ):
            record_partial_delivery(
                po.id, [{"product_id": product.id, "quantity": 1}]
            )

        # Stock remains 60
        assert db.session.get(Product, product.id).stock == 60


def test_full_receipt_after_partial_delivery_does_not_double_count(app):
    with app.app_context():
        supplier = Supplier(name="Hybrid Supplier")
        product = Product(name="Hybrid Item", price=Decimal("25.00"), stock=100)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 20}],
        )

        # Deliver 8 units partially
        record_partial_delivery(po.id, [{"product_id": product.id, "quantity": 8}])
        assert db.session.get(Product, product.id).stock == 108
        assert po.status == "Partially Received"

        # Now perform full receive on the partially-delivered PO
        receive_purchase_order(po.id)

        # Stock must increase only by the remaining 12 units (108 + 12 = 120)
        assert db.session.get(Product, product.id).stock == 120
        assert po.status == "Received"
        assert po.items[0].received_quantity == 20
        assert po.items[0].pending_quantity == 0

        # Two audit restocks: 8 and 12
        restocks = ProductRestock.query.filter_by(product_id=product.id).all()
        assert len(restocks) == 2
        assert {r.quantity for r in restocks} == {8, 12}

        # Second full receive attempt fails
        with pytest.raises(
            PurchaseOrderValidationError, match="already been received"
        ):
            receive_purchase_order(po.id)

        assert db.session.get(Product, product.id).stock == 120


def test_partial_delivery_rejects_zero_quantity(app):
    with app.app_context():
        supplier = Supplier(name="Zero Supplier")
        product = Product(name="Zero Item", price=Decimal("10.00"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        with pytest.raises(
            PurchaseOrderValidationError, match="positive whole number"
        ):
            record_partial_delivery(
                po.id, [{"product_id": product.id, "quantity": 0}]
            )

        assert db.session.get(Product, product.id).stock == 10
        assert po.status == "Pending"


def test_partial_delivery_rejects_negative_quantity(app):
    with app.app_context():
        supplier = Supplier(name="Negative Supplier")
        product = Product(name="Negative Item", price=Decimal("10.00"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        with pytest.raises(
            PurchaseOrderValidationError, match="positive whole number"
        ):
            record_partial_delivery(
                po.id, [{"product_id": product.id, "quantity": -3}]
            )

        assert db.session.get(Product, product.id).stock == 10


def test_partial_delivery_rejects_malformed_quantity(app):
    with app.app_context():
        supplier = Supplier(name="Malformed Supplier")
        product = Product(name="Malformed Item", price=Decimal("10.00"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        for malformed in ["abc", "2.5", "", None, True]:
            with pytest.raises(PurchaseOrderValidationError):
                record_partial_delivery(
                    po.id, [{"product_id": product.id, "quantity": malformed}]
                )

        assert db.session.get(Product, product.id).stock == 10


def test_partial_delivery_rejects_over_delivery(app):
    with app.app_context():
        supplier = Supplier(name="Over Delivery Supplier")
        product = Product(name="Over Item", price=Decimal("10.00"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        # Deliver 6 first
        record_partial_delivery(po.id, [{"product_id": product.id, "quantity": 6}])
        assert db.session.get(Product, product.id).stock == 16

        # Attempt to deliver 5 (pending is 4) -> must fail!
        with pytest.raises(
            PurchaseOrderValidationError, match="exceeds pending quantity"
        ):
            record_partial_delivery(
                po.id, [{"product_id": product.id, "quantity": 5}]
            )

        # Stock must not have increased
        assert db.session.get(Product, product.id).stock == 16
        assert po.items[0].received_quantity == 6


def test_partial_delivery_rejects_duplicate_submission_preventing_double_stock(app):
    with app.app_context():
        supplier = Supplier(name="Dupe Deliver Supplier")
        product = Product(name="Dupe Item", price=Decimal("10.00"), stock=10)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 8}],
        )

        # First delivery of 5
        record_partial_delivery(po.id, [{"product_id": product.id, "quantity": 5}])
        assert db.session.get(Product, product.id).stock == 15

        # Duplicate delivery of 5 would exceed pending 3 -> rejected!
        with pytest.raises(
            PurchaseOrderValidationError, match="exceeds pending quantity"
        ):
            record_partial_delivery(
                po.id, [{"product_id": product.id, "quantity": 5}]
            )

        assert db.session.get(Product, product.id).stock == 15


def test_partial_delivery_rejects_line_item_not_in_purchase_order(app):
    with app.app_context():
        supplier = Supplier(name="Wrong Item Supplier")
        p1 = Product(name="In PO", price=Decimal("10.00"), stock=10)
        p2 = Product(name="Not In PO", price=Decimal("20.00"), stock=10)
        db.session.add_all([supplier, p1, p2])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": p1.id, "quantity": 5}],
        )

        with pytest.raises(
            PurchaseOrderValidationError, match="does not belong to purchase order"
        ):
            record_partial_delivery(
                po.id, [{"product_id": p2.id, "quantity": 2}]
            )


def test_partial_delivery_rejects_nonexistent_purchase_order(app):
    with app.app_context():
        with pytest.raises(
            PurchaseOrderValidationError, match="does not exist"
        ):
            record_partial_delivery(
                999999, [{"product_id": 1, "quantity": 5}]
            )


def test_partial_delivery_database_failure_rolls_back(app, monkeypatch):
    with app.app_context():
        supplier = Supplier(name="Rollback Supplier")
        product = Product(name="Rollback Item", price=Decimal("15.00"), stock=25)
        db.session.add_all([supplier, product])
        db.session.commit()

        po = create_purchase_order(
            supplier_id=supplier.id,
            items=[{"product_id": product.id, "quantity": 10}],
        )

        def mock_commit():
            raise Exception("Database failure during partial delivery commit")

        monkeypatch.setattr(db.session, "commit", mock_commit)

        with pytest.raises(Exception, match="Database failure"):
            record_partial_delivery(
                po.id, [{"product_id": product.id, "quantity": 5}]
            )

        monkeypatch.undo()

        # Stock and received quantity must be rolled back!
        assert db.session.get(Product, product.id).stock == 25
        reloaded_po = db.session.get(PurchaseOrder, po.id)
        assert reloaded_po.status == "Pending"
        assert reloaded_po.items[0].received_quantity == 0


def test_partial_delivery_requires_authentication(client):
    response = client.post("/purchase-orders/1/partial-receive")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_staff_cannot_record_partial_delivery(client, logged_in_staff):
    supplier = Supplier(name="Staff Partial Supplier")
    product = Product(name="Staff Partial Product", price=Decimal("20.00"), stock=10)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 10}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/partial-receive",
        data={"item_id": po.items[0].id, "delivered_quantity": 4},
    )
    assert response.status_code == 403

    # Stock and status untouched
    assert db.session.get(Product, product.id).stock == 10
    assert db.session.get(PurchaseOrder, po.id).status == "Pending"


def test_manager_can_record_partial_delivery_via_http(client, logged_in_manager):
    supplier = Supplier(name="Manager Partial Supplier")
    product = Product(name="Manager Partial Product", price=Decimal("30.00"), stock=5)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 15}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/partial-receive",
        data={"item_id": po.items[0].id, "delivered_quantity": 6},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Delivery recorded successfully" in response.data
    assert b"Partially Received" in response.data

    # Stock increased by 6 (5 + 6 = 11)
    assert db.session.get(Product, product.id).stock == 11
    assert db.session.get(PurchaseOrder, po.id).status == "Partially Received"


def test_admin_can_record_partial_delivery_via_http(client, logged_in_admin):
    supplier = Supplier(name="Admin Partial Supplier")
    product = Product(name="Admin Partial Product", price=Decimal("40.00"), stock=20)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 12}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/record-delivery",
        data={"item_id": po.items[0].id, "delivered_quantity": 5},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Delivery recorded successfully" in response.data
    assert db.session.get(Product, product.id).stock == 25
    assert db.session.get(PurchaseOrder, po.id).status == "Partially Received"


def test_partial_delivery_via_json_api(client, logged_in_manager):
    supplier = Supplier(name="JSON Partial Supplier")
    product = Product(name="JSON Item", price=Decimal("50.00"), stock=15)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 20}],
    )

    response = client.post(
        f"/purchase-orders/{po.id}/partial-receive",
        json={"deliveries": [{"product_id": product.id, "quantity": 7}]},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["purchase_order"]["status"] == "Partially Received"
    assert data["purchase_order"]["total_received_quantity"] == 7
    assert data["purchase_order"]["total_pending_quantity"] == 13
    assert db.session.get(Product, product.id).stock == 22


def test_partial_delivery_rejects_invalid_inputs_via_http(client, logged_in_manager):
    supplier = Supplier(name="Invalid Input Supplier")
    product = Product(name="Invalid Input Item", price=Decimal("15.00"), stock=10)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 10}],
    )

    # Negative quantity
    res_neg = client.post(
        f"/purchase-orders/{po.id}/partial-receive",
        data={"item_id": po.items[0].id, "delivered_quantity": -2},
        follow_redirects=True,
    )
    assert res_neg.status_code == 200
    assert b"positive whole number" in res_neg.data

    # Over delivery
    res_over = client.post(
        f"/purchase-orders/{po.id}/partial-receive",
        data={"item_id": po.items[0].id, "delivered_quantity": 25},
        follow_redirects=True,
    )
    assert res_over.status_code == 200
    assert b"exceeds pending quantity" in res_over.data

    # Nonexistent PO -> 404
    res_404 = client.post(
        "/purchase-orders/999999/partial-receive",
        data={"item_id": 1, "delivered_quantity": 5},
    )
    assert res_404.status_code == 404


def test_purchase_order_view_renders_pending_quantities_and_delivery_form(
    client, logged_in_manager
):
    supplier = Supplier(name="Render Supplier")
    product = Product(name="Render Item", price=Decimal("12.50"), stock=8)
    db.session.add_all([supplier, product])
    db.session.commit()

    po = create_purchase_order(
        supplier_id=supplier.id,
        items=[{"product_id": product.id, "quantity": 10}],
    )

    # Initial view
    res = client.get(f"/purchase-orders/{po.id}")
    assert res.status_code == 200
    assert b"Quantity Pending" in res.data
    assert b"Record Delivery" in res.data

    # Partial delivery of 4
    client.post(
        f"/purchase-orders/{po.id}/partial-receive",
        data={"item_id": po.items[0].id, "delivered_quantity": 4},
    )

    res_after = client.get(f"/purchase-orders/{po.id}")
    assert res_after.status_code == 200
    assert b"Partially Received" in res_after.data
    assert b"4" in res_after.data  # Received qty
    assert b"6" in res_after.data  # Pending qty


# ==========================================
# 6. US-24: Create Purchase Orders Directly from Low-Stock Alerts Tests
# ==========================================


def test_create_po_from_low_stock_business_logic_success(app):
    with app.app_context():
        supplier = Supplier(name="Prime Supply Co", contact_info="orders@prime.com")
        product = Product(
            name="Mechanical Keyboard",
            price=Decimal("79.99"),
            stock=2,
            reorder_threshold=10,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        assert product.is_low_stock is True
        assert product.suggested_reorder_quantity == 8  # 10 - 2

        po = create_purchase_order_from_low_stock(product.id)

        assert po is not None
        assert po.id is not None
        assert po.supplier_id == supplier.id
        assert po.status == "Pending"
        assert len(po.items) == 1
        assert po.items[0].product_id == product.id
        assert po.items[0].quantity == 8
        assert po.items[0].unit_price == Decimal("79.99")
        assert po.items[0].received_quantity == 0

        # CRITICAL: Stock must NOT have changed when initiating the PO!
        reloaded = db.session.get(Product, product.id)
        assert reloaded.stock == 2


def test_create_po_from_low_stock_explicit_quantity_override(app):
    with app.app_context():
        supplier = Supplier(name="Fast Electro")
        product = Product(
            name="Gaming Headset",
            price=Decimal("59.99"),
            stock=1,
            reorder_threshold=5,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        # Explicitly order 20 units rather than suggested 4
        po = create_purchase_order_from_low_stock(product.id, quantity=20)

        assert po.items[0].quantity == 20
        assert db.session.get(Product, product.id).stock == 1


def test_create_po_from_low_stock_suggested_quantity_when_zero_stock(app):
    with app.app_context():
        supplier = Supplier(name="Zero Stock Supplier")
        product = Product(
            name="USB Flash Drive",
            price=Decimal("12.00"),
            stock=0,
            reorder_threshold=15,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        po = create_purchase_order_from_low_stock(product.id)
        assert po.items[0].quantity == 15  # 15 - 0


def test_create_po_from_low_stock_rejects_product_without_supplier(app):
    with app.app_context():
        product = Product(
            name="Unassigned Drone",
            price=Decimal("299.00"),
            stock=1,
            reorder_threshold=8,
            supplier_id=None,
        )
        db.session.add(product)
        db.session.commit()

        with pytest.raises(
            PurchaseOrderValidationError, match="no assigned supplier"
        ):
            create_purchase_order_from_low_stock(product.id)

        # Confirm no PO was created
        assert PurchaseOrder.query.count() == 0


def test_create_po_from_low_stock_rejects_stale_alert_stock_at_or_above_threshold(
    app,
):
    with app.app_context():
        supplier = Supplier(name="Stale Supplier")
        product = Product(
            name="Laptop Charger",
            price=Decimal("39.99"),
            stock=10,
            reorder_threshold=10,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        assert product.is_low_stock is False

        with pytest.raises(
            PurchaseOrderValidationError,
            match="not currently below its reorder threshold",
        ):
            create_purchase_order_from_low_stock(product.id)

        assert PurchaseOrder.query.count() == 0


def test_create_po_from_low_stock_rejects_unconfigured_threshold_zero(app):
    with app.app_context():
        supplier = Supplier(name="Zero Threshold Supplier")
        product = Product(
            name="Loose Screws",
            price=Decimal("0.50"),
            stock=0,
            reorder_threshold=0,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        with pytest.raises(
            PurchaseOrderValidationError,
            match="not currently below its reorder threshold",
        ):
            create_purchase_order_from_low_stock(product.id)

        assert PurchaseOrder.query.count() == 0


def test_create_po_from_low_stock_rejects_nonexistent_product(app):
    with app.app_context():
        with pytest.raises(
            PurchaseOrderValidationError, match="does not exist"
        ):
            create_purchase_order_from_low_stock(999999)


def test_create_po_from_low_stock_prevents_duplicate_pending_order(app):
    with app.app_context():
        supplier = Supplier(name="Dupe Low Stock Supplier")
        product = Product(
            name="HDMI Splitter",
            price=Decimal("19.99"),
            stock=2,
            reorder_threshold=10,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        # First PO creation succeeds
        po1 = create_purchase_order_from_low_stock(product.id)
        assert po1.id is not None
        assert PurchaseOrder.query.count() == 1

        # Second creation attempt while po1 is Pending must be rejected to prevent duplicate ordering
        with pytest.raises(
            PurchaseOrderValidationError, match="already exists"
        ):
            create_purchase_order_from_low_stock(product.id)

        assert PurchaseOrder.query.count() == 1

        # When allow_duplicate=True, another order is allowed
        po2 = create_purchase_order_from_low_stock(
            product.id, allow_duplicate=True
        )
        assert po2.id is not None
        assert PurchaseOrder.query.count() == 2


def test_create_po_from_low_stock_database_failure_rolls_back(app, monkeypatch):
    with app.app_context():
        supplier = Supplier(name="Rollback PO Supplier")
        product = Product(
            name="Rollback Mouse",
            price=Decimal("25.00"),
            stock=1,
            reorder_threshold=6,
        )
        db.session.add_all([supplier, product])
        db.session.commit()

        product.supplier_id = supplier.id
        db.session.commit()

        def mock_commit():
            raise Exception("Simulated DB failure during PO creation commit")

        monkeypatch.setattr(db.session, "commit", mock_commit)

        with pytest.raises(Exception, match="Simulated DB failure"):
            create_purchase_order_from_low_stock(product.id)

        monkeypatch.undo()

        # Verify no purchase order or item records were left behind
        assert PurchaseOrder.query.count() == 0


def test_create_po_from_low_stock_requires_authentication(client):
    response = client.post("/purchase-orders/from-low-stock/1")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_staff_cannot_create_po_from_low_stock(client, logged_in_staff):
    supplier = Supplier(name="Staff PO Supplier")
    product = Product(
        name="Staff PO Product",
        price=Decimal("15.00"),
        stock=2,
        reorder_threshold=10,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    response = client.post(f"/purchase-orders/from-low-stock/{product.id}")
    assert response.status_code == 403
    assert PurchaseOrder.query.count() == 0


def test_manager_creates_po_from_low_stock_via_http(client, logged_in_manager):
    supplier = Supplier(name="Manager Low Stock Supplier")
    product = Product(
        name="Wireless Router",
        price=Decimal("89.99"),
        stock=3,
        reorder_threshold=10,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    response = client.post(
        f"/purchase-orders/from-low-stock/{product.id}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"created successfully" in response.data
    assert b"Purchase Order:" in response.data

    # Verify PO in database
    po = PurchaseOrder.query.first()
    assert po is not None
    assert po.supplier_id == supplier.id
    assert po.items[0].product_id == product.id
    assert po.items[0].quantity == 7  # 10 - 3


def test_admin_creates_po_from_low_stock_via_alternate_endpoint(
    client, logged_in_admin
):
    supplier = Supplier(name="Admin Low Stock Supplier")
    product = Product(
        name="Ethernet Cable 50ft",
        price=Decimal("14.99"),
        stock=1,
        reorder_threshold=8,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    response = client.post(
        f"/products/{product.id}/create-purchase-order",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"created successfully" in response.data
    assert PurchaseOrder.query.count() == 1


def test_create_po_from_low_stock_via_json_api(client, logged_in_manager):
    supplier = Supplier(name="JSON PO Supplier")
    product = Product(
        name="Bluetooth Speaker",
        price=Decimal("49.99"),
        stock=2,
        reorder_threshold=10,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    response = client.post(
        f"/purchase-orders/from-low-stock/{product.id}",
        json={"quantity": 12},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["success"] is True
    assert data["purchase_order"]["status"] == "Pending"
    assert data["purchase_order"]["items"][0]["quantity"] == 12
    assert "purchase_order_url" in data


def test_create_po_from_low_stock_http_handles_no_supplier(
    client, logged_in_manager
):
    product = Product(
        name="Orphan Product",
        price=Decimal("20.00"),
        stock=1,
        reorder_threshold=5,
        supplier_id=None,
    )
    db.session.add(product)
    db.session.commit()

    response = client.post(
        f"/purchase-orders/from-low-stock/{product.id}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"no assigned supplier" in response.data
    assert PurchaseOrder.query.count() == 0


def test_create_po_from_low_stock_http_handles_stale_alert(
    client, logged_in_manager
):
    supplier = Supplier(name="Restocked Supplier")
    product = Product(
        name="Well Stocked Item",
        price=Decimal("10.00"),
        stock=20,
        reorder_threshold=10,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    response = client.post(
        f"/purchase-orders/from-low-stock/{product.id}",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"not currently below its reorder threshold" in response.data
    assert PurchaseOrder.query.count() == 0


def test_create_po_from_low_stock_http_nonexistent_product_returns_404(
    client, logged_in_manager
):
    response = client.post("/purchase-orders/from-low-stock/999999")
    assert response.status_code == 404


def test_created_po_from_low_stock_appears_in_views_and_can_be_received(
    client, logged_in_manager
):
    supplier = Supplier(name="Full Lifecycle Supplier")
    product = Product(
        name="Lifecycle Product",
        price=Decimal("35.00"),
        stock=2,
        reorder_threshold=10,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    # 1. Create PO from low-stock alert
    res_create = client.post(
        f"/purchase-orders/from-low-stock/{product.id}",
        follow_redirects=True,
    )
    assert res_create.status_code == 200
    po = PurchaseOrder.query.first()
    assert po is not None

    # 2. Check it appears in PO list view
    res_list = client.get("/purchase-orders")
    assert res_list.status_code == 200
    assert po.order_number.encode() in res_list.data

    # 3. Check it appears in PO detail view
    res_detail = client.get(f"/purchase-orders/{po.id}")
    assert res_detail.status_code == 200
    assert b"Lifecycle Product" in res_detail.data
    assert b"8" in res_detail.data  # quantity

    # 4. Receive the purchase order
    res_receive = client.post(
        f"/purchase-orders/{po.id}/receive", follow_redirects=True
    )
    assert res_receive.status_code == 200
    assert b"Received" in res_receive.data

    # 5. Product stock must be updated to 10 (2 + 8)
    reloaded = db.session.get(Product, product.id)
    assert reloaded.stock == 10

    # 6. Low stock alert should no longer be active on the dashboard!
    res_dash = client.get("/")
    assert res_dash.status_code == 200
    assert b"Low-Stock Alert:" not in res_dash.data


def test_low_stock_alert_renders_create_purchase_order_action_for_manager(
    client, logged_in_manager
):
    supplier = Supplier(name="Action Supplier")
    product = Product(
        name="Alerted Gadget",
        sku="GADGET-1",
        price=Decimal("29.99"),
        stock=1,
        reorder_threshold=5,
    )
    db.session.add_all([supplier, product])
    db.session.commit()

    product.supplier_id = supplier.id
    db.session.commit()

    # Check dashboard low-stock banner
    res_dash = client.get("/")
    assert res_dash.status_code == 200
    assert b"Low-Stock Alert" in res_dash.data
    assert b"Create Purchase Order" in res_dash.data
    assert f"/purchase-orders/from-low-stock/{product.id}".encode() in res_dash.data

    # Check edit product low-stock banner
    res_edit = client.get(f"/products/{product.id}/edit")
    assert res_edit.status_code == 200
    assert b"Create Purchase Order" in res_edit.data
