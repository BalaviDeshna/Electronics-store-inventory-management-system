import os
import socket
from decimal import Decimal
from app import create_app
from app.data.extensions import db
from app.data.models import (
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Supplier,
    User,
)

app = create_app()


def init_db():
    with app.app_context():
        db.create_all()
        # Seed demo users if empty
        if User.query.first() is None:
            admin = User(
                username="admin",
                email="admin@electronics.local",
                role="admin",
            )
            admin.set_password("Admin123!")

            manager = User(
                username="manager",
                email="manager@electronics.local",
                role="manager",
            )
            manager.set_password("Manager123!")

            staff = User(
                username="staff",
                email="staff@electronics.local",
                role="staff",
            )
            staff.set_password("Staff123!")

            db.session.add_all([admin, manager, staff])
            db.session.commit()

        # Seed sample products if empty
        if Product.query.first() is None:
            demo_products = [
                Product(
                    name="Wireless Mouse",
                    sku="MOU-001",
                    category="Accessories",
                    price=Decimal("39.99"),
                    stock=40,
                    reorder_threshold=15,
                ),
                Product(
                    name="Mechanical Keyboard",
                    sku="KEY-001",
                    category="Accessories",
                    price=Decimal("89.99"),
                    stock=25,
                    reorder_threshold=10,
                ),
                Product(
                    name="27-Inch 4K Monitor",
                    sku="MON-001",
                    category="Displays",
                    price=Decimal("299.99"),
                    stock=8,
                    reorder_threshold=5,
                ),
                Product(
                    name="Noise-Cancelling Headphones",
                    sku="AUD-001",
                    category="Audio",
                    price=Decimal("149.99"),
                    stock=12,
                    reorder_threshold=6,
                ),
            ]
            db.session.add_all(demo_products)
            db.session.commit()

        # Seed sample suppliers if empty
        if Supplier.query.first() is None:
            demo_suppliers = [
                Supplier(
                    name="Apex Tech Distro",
                    contact_info="orders@apextech.com | +1-800-555-0199",
                    address="100 Silicon Blvd, San Jose, CA 95134",
                ),
                Supplier(
                    name="Global Components Ltd",
                    contact_info="sales@globalcomp.io | +1-888-555-0144",
                    address="456 Innovation Way, Austin, TX 78701",
                ),
            ]
            db.session.add_all(demo_suppliers)
            db.session.commit()


def get_available_port() -> int:
    port_env = os.environ.get("PORT")
    if port_env:
        return int(port_env)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Check if 5000 is occupied (e.g. by macOS AirPlay Receiver)
        if s.connect_ex(("127.0.0.1", 5000)) == 0:
            return 5001
    return 5000


if __name__ == "__main__":
    init_db()
    port = get_available_port()
    app.run(debug=True, port=port)
