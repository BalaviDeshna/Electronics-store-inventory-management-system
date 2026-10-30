from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.business.stock import (
    StockUpdateError,
    process_return,
    restock_inventory,
    restock_product,
)
from app.data.extensions import db
from app.data.models.sale import Sale, SaleItem


CENT = Decimal("0.01")
TAX_RATE = Decimal("0.05")


class SaleValidationError(StockUpdateError):
    """Raised when a requested sale is invalid."""


def money(value):
    """Convert a price to a two-decimal Decimal."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SaleValidationError("Invalid monetary amount.") from exc

    if not amount.is_finite():
        raise SaleValidationError("Monetary amount must be finite.")

    return amount.quantize(CENT, rounding=ROUND_HALF_UP)



def calculate_totals(subtotal):
    """Calculate subtotal, 5% tax, and final total."""
    subtotal = money(subtotal)
    tax_amount = money(subtotal * TAX_RATE)
    final_total = money(subtotal + tax_amount)
    return subtotal, tax_amount, final_total


def create_sale(items, product_model):
    """
    Create a sale and deduct stock atomically.

    Expected items format:
        [{"product_id": 1, "quantity": 2}, ...]

    product_model must provide id, name, price, and stock attributes.
    Products are locked where supported by the database.
    """
    if not items:
        raise SaleValidationError("A sale must contain at least one item.")


    quantities = {}
    for item in items:
        try:
            raw_product_id = item["product_id"]
            raw_quantity = item["quantity"]

            if isinstance(raw_product_id, bool) or isinstance(raw_quantity, bool):
                raise ValueError("Boolean values are not valid IDs or quantities.")

            product_id = int(raw_product_id)
            quantity = int(raw_quantity)

            if str(product_id) != str(raw_product_id).strip():
                raise ValueError("Product ID must be an integer.")

            if str(quantity) != str(raw_quantity).strip():
                raise ValueError("Quantity must be an integer.")

        except (KeyError, TypeError, ValueError) as exc:
            raise SaleValidationError(
                "Each item needs a valid integer product_id and quantity."
            ) from exc

        if product_id <= 0 or quantity <= 0:
            raise SaleValidationError(
                "Product IDs and quantities must be positive."
            )

        quantities[product_id] = quantities.get(product_id, 0) + quantity

    try:
        validated_items = []

        query = db.session.query(product_model).filter(
            product_model.id.in_(quantities.keys())
        )

        if db.engine.dialect.name != "sqlite":
            query = query.with_for_update()

        products_by_id = {
            product.id: product
            for product in query.all()
        }

        for product_id in sorted(quantities):
            product = products_by_id.get(product_id)

            if product is None:
                raise SaleValidationError(
                    f"Product {product_id} does not exist."
                )

            quantity = quantities[product_id]
            stock = int(product.stock)

            if stock < quantity:
                product_name = getattr(product, "name", str(product_id))
                raise SaleValidationError(
                    f"Insufficient stock for {product_name}. "
                    f"Available: {stock}, requested: {quantity}. "
                    "Reduce the quantity or restock the product."
                )

            unit_price = money(product.price)

            if unit_price < 0:
                raise SaleValidationError(
                    "Product price cannot be negative."
                )

            line_total = money(unit_price * quantity)
            validated_items.append(
                (product, product_id, quantity, unit_price, line_total)
            )

        sale = Sale(total_amount=Decimal("0.00"))
        total = Decimal("0.00")

        for product, product_id, quantity, unit_price, line_total in validated_items:
            sale.items.append(
                SaleItem(
                    product_id=product_id,
                    product_name=str(product.name),
                    quantity=quantity,
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

            product.stock = int(product.stock) - quantity
            total += line_total

        _, _, final_total = calculate_totals(total)
        sale.total_amount = final_total
        db.session.add(sale)
        db.session.commit()
        return sale

    except Exception:
        db.session.rollback()
        raise

