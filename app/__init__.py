
from flask import Flask

from sqlalchemy import inspect, text

from app.config import Config
from app.data.extensions import db, login_manager
from app.data.models import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Sale,
    SaleItem,
    Supplier,
    User,
)
from app.presentation.routes.main import main_bp
from app.presentation.routes.auth import auth_bp
from app.presentation.routes.supplier import supplier_bp
from app.presentation.routes.purchase_order import purchase_order_bp


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(supplier_bp)
    app.register_blueprint(supplier_bp, name="suppliers")
    app.register_blueprint(purchase_order_bp)

    with app.app_context():
        # Ensure supporting tables exist.
        try:
            Supplier.__table__.create(db.engine, checkfirst=True)
            PurchaseOrder.__table__.create(db.engine, checkfirst=True)
            PurchaseOrderItem.__table__.create(db.engine, checkfirst=True)
        except Exception:
            app.logger.exception(
                "Unable to ensure supporting tables exist"
            )

        # Add columns introduced by previous schema updates.
        try:
            inspector = inspect(db.engine)
            table_names = inspector.get_table_names()

            if "products" in table_names:
                columns = {
                    column["name"]
                    for column in inspector.get_columns("products")
                }

                if "reorder_threshold" not in columns:
                    with db.engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE products "
                                "ADD COLUMN reorder_threshold "
                                "INTEGER NOT NULL DEFAULT 0"
                            )
                        )

                if "supplier_id" not in columns:
                    with db.engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE products "
                                "ADD COLUMN supplier_id INTEGER "
                                "REFERENCES suppliers(id)"
                            )
                        )
        except Exception:
            app.logger.exception(
                "Unable to update products schema"
            )

        # Add the refund amount column to existing return tables.
        try:
            inspector = inspect(db.engine)
            table_names = inspector.get_table_names()

            if "product_returns" in table_names:
                columns = {
                    column["name"]
                    for column in inspector.get_columns(
                        "product_returns"
                    )
                }

                if "refund_amount" not in columns:
                    with db.engine.begin() as conn:
                        conn.execute(
                            text(
                                "ALTER TABLE product_returns "
                                "ADD COLUMN refund_amount "
                                "NUMERIC(12, 2) "
                                "NOT NULL DEFAULT 0.00"
                            )
                        )
        except Exception:
            app.logger.exception(
                "Unable to update product_returns schema"
            )

    return app
