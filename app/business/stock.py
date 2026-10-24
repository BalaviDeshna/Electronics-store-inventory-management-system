from sqlalchemy import func

from app.data.extensions import db
from app.data.models.product import Product
from app.data.models.sale import SaleItem
from app.data.models.stock import ProductRestock, ProductReturn


class StockUpdateError(ValueError):
    """Raised when an inventory or stock update operation fails validation."""


def _validate_positive_int(value, name="Quantity"):
    if isinstance(value, bool):
        raise StockUpdateError(f"{name} must be a positive integer, not a boolean.")
    try:
        val_str = str(value).strip()
        int_val = int(val_str)
        if str(int_val) != val_str:
            raise ValueError
    except (TypeError, ValueError) as exc:
        raise StockUpdateError(f"{name} must be a valid positive integer.") from exc

    if int_val <= 0:
        raise StockUpdateError(f"{name} must be greater than zero.")
    return int_val


def restock_product(product_id, quantity, reference=None, product_model=None):
    """
    Increase product stock by received quantity atomically.
    """
    if product_model is None:
        product_model = Product

    valid_id = _validate_positive_int(product_id, name="Product ID")
    valid_qty = _validate_positive_int(quantity, name="Restock quantity")

    try:
        query = db.session.query(product_model).filter_by(id=valid_id)
        if db.engine.dialect.name != "sqlite":
            query = query.with_for_update()

        product = query.one_or_none()
        if product is None:
            raise StockUpdateError(f"Product {valid_id} does not exist.")

        product.stock = int(product.stock) + valid_qty

        restock_record = ProductRestock(
            product_id=valid_id,
            quantity=valid_qty,
            reference=str(reference).strip() if reference else None,
        )
        db.session.add(restock_record)
        db.session.commit()
        return product
    except Exception:
        db.session.rollback()
        raise


def restock_inventory(items, product_model=None):
    """
    Batch restock multiple products atomically.
    All items are validated before updating any stock.
    """
    if not items:
        raise StockUpdateError("Restock list cannot be empty.")

    if product_model is None:
        product_model = Product

    quantities = {}
    for item in items:
        try:
            pid = _validate_positive_int(item["product_id"], name="Product ID")
            qty = _validate_positive_int(item["quantity"], name="Restock quantity")
        except (KeyError, TypeError) as exc:
            raise StockUpdateError(
                "Each item requires valid 'product_id' and 'quantity'."
            ) from exc
        quantities[pid] = quantities.get(pid, 0) + qty

    try:
        products = []
        for pid in sorted(quantities):
            query = db.session.query(product_model).filter_by(id=pid)
            if db.engine.dialect.name != "sqlite":
                query = query.with_for_update()
            p = query.one_or_none()
            if p is None:
                raise StockUpdateError(f"Product {pid} does not exist.")
            products.append((p, pid, quantities[pid]))

        for p, pid, qty in products:
            p.stock = int(p.stock) + qty
            db.session.add(ProductRestock(product_id=pid, quantity=qty))

        db.session.commit()
        return [p for p, _, _ in products]
    except Exception:
        db.session.rollback()
        raise


def process_return(
    product_id=None,
    quantity=None,
    sale_item_id=None,
    sale_id=None,
    return_id=None,
    product_model=None,
):
    """
    Process a customer return and increase stock accordingly.
    Prevents duplicate processing and invalid quantities.
    """
    if product_model is None:
        product_model = Product

    clean_return_id = None
    if return_id is not None:
        clean_return_id = str(return_id).strip()
        if not clean_return_id:
            raise StockUpdateError("Return ID cannot be empty.")
        existing = db.session.execute(
            db.select(ProductReturn).filter_by(return_id=clean_return_id)
        ).scalar_one_or_none()
        if existing is not None:
            raise StockUpdateError(
                f"Return '{clean_return_id}' has already been processed."
            )

    sale_item = None
    if sale_item_id is not None:
        valid_sale_item_id = _validate_positive_int(
            sale_item_id, name="Sale item ID"
        )
        sale_item = db.session.get(SaleItem, valid_sale_item_id)
        if sale_item is None:
            raise StockUpdateError(
                f"Sale item {valid_sale_item_id} does not exist."
            )

        target_product_id = sale_item.product_id
        effective_sale_id = sale_id or sale_item.sale_id

        already_returned = (
            db.session.query(
                func.coalesce(func.sum(ProductReturn.quantity), 0)
            )
            .filter(ProductReturn.sale_item_id == valid_sale_item_id)
            .scalar()
        )

        if quantity is None:
            valid_qty = sale_item.quantity - already_returned
            if valid_qty <= 0:
                raise StockUpdateError(
                    f"Sale item {valid_sale_item_id} has already been completely returned."
                )
        else:
            valid_qty = _validate_positive_int(quantity, name="Return quantity")
            if already_returned + valid_qty > sale_item.quantity:
                raise StockUpdateError(
                    f"Cannot return {valid_qty} units. Already returned: {already_returned}, purchased: {sale_item.quantity}."
                )
    elif product_id is not None:
        target_product_id = _validate_positive_int(product_id, name="Product ID")
        if quantity is None:
            raise StockUpdateError("Return quantity must be provided.")
        valid_qty = _validate_positive_int(quantity, name="Return quantity")
        effective_sale_id = (
            _validate_positive_int(sale_id, name="Sale ID") if sale_id else None
        )
        valid_sale_item_id = None
    else:
        raise StockUpdateError(
            "Either product_id or sale_item_id must be provided for a return."
        )

    try:
        query = db.session.query(product_model).filter_by(id=target_product_id)
        if db.engine.dialect.name != "sqlite":
            query = query.with_for_update()

        product = query.one_or_none()
        if product is None:
            raise StockUpdateError(f"Product {target_product_id} does not exist.")

        product.stock = int(product.stock) + valid_qty

        return_record = ProductReturn(
            return_id=clean_return_id,
            sale_id=effective_sale_id,
            sale_item_id=valid_sale_item_id,
            product_id=target_product_id,
            quantity=valid_qty,
        )
        db.session.add(return_record)
        db.session.commit()
        return product
    except Exception:
        db.session.rollback()
        raise
