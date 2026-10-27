from decimal import Decimal

from app.data.extensions import db
from app.data.models import (
    Product,
    ProductRestock,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
)


class PurchaseOrderValidationError(ValueError):
    """Raised when purchase order validation fails."""

    pass


def parse_supplier_id(raw_val):
    if raw_val is None or isinstance(raw_val, bool):
        raise PurchaseOrderValidationError("Supplier is required.")
    s = str(raw_val).strip()
    if not s:
        raise PurchaseOrderValidationError("Supplier is required.")
    try:
        val = int(s)
        if str(val) != s or val <= 0:
            raise ValueError
        return val
    except (ValueError, TypeError):
        raise PurchaseOrderValidationError("Please select a valid supplier.")


def parse_product_id(raw_val):
    if raw_val is None or isinstance(raw_val, bool):
        raise PurchaseOrderValidationError("Product is required for each line item.")
    s = str(raw_val).strip()
    if not s:
        raise PurchaseOrderValidationError("Product is required for each line item.")
    try:
        val = int(s)
        if str(val) != s or val <= 0:
            raise ValueError
        return val
    except (ValueError, TypeError):
        raise PurchaseOrderValidationError("Please select a valid product.")


def parse_quantity(raw_val):
    if raw_val is None or isinstance(raw_val, bool):
        raise PurchaseOrderValidationError("Quantity is required for each line item.")
    s = str(raw_val).strip()
    if not s:
        raise PurchaseOrderValidationError("Quantity is required for each line item.")
    if "." in s or "e" in s.lower() or "E" in s:
        raise PurchaseOrderValidationError("Quantity must be a positive whole number.")
    try:
        val = int(s)
        if str(val) != s or val <= 0:
            raise ValueError
        return val
    except (ValueError, TypeError):
        raise PurchaseOrderValidationError("Quantity must be a positive whole number.")


def create_purchase_order(
    supplier_id,
    items,
    status="Pending",
    supplier_model=Supplier,
    product_model=Product,
    po_model=PurchaseOrder,
    po_item_model=PurchaseOrderItem,
    commit=True,
):
    """
    Creates a new purchase order for an existing supplier with one or more products.

    items can be a list of dicts:
        [{"product_id": 1, "quantity": 10}, ...]
        or a list of tuples: [(1, 10), ...]

    Strictly validates:
        - supplier exists.
        - items list is non-empty.
        - each product exists.
        - quantities are positive integers.
        - product stock is NOT changed!
    """
    s_id = parse_supplier_id(supplier_id)
    supplier = db.session.get(supplier_model, s_id)
    if supplier is None:
        raise PurchaseOrderValidationError("Selected supplier does not exist.")

    if not items:
        raise PurchaseOrderValidationError(
            "A purchase order must contain at least one product."
        )

    quantities_by_product = {}

    for item in items:
        if isinstance(item, dict):
            raw_pid = item.get("product_id")
            raw_qty = item.get("quantity")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            raw_pid, raw_qty = item[0], item[1]
        else:
            raise PurchaseOrderValidationError(
                "Invalid item format in purchase order."
            )

        pid = parse_product_id(raw_pid)
        qty = parse_quantity(raw_qty)

        product = db.session.get(product_model, pid)
        if product is None:
            raise PurchaseOrderValidationError(
                f"Product with ID {pid} does not exist."
            )

        quantities_by_product[pid] = quantities_by_product.get(pid, 0) + qty

    if not quantities_by_product:
        raise PurchaseOrderValidationError(
            "A purchase order must contain at least one product."
        )

    po = po_model(
        supplier_id=supplier.id,
        status=status or "Pending",
    )

    for pid, qty in quantities_by_product.items():
        product = db.session.get(product_model, pid)
        unit_price = getattr(product, "price", None)
        po_item = po_item_model(
            product_id=pid,
            quantity=qty,
            unit_price=unit_price,
            received_quantity=0,
        )
        po.items.append(po_item)

    db.session.add(po)
    if commit:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

    return po


def receive_purchase_order(
    po_id,
    po_model=PurchaseOrder,
    product_model=Product,
    commit=True,
):
    """
    Mark a pending purchase order as received and increase product stock atomically.

    Raises:
        PurchaseOrderValidationError: if PO is missing, already received, or has invalid data.
    """
    if po_id is None or isinstance(po_id, bool):
        raise PurchaseOrderValidationError("Purchase order ID is required.")
    try:
        valid_id = int(str(po_id).strip())
        if valid_id <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise PurchaseOrderValidationError("Invalid purchase order ID.")

    po = db.session.get(po_model, valid_id)
    if po is None:
        raise PurchaseOrderValidationError(f"Purchase order {valid_id} does not exist.")

    if po.status == "Received":
        raise PurchaseOrderValidationError("Purchase order has already been received.")

    if po.status != "Pending":
        raise PurchaseOrderValidationError(
            f"Cannot receive purchase order with status '{po.status}'."
        )

    if not po.items:
        raise PurchaseOrderValidationError(
            "Purchase order contains no items to receive."
        )

    try:
        # Increase stock for each item in the purchase order
        for item in po.items:
            product = db.session.get(product_model, item.product_id)
            if product is None:
                raise PurchaseOrderValidationError(
                    f"Product {item.product_id} does not exist."
                )

            product.stock = int(product.stock) + int(item.quantity)
            item.received_quantity = int(item.quantity)

            # Record restock movement for audit history and reports
            restock_record = ProductRestock(
                product_id=product.id,
                quantity=item.quantity,
                reference=f"PO #{po.id}",
            )
            db.session.add(restock_record)

        po.status = "Received"

        if commit:
            db.session.commit()

        return po
    except Exception:
        db.session.rollback()
        raise
