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


def parse_delivery_quantity(raw_val):
    if raw_val is None or isinstance(raw_val, bool):
        raise PurchaseOrderValidationError("Delivered quantity is required.")
    s = str(raw_val).strip()
    if not s:
        raise PurchaseOrderValidationError("Delivered quantity is required.")
    if "." in s or "e" in s.lower() or "E" in s:
        raise PurchaseOrderValidationError(
            "Delivered quantity must be a positive whole number."
        )
    try:
        val = int(s)
        if str(val) != s or val <= 0:
            raise ValueError
        return val
    except (ValueError, TypeError):
        raise PurchaseOrderValidationError(
            "Delivered quantity must be a positive whole number."
        )


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
    Mark a pending or partially received purchase order as received and increase product stock atomically.

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

    if po.status not in ("Pending", "Partially Received"):
        raise PurchaseOrderValidationError(
            f"Cannot receive purchase order with status '{po.status}'."
        )

    if not po.items:
        raise PurchaseOrderValidationError(
            "Purchase order contains no items to receive."
        )

    try:
        # Increase stock only for the remaining pending quantity of each item
        for item in po.items:
            product = db.session.get(product_model, item.product_id)
            if product is None:
                raise PurchaseOrderValidationError(
                    f"Product {item.product_id} does not exist."
                )

            delta = int(item.quantity) - int(item.received_quantity or 0)
            if delta > 0:
                product.stock = int(product.stock) + delta
                item.received_quantity = int(item.quantity)

                # Record restock movement for audit history and reports
                restock_record = ProductRestock(
                    product_id=product.id,
                    quantity=delta,
                    reference=f"PO #{po.id}",
                )
                db.session.add(restock_record)
            else:
                item.received_quantity = int(item.quantity)

        po.status = "Received"

        if commit:
            db.session.commit()

        return po
    except Exception:
        db.session.rollback()
        raise


def record_partial_delivery(
    po_id,
    deliveries,
    po_model=PurchaseOrder,
    product_model=Product,
    commit=True,
):
    """
    Record partial delivery quantities for line items in a purchase order.
    Increases product stock only by the newly delivered quantities.
    Updates the purchase order status to 'Partially Received' or 'Received'.

    Raises:
        PurchaseOrderValidationError: on invalid PO, negative/zero/excessive quantities, or non-matching items.
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

    if po.status not in ("Pending", "Partially Received"):
        raise PurchaseOrderValidationError(
            f"Cannot record delivery for purchase order with status '{po.status}'."
        )

    if not po.items:
        raise PurchaseOrderValidationError(
            "Purchase order contains no items to receive."
        )

    if not deliveries:
        raise PurchaseOrderValidationError("No delivery quantities provided.")

    if isinstance(deliveries, dict):
        if "deliveries" in deliveries:
            deliveries = deliveries["deliveries"]
        elif "items" in deliveries:
            deliveries = deliveries["items"]
        elif "item_id" in deliveries or "product_id" in deliveries:
            deliveries = [deliveries]
        else:
            deliveries = [{"item_id": k, "quantity": v} for k, v in deliveries.items()]

    if not isinstance(deliveries, (list, tuple)) or not deliveries:
        raise PurchaseOrderValidationError("No delivery quantities provided.")

    # Build lookup maps for po.items
    items_by_id = {item.id: item for item in po.items if item.id is not None}
    items_by_product_id = {item.product_id: item for item in po.items}

    delivered_by_item = {}

    for entry in deliveries:
        if isinstance(entry, dict):
            raw_item_id = entry.get("item_id")
            raw_product_id = entry.get("product_id")
            raw_qty = (
                entry.get("quantity")
                if "quantity" in entry
                else entry.get("delivered_quantity")
            )
        elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
            raw_item_id, raw_qty = entry[0], entry[1]
            raw_product_id = None
        else:
            raise PurchaseOrderValidationError("Invalid delivery item format.")

        qty = parse_delivery_quantity(raw_qty)

        # Match to purchase order item
        matched_item = None
        if raw_item_id is not None:
            try:
                iid = int(str(raw_item_id).strip())
                matched_item = items_by_id.get(iid)
                if matched_item is None and iid in items_by_product_id:
                    matched_item = items_by_product_id[iid]
            except (ValueError, TypeError):
                pass

        if matched_item is None and raw_product_id is not None:
            try:
                pid = int(str(raw_product_id).strip())
                matched_item = items_by_product_id.get(pid)
            except (ValueError, TypeError):
                pass

        if matched_item is None:
            target_id = raw_item_id if raw_item_id is not None else raw_product_id
            raise PurchaseOrderValidationError(
                f"Line item '{target_id}' does not belong to purchase order #{po.id}."
            )

        delivered_by_item[matched_item.id] = (
            delivered_by_item.get(matched_item.id, 0) + qty
        )

    if not delivered_by_item:
        raise PurchaseOrderValidationError("No delivery quantities provided.")

    # Validate against pending quantities
    for item_id, delivery_qty in delivered_by_item.items():
        item = items_by_id[item_id]
        current_received = int(item.received_quantity or 0)
        pending = int(item.quantity) - current_received
        prod_name = (
            item.product.name
            if item.product
            else item.product_name or f"Product #{item.product_id}"
        )

        if pending <= 0:
            raise PurchaseOrderValidationError(
                f"Product '{prod_name}' has already been fully received."
            )

        if delivery_qty > pending:
            raise PurchaseOrderValidationError(
                f"Delivered quantity ({delivery_qty}) exceeds pending quantity ({pending}) for '{prod_name}'. Cumulative received quantity cannot exceed ordered quantity."
            )

    try:
        for item_id, delivery_qty in delivered_by_item.items():
            item = items_by_id[item_id]
            product = db.session.get(product_model, item.product_id)
            if product is None:
                raise PurchaseOrderValidationError(
                    f"Product {item.product_id} does not exist."
                )

            product.stock = int(product.stock) + delivery_qty
            item.received_quantity = int(item.received_quantity or 0) + delivery_qty

            restock_record = ProductRestock(
                product_id=product.id,
                quantity=delivery_qty,
                reference=f"PO #{po.id}",
            )
            db.session.add(restock_record)

        po.update_status_from_items()

        if commit:
            db.session.commit()

        return po
    except Exception:
        db.session.rollback()
        raise


def create_purchase_order_from_low_stock(
    product_id,
    quantity=None,
    supplier_id=None,
    allow_duplicate=False,
    product_model=Product,
    supplier_model=Supplier,
    po_model=PurchaseOrder,
    po_item_model=PurchaseOrderItem,
    commit=True,
):
    """
    Create a purchase order directly from an active low-stock alert for a product.

    - Validates that the product exists.
    - Validates that the product is currently below its reorder threshold (rejects stale alerts).
    - Identifies the assigned supplier (from product.supplier_id or explicit supplier_id).
    - Rejects products with no suitable supplier.
    - Determines suggested order quantity based on threshold deficit (threshold - stock) or user override.
    - Prevents accidental duplicate pending purchase orders for the same product unless allow_duplicate=True.
    - Reuses create_purchase_order() to ensure consistency and atomic transaction behavior.
    """
    if product_id is None or isinstance(product_id, bool):
        raise PurchaseOrderValidationError("Product ID is required.")
    try:
        valid_pid = int(str(product_id).strip())
        if valid_pid <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise PurchaseOrderValidationError("Invalid product ID.")

    product = db.session.get(product_model, valid_pid)
    if product is None:
        raise PurchaseOrderValidationError(f"Product with ID {valid_pid} does not exist.")

    # Validate active low-stock condition (handling stale alerts)
    threshold = getattr(product, "reorder_threshold", 0) or 0
    stock = getattr(product, "stock", 0) or 0
    is_low = getattr(product, "is_below_reorder_threshold", False) or (
        threshold > 0 and stock < threshold
    )
    if not is_low:
        raise PurchaseOrderValidationError(
            f"Product '{product.name}' is not currently below its reorder threshold."
        )

    # Determine supplier
    target_supplier_id = None
    if supplier_id is not None:
        try:
            target_supplier_id = parse_supplier_id(supplier_id)
        except PurchaseOrderValidationError:
            raise PurchaseOrderValidationError("Selected supplier does not exist.")
    elif getattr(product, "supplier_id", None):
        target_supplier_id = product.supplier_id

    if not target_supplier_id:
        raise PurchaseOrderValidationError(
            f"Product '{product.name}' has no assigned supplier. Please assign a supplier before creating a purchase order."
        )

    supplier = db.session.get(supplier_model, target_supplier_id)
    if supplier is None:
        raise PurchaseOrderValidationError(
            f"Supplier with ID {target_supplier_id} does not exist."
        )

    # Determine order quantity
    if quantity is not None and str(quantity).strip() != "":
        order_qty = parse_quantity(quantity)
    else:
        order_qty = getattr(
            product, "suggested_reorder_quantity", max(1, threshold - stock)
        )
        if order_qty <= 0:
            order_qty = max(1, threshold - stock)

    # Prevent accidental duplicate pending purchase orders for the same product
    if not allow_duplicate:
        existing_item = (
            db.session.query(po_item_model)
            .join(po_model, po_item_model.purchase_order_id == po_model.id)
            .filter(
                po_item_model.product_id == product.id,
                po_model.status.in_(["Pending", "Partially Received"]),
            )
            .first()
        )
        if existing_item is not None:
            existing_po = existing_item.purchase_order
            raise PurchaseOrderValidationError(
                f"A pending purchase order (#{existing_po.id}) already exists for product '{product.name}'."
            )

    items = [{"product_id": product.id, "quantity": order_qty}]

    return create_purchase_order(
        supplier_id=supplier.id,
        items=items,
        status="Pending",
        supplier_model=supplier_model,
        product_model=product_model,
        po_model=po_model,
        po_item_model=po_item_model,
        commit=commit,
    )
