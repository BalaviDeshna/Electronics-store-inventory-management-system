import pytest
from decimal import Decimal
from unittest.mock import patch

from app.data.extensions import db
from app.data.models import Product, Supplier, PurchaseOrder, PurchaseOrderItem
from app.business.purchase_order import (
    parse_supplier_id,
    parse_product_id,
    create_purchase_order,
    receive_purchase_order,
    record_partial_delivery,
    create_purchase_order_from_low_stock,
    PurchaseOrderValidationError,
)


def test_business_po_validation_functions():
    with pytest.raises(PurchaseOrderValidationError, match="Supplier is required"):
        parse_supplier_id(None)
    with pytest.raises(PurchaseOrderValidationError, match="Please select a valid supplier"):
        parse_supplier_id("not_an_int")

    with pytest.raises(PurchaseOrderValidationError, match="Product is required"):
        parse_product_id(None)
    with pytest.raises(PurchaseOrderValidationError, match="Product is required"):
        parse_product_id("")
    with pytest.raises(PurchaseOrderValidationError, match="Please select a valid product"):
        parse_product_id("not_an_int")


def test_business_create_po_edge_cases(app):
    with app.app_context():
        s = Supplier(name="PO Sup", contact_info="Contact")
        p = Product(name="PO Prod", price=Decimal("10.00"), stock=5, supplier=s)
        db.session.add_all([s, p])
        db.session.commit()
        sid, pid = s.id, p.id

        # items as list of tuples (pid, qty) -> lines 127-128
        po = create_purchase_order(supplier_id=sid, items=[(pid, 5)])
        assert po.id is not None
        assert len(po.items) == 1

        # invalid item format -> line 130
        with pytest.raises(PurchaseOrderValidationError, match="Invalid item format"):
            create_purchase_order(supplier_id=sid, items=["invalid_item"])

        # non-existent supplier -> line 146
        with pytest.raises(PurchaseOrderValidationError, match="Selected supplier does not exist"):
            create_purchase_order(supplier_id=99999, items=[{"product_id": pid, "quantity": 1}])


def test_business_receive_po_edge_cases(app):
    with app.app_context():
        s = Supplier(name="PO Sup 2", contact_info="Contact")
        p = Product(name="PO Prod 2", price=Decimal("10.00"), stock=5, supplier=s)
        db.session.add_all([s, p])
        db.session.commit()
        sid, pid = s.id, p.id

        po = create_purchase_order(supplier_id=sid, items=[{"product_id": pid, "quantity": 4}])

        with pytest.raises(PurchaseOrderValidationError, match="Purchase order ID is required"):
            receive_purchase_order(None)

        with pytest.raises(PurchaseOrderValidationError, match="Invalid purchase order ID"):
            receive_purchase_order("invalid_id")

        with pytest.raises(PurchaseOrderValidationError, match="does not exist"):
            receive_purchase_order(99999)

        # Receive once -> line 237
        receive_purchase_order(po.id)
        assert po.status == "Received"

        # Already received -> line 211
        with pytest.raises(PurchaseOrderValidationError, match="already been received"):
            receive_purchase_order(po.id)


def test_business_record_partial_delivery_edge_cases(app):
    with app.app_context():
        s = Supplier(name="PO Sup 3", contact_info="Contact")
        p = Product(name="PO Prod 3", price=Decimal("10.00"), stock=5, supplier=s)
        db.session.add_all([s, p])
        db.session.commit()
        sid, pid = s.id, p.id

        po = create_purchase_order(supplier_id=sid, items=[{"product_id": pid, "quantity": 10}])
        item_id = po.items[0].id

        # PO ID checks
        with pytest.raises(PurchaseOrderValidationError, match="Purchase order ID is required"):
            record_partial_delivery(None, [])
        with pytest.raises(PurchaseOrderValidationError, match="Invalid purchase order ID"):
            record_partial_delivery("bad_id", [])
        with pytest.raises(PurchaseOrderValidationError, match="does not exist"):
            record_partial_delivery(99999, [])

        # Empty deliveries -> lines 292, 305
        with pytest.raises(PurchaseOrderValidationError, match="No delivery quantities provided"):
            record_partial_delivery(po.id, deliveries=None)
        with pytest.raises(PurchaseOrderValidationError, match="No delivery quantities provided"):
            record_partial_delivery(po.id, deliveries={})

        # Deliveries as dict formats -> lines 295-302
        po = record_partial_delivery(po.id, deliveries={"deliveries": [{"item_id": item_id, "quantity": 1}]})
        assert po.items[0].received_quantity == 1

        po = record_partial_delivery(po.id, deliveries={"items": [{"item_id": item_id, "quantity": 1}]})
        assert po.items[0].received_quantity == 2

        po = record_partial_delivery(po.id, deliveries={"item_id": item_id, "quantity": 1})
        assert po.items[0].received_quantity == 3

        po = record_partial_delivery(po.id, deliveries={str(item_id): 1})
        assert po.items[0].received_quantity == 4

        # Tuple entry -> lines 322-324
        po = record_partial_delivery(po.id, deliveries=[(item_id, 1)])
        assert po.items[0].received_quantity == 5

        # Invalid entry format -> line 326
        with pytest.raises(PurchaseOrderValidationError, match="Invalid delivery item format"):
            record_partial_delivery(po.id, deliveries=["invalid_format"])

        # String item_id not matching integer -> lines 337-339
        with pytest.raises(PurchaseOrderValidationError, match="does not belong to purchase order"):
            record_partial_delivery(po.id, deliveries=[{"item_id": "not_an_int", "quantity": 1}])

        # String product_id not matching integer -> lines 345-346
        with pytest.raises(PurchaseOrderValidationError, match="does not belong to purchase order"):
            record_partial_delivery(po.id, deliveries=[{"product_id": "not_an_int", "quantity": 1}])

        # Zero quantity -> raises Delivered quantity must be a positive whole number
        with pytest.raises(PurchaseOrderValidationError, match="Delivered quantity must be a positive whole number"):
            record_partial_delivery(po.id, deliveries=[{"item_id": item_id, "quantity": 0}])

        # Item does not belong to PO -> line 373
        with pytest.raises(PurchaseOrderValidationError, match="does not belong to purchase order"):
            record_partial_delivery(po.id, deliveries=[{"item_id": 99999, "quantity": 1}])

        # Deliver remaining 5 items -> status becomes Received
        po = record_partial_delivery(po.id, deliveries=[{"item_id": item_id, "quantity": 5}])
        assert po.status == "Received"

        # Already received -> line 287
        with pytest.raises(PurchaseOrderValidationError, match="already been received"):
            record_partial_delivery(po.id, deliveries=[{"item_id": item_id, "quantity": 1}])


def test_business_create_po_from_low_stock_edge_cases(app):
    with app.app_context():
        s = Supplier(name="PO Sup 4", contact_info="Contact")
        p = Product(name="PO Prod 4", price=Decimal("10.00"), stock=2, reorder_threshold=10, supplier=s)
        db.session.add_all([s, p])
        db.session.commit()
        sid, pid = s.id, p.id

        with pytest.raises(PurchaseOrderValidationError, match="Product ID is required"):
            create_purchase_order_from_low_stock(None)

        with pytest.raises(PurchaseOrderValidationError, match="Invalid product ID"):
            create_purchase_order_from_low_stock("bad")

        with pytest.raises(PurchaseOrderValidationError, match="Selected supplier does not exist"):
            create_purchase_order_from_low_stock(pid, supplier_id="bad_sup")

        # Invalid supplier ID -> line 475
        with pytest.raises(PurchaseOrderValidationError, match="does not exist"):
            create_purchase_order_from_low_stock(pid, supplier_id=99999)

        # Default quantity calculation -> line 487 (threshold 10 - stock 2 = 8)
        with patch.object(Product, "suggested_reorder_quantity", 0):
            po = create_purchase_order_from_low_stock(pid, quantity=None)
            assert po.items[0].quantity == 8


def test_purchase_order_routes_coverage_expansion(app, client, logged_in_admin):
    with app.app_context():
        s = Supplier(name="Route PO Sup", contact_info="Contact")
        p = Product(name="Route PO Prod", price=Decimal("20.00"), stock=2, reorder_threshold=5, supplier=s)
        db.session.add_all([s, p])
        db.session.commit()
        sid, pid = s.id, p.id

    # GET /purchase-orders/new with product_id -> lines 110-116
    r = client.get(f"/purchase-orders/new?product_id={pid}")
    assert r.status_code == 200

    # POST create PO with single string product_id and quantity -> lines 59, 61
    r = client.post("/purchase-orders", data={
        "supplier_id": str(sid),
        "product_id": str(pid),
        "quantity": "3",
    })
    assert r.status_code == 302

    # POST create PO JSON validation error -> line 78
    r = client.post("/purchase-orders", json={"supplier_id": None}, content_type="application/json")
    assert r.status_code == 400
    assert "error" in r.get_json()

    # POST create PO JSON exception rollback -> lines 89-95
    with patch("app.presentation.routes.purchase_order.create_purchase_order", side_effect=RuntimeError("create po fail")):
        r = client.post("/purchase-orders", json={"supplier_id": sid, "items": [{"product_id": pid, "quantity": 1}]}, content_type="application/json")
        assert r.status_code == 500

    # GET /purchase-orders with content_type="application/json" -> line 148
    r = client.get("/purchase-orders", content_type="application/json")
    assert r.status_code == 200
    pos_json = r.get_json()
    assert isinstance(pos_json, list)
    po_id = pos_json[0]["id"]

    # GET /purchase-orders/<id> JSON not found -> line 166
    r = client.get("/purchase-orders/99999", content_type="application/json")
    assert r.status_code == 404

    # GET /purchase-orders/<id> JSON found -> line 170
    r = client.get(f"/purchase-orders/{po_id}", content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["id"] == po_id

    # POST receive PO JSON not found -> line 193
    r = client.post("/purchase-orders/99999/receive", content_type="application/json")
    assert r.status_code == 404

    # POST receive PO JSON validation error -> line 217
    with patch("app.presentation.routes.purchase_order.receive_purchase_order", side_effect=PurchaseOrderValidationError("receive val err")):
        r = client.post(f"/purchase-orders/{po_id}/receive", content_type="application/json")
        assert r.status_code == 400

    # POST receive PO JSON exception -> lines 221-227
    with patch("app.presentation.routes.purchase_order.receive_purchase_order", side_effect=RuntimeError("receive err")):
        r = client.post(f"/purchase-orders/{po_id}/receive", content_type="application/json")
        assert r.status_code == 500

    # GET deliveries JSON not found -> line 255
    r = client.get("/purchase-orders/99999/deliveries", content_type="application/json")
    assert r.status_code == 404

    # GET deliveries JSON found -> line 259-260
    r = client.get(f"/purchase-orders/{po_id}/deliveries", content_type="application/json")
    assert r.status_code == 200

    # GET deliveries HTML -> line 261
    r = client.get(f"/purchase-orders/{po_id}/deliveries")
    assert r.status_code == 200

    # POST deliveries JSON format with items dict -> lines 273-278
    r = client.post(f"/purchase-orders/{po_id}/deliveries", json={"item_id": pos_json[0]["items"][0]["id"], "quantity": 1})
    assert r.status_code == 200

    # POST deliveries form with product_id and quantity lists -> lines 284, 291-295
    r = client.post(f"/purchase-orders/{po_id}/deliveries", data={
        "product_id": [str(pid)],
        "quantity": ["1"],
    })
    assert r.status_code == 302

    # POST deliveries form with item_<id> -> lines 298-305
    item_id = pos_json[0]["items"][0]["id"]
    r = client.post(f"/purchase-orders/{po_id}/deliveries", data={
        f"item_{item_id}": "1",
    })
    assert r.status_code == 302

    # POST deliveries JSON validation error -> line 328
    r = client.post(f"/purchase-orders/{po_id}/deliveries", json={"items": [{"item_id": 99999, "quantity": 1}]})
    assert r.status_code == 400

    # POST deliveries JSON exception -> lines 332-338
    with patch("app.presentation.routes.purchase_order.record_partial_delivery", side_effect=RuntimeError("deliv fail")):
        r = client.post(f"/purchase-orders/{po_id}/deliveries", json={"items": [{"item_id": item_id, "quantity": 1}]})
        assert r.status_code == 500

    # GET low-stock PO JSON not found -> line 356
    r = client.get("/purchase-orders/from-low-stock/99999", content_type="application/json")
    assert r.status_code == 404

    # GET low-stock PO JSON found -> lines 360-361
    r = client.get(f"/purchase-orders/from-low-stock/{pid}", content_type="application/json")
    assert r.status_code == 200

    # POST low-stock PO JSON validation error -> line 430
    r = client.post(f"/purchase-orders/from-low-stock/{pid}", json={"supplier_id": 99999})
    assert r.status_code == 400

    # POST low-stock PO JSON exception -> lines 434-440
    with patch("app.presentation.routes.purchase_order.create_purchase_order_from_low_stock", side_effect=RuntimeError("po low crash")):
        r = client.post(f"/purchase-orders/from-low-stock/{pid}", json={"requested_quantity": 2})
        assert r.status_code == 500
