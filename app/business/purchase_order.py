from decimal import Decimal

from app.data.extensions import db
from app.data.models import Product, PurchaseOrder, PurchaseOrderItem, Supplier


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
