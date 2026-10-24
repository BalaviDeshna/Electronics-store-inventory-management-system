from datetime import datetime, timezone

from app.data.extensions import db


class ProductReturn(db.Model):
    """A record of a processed product return into inventory."""

    __tablename__ = "product_returns"

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.String(100), unique=True, nullable=True, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey("sale_items.id"), nullable=True)
    product_id = db.Column(db.Integer, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_product_return_quantity_positive"),
    )


class ProductRestock(db.Model):
    """A record of received restock inventory."""

    __tablename__ = "product_restocks"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(100), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_product_restock_quantity_positive"),
    )
