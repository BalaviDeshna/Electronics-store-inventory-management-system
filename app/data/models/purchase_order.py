from datetime import datetime, timezone
from decimal import Decimal

from app.data.extensions import db


class PurchaseOrder(db.Model):
    """A purchase order issued to a supplier for replenishing product inventory."""

    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("suppliers.id"),
        nullable=False,
        index=True,
    )
    status = db.Column(
        db.String(50),
        nullable=False,
        default="Pending",
        server_default="Pending",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    supplier = db.relationship(
        "Supplier",
        backref=db.backref("purchase_orders", lazy=True),
    )
    items = db.relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        lazy=True,
    )

    @property
    def order_number(self):
        return f"PO-{self.id:04d}" if self.id else "PO-NEW"

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items)

    @property
    def total_received_quantity(self):
        return sum(item.received_quantity or 0 for item in self.items)

    @property
    def total_pending_quantity(self):
        return sum(item.pending_quantity for item in self.items)

    def update_status_from_items(self):
        """Update purchase order status based on current items' received quantities."""
        if not self.items:
            return
        all_received = all((item.received_quantity or 0) >= item.quantity for item in self.items)
        none_received = all((item.received_quantity or 0) == 0 for item in self.items)
        if all_received:
            self.status = "Received"
        elif none_received:
            self.status = "Pending"
        else:
            self.status = "Partially Received"

    def mark_as_received(self):
        """Update purchase order status to Received and set received quantities."""
        self.status = "Received"
        for item in self.items:
            item.received_quantity = item.quantity

    def to_dict(self):
        return {
            "id": self.id,
            "order_number": self.order_number,
            "supplier_id": self.supplier_id,
            "supplier_name": self.supplier.name if self.supplier else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "total_quantity": self.total_quantity,
            "total_received_quantity": self.total_received_quantity,
            "total_pending_quantity": self.total_pending_quantity,
            "items": [item.to_dict() for item in self.items],
        }

    def __repr__(self):
        return f"<PurchaseOrder id={self.id} supplier_id={self.supplier_id} status={self.status!r}>"


class PurchaseOrderItem(db.Model):
    """A line item within a purchase order specifying product and ordered quantity."""

    __tablename__ = "purchase_order_items"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False,
        index=True,
    )
    quantity = db.Column(db.Integer, nullable=False)
    received_quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)

    purchase_order = db.relationship("PurchaseOrder", back_populates="items")
    product = db.relationship(
        "app.data.models.product.Product",
        backref=db.backref("purchase_order_items", lazy=True),
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_purchase_order_item_quantity_positive"),
        db.CheckConstraint("received_quantity >= 0", name="ck_purchase_order_item_received_quantity_nonnegative"),
    )

    @property
    def product_name(self):
        return self.product.name if self.product else None

    @property
    def pending_quantity(self):
        return max(0, self.quantity - (self.received_quantity or 0))

    @property
    def is_fully_received(self):
        return (self.received_quantity or 0) >= self.quantity

    @property
    def line_total(self):
        if self.unit_price is not None:
            return self.unit_price * self.quantity
        if self.product and getattr(self.product, "price", None) is not None:
            return self.product.price * self.quantity
        return Decimal("0.00")

    def to_dict(self):
        return {
            "id": self.id,
            "purchase_order_id": self.purchase_order_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "quantity": self.quantity,
            "received_quantity": self.received_quantity,
            "pending_quantity": self.pending_quantity,
            "unit_price": str(self.unit_price) if self.unit_price is not None else None,
            "line_total": str(self.line_total),
        }

    def __repr__(self):
        return (
            f"<PurchaseOrderItem id={self.id} po_id={self.purchase_order_id} "
            f"product_id={self.product_id} qty={self.quantity}>"
        )
