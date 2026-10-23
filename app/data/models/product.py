
from app.data.extensions import db


class Product(db.Model):
    """A product available in the electronics store."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(100), unique=True, nullable=True, index=True)
    price = db.Column(db.Numeric(12, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.CheckConstraint(
            "price >= 0",
            name="ck_product_price_nonnegative",
        ),
        db.CheckConstraint(
            "stock >= 0",
            name="ck_product_stock_nonnegative",
        ),
    )
