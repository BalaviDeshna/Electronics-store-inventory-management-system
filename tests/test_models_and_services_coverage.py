import pytest
from decimal import Decimal
from unittest.mock import patch
from app.data.extensions import db
from app.data.models import Product, Supplier, PurchaseOrder, PurchaseOrderItem, Sale, SaleItem
from app.business.sales import money, create_sale, SaleValidationError
from app.business.stock import (
    restock_product,
    restock_inventory,
    process_return,
    _validate_positive_int,
    StockUpdateError,
)
from app.business.security import hash_password, verify_password


def test_models_purchase_order_coverage(app):
    with app.app_context():
        s = Supplier(name="PO Model Sup", contact_info="Contact")
        p = Product(name="PO Model Prod", price=Decimal("15.50"), stock=10, supplier=s)
        db.session.add_all([s, p])
        db.session.commit()

        po = PurchaseOrder(supplier_id=s.id, status="Pending")
        assert repr(po).startswith("<PurchaseOrder")

        # update_status_from_items with no items -> line 61
        po.update_status_from_items()
        assert po.status == "Pending"

        item = PurchaseOrderItem(purchase_order=po, product=p, product_id=p.id, quantity=5, received_quantity=0)
        db.session.add(item)
        db.session.commit()

        # line 67
        po.update_status_from_items()
        assert po.status == "Pending"

        # line_total with product -> line 150
        assert item.line_total == Decimal("77.50")

        # line_total without product -> line 151
        item_no_prod = PurchaseOrderItem(purchase_order=po, product_id=99999, quantity=2)
        assert item_no_prod.line_total == Decimal("0.00")

        # repr(item) -> line 167
        assert repr(item).startswith("<PurchaseOrderItem")

        # is_fully_received -> line 143
        assert item.is_fully_received is False
        item.received_quantity = 5
        assert item.is_fully_received is True

        # mark_as_received -> lines 73-75
        po.mark_as_received()
        assert po.status == "Received"
        assert item.received_quantity == 5


def test_models_product_coverage():
    p = Product(name="P", price=Decimal("10.00"), stock=5, reorder_threshold=None)
    # line 36: reorder_threshold is None
    assert p.is_below_reorder_threshold is False

    # line 51: stock is None
    p2 = Product(name="P2", price=Decimal("10.00"), stock=None, reorder_threshold=8)
    assert p2.suggested_reorder_quantity == 8


def test_business_sales_coverage(app):
    # money validation
    with pytest.raises(SaleValidationError, match="Invalid monetary amount"):
        money("invalid_decimal")
    with pytest.raises(SaleValidationError, match="Monetary amount must be finite"):
        money(Decimal("NaN"))
    with pytest.raises(SaleValidationError, match="Monetary amount must be finite"):
        money(Decimal("Infinity"))

    with app.app_context():
        p = Product(name="Sales Test Prod", price=Decimal("20.00"), stock=5)
        db.session.add(p)
        db.session.commit()
        pid = p.id

        # Product ID must be an integer -> line 70
        with pytest.raises(SaleValidationError, match="Each item needs a valid integer"):
            create_sale([{"product_id": "not_an_int", "quantity": 1}], Product)

        # Product does not exist -> line 106
        with pytest.raises(SaleValidationError, match="does not exist"):
            create_sale([{"product_id": 99999, "quantity": 1}], Product)

        # Insufficient stock -> line 124
        with pytest.raises(SaleValidationError, match="Insufficient stock"):
            create_sale([{"product_id": pid, "quantity": 10}], Product)

        # dialect name != sqlite -> line 95
        with patch.object(db.engine.dialect, "name", "postgresql"):
            sale = create_sale([{"product_id": pid, "quantity": 2}], Product)
            assert sale.id is not None
            assert p.stock == 3


def test_business_stock_coverage(app):
    # _validate_positive_int with boolean -> line 21
    with pytest.raises(ValueError):
        _validate_positive_int(True)
    with pytest.raises(ValueError):
        _validate_positive_int(False)

    with app.app_context():
        p = Product(name="Stock Prod", price=Decimal("10.00"), stock=5)
        db.session.add(p)
        db.session.commit()
        pid = p.id

        # restock_product with product_model=None and dialect != sqlite -> lines 35, 43
        with patch.object(db.engine.dialect, "name", "postgresql"):
            p_res = restock_product(pid, 3, product_model=None)
            assert p_res.stock == 8

        # restock_inventory empty list -> line 70
        with pytest.raises(StockUpdateError, match="Restock list cannot be empty"):
            restock_inventory([])

        # restock_inventory invalid item dict -> lines 73, 80-81
        with pytest.raises(StockUpdateError):
            restock_inventory([None])

        # restock_inventory with dialect != sqlite -> line 91
        with patch.object(db.engine.dialect, "name", "postgresql"):
            p_res2 = restock_inventory([{"product_id": pid, "quantity": 2}], product_model=None)
            assert p.stock == 10

        # Create a sale for return tests
        s = Sale(total_amount=Decimal("30.00"))
        db.session.add(s)
        db.session.flush()
        item = SaleItem(sale_id=s.id, product_id=pid, product_name=p.name, quantity=3, unit_price=Decimal("10.00"), line_total=Decimal("30.00"))
        db.session.add(item)
        db.session.commit()
        item_id = item.id

        # process_return empty return_id -> line 128
        with pytest.raises(StockUpdateError, match="Return ID cannot be empty"):
            process_return(return_id="   ", sale_item_id=item_id)

        # process_return sale_item not found -> line 149
        with pytest.raises(StockUpdateError, match="does not exist"):
            process_return(sale_item_id=99999)

        # process_return empty quantity for product_id return -> line 204
        with pytest.raises(StockUpdateError, match="Return quantity must be provided"):
            process_return(product_id=pid, quantity=None)

        # process_return sale_id without sale_item_id -> line 211
        with pytest.raises(StockUpdateError, match="sale item ID is required"):
            process_return(product_id=pid, quantity=1, sale_id=123)

        # process_return neither product_id nor sale_item_id -> line 216
        with pytest.raises(StockUpdateError, match="Either product_id or sale_item_id must be provided"):
            process_return(product_id=None, sale_item_id=None)

        # process_return with dialect != sqlite returning 3 items -> lines 223-224
        with patch.object(db.engine.dialect, "name", "postgresql"):
            ret_record = process_return(sale_item_id=item_id, quantity=3)
            assert ret_record.id is not None

        # process_return when already fully returned (quantity is None -> valid_qty <= 0) -> lines 175-177
        with pytest.raises(StockUpdateError, match="has already been completely returned"):
            process_return(sale_item_id=item_id, quantity=None)


def test_business_security_coverage():
    # hash_password TypeError -> line 7
    with pytest.raises(TypeError, match="Password must be a string"):
        hash_password(None)
    with pytest.raises(TypeError, match="Password must be a string"):
        hash_password(12345)

    # verify_password empty password or hash -> lines 26, 29
    assert verify_password(None, "some_hash") is False
    assert verify_password("", "some_hash") is False
    assert verify_password("some_password", None) is False
    assert verify_password("some_password", "") is False
    assert verify_password("some_password", "invalid_bcrypt_hash") is False
