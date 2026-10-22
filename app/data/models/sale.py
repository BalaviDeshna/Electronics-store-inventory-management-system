from datetime import datetime, timezone
from decimal import Decimal

from app.data.extensions import db


class Sale(db.Model):
    """A completed sales transaction."""

    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    items = db.relationship(
        "SaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy=True,
    )


class SaleItem(db.Model):
    """A product and quantity recorded within a sale."""

    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sales.id"),
        nullable=False,
    )
    product_id = db.Column(db.Integer, nullable=False, index=True)
    product_name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    sale = db.relationship("Sale", back_populates="items")

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_sale_item_quantity_positive"),
        db.CheckConstraint("unit_price >= 0", name="ck_sale_item_price_nonnegative"),
        db.CheckConstraint("line_total >= 0", name="ck_sale_item_total_nonnegative"),
    )
