
from app.data.extensions import db


class Product(db.Model):
    """A product available in the electronics store."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(100), unique=True, nullable=True, index=True)
    category = db.Column(db.String(100), nullable=True, index=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    reorder_threshold = db.Column(
        db.Integer, nullable=False, default=0, server_default="0"
    )
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id"), nullable=True, index=True
    )

    supplier = db.relationship(
        "Supplier",
        backref=db.backref("products", lazy=True),
    )

    @property
    def is_below_reorder_threshold(self) -> bool:
        """Return True if stock is strictly below a configured positive reorder threshold."""
        threshold = getattr(self, "reorder_threshold", 0)
        if threshold is None or threshold <= 0:
            return False
        stock = getattr(self, "stock", 0)
        if stock is None:
            return False
        return stock < threshold

    @property
    def is_low_stock(self) -> bool:
        """Alias for is_below_reorder_threshold."""
        return self.is_below_reorder_threshold

    @property
    def suggested_reorder_quantity(self) -> int:
        """Calculate suggested replenishment quantity to restore inventory to threshold."""
        threshold = getattr(self, "reorder_threshold", 0) or 0
        stock = getattr(self, "stock", 0) or 0
        if threshold > stock:
            return threshold - stock
        return max(1, threshold)

    __table_args__ = (
        db.CheckConstraint(
            "price >= 0",
            name="ck_product_price_nonnegative",
        ),
        db.CheckConstraint(
            "stock >= 0",
            name="ck_product_stock_nonnegative",
        ),
        db.CheckConstraint(
            "reorder_threshold >= 0",
            name="ck_product_reorder_threshold_nonnegative",
        ),
    )
