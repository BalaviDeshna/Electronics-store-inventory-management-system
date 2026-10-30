
import statistics
import tempfile
import time
from pathlib import Path

from app import create_app
from app.data.extensions import db
from app.data.models import Product
from app.business.sales import create_sale


def run_benchmark(product_count, repetitions=15):
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "benchmark.db"

        app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
            "SECRET_KEY": "benchmark-only",
        })

        with app.app_context():
            db.create_all()

            products = [
                Product(
                    name=f"Benchmark Product {i}",
                    sku=f"BENCH-{i}",
                    price=100 + i,
                    stock=repetitions + 10,
                    reorder_threshold=0,
                )
                for i in range(product_count)
            ]

            db.session.add_all(products)
            db.session.commit()

            items = [
                {"product_id": product.id, "quantity": 1}
                for product in products
            ]

            # Warm-up: excluded from measurements.
            create_sale(items, Product)

            timings = []

            for _ in range(repetitions):
                start = time.perf_counter()

                sale = create_sale(items, Product)

                elapsed = time.perf_counter() - start
                timings.append(elapsed * 1000)

                assert sale.id is not None

            print(f"\nProducts per sale: {product_count}")
            print(f"Repetitions: {repetitions}")
            print(f"Average: {statistics.mean(timings):.3f} ms")
            print(f"Median:  {statistics.median(timings):.3f} ms")
            print(f"Maximum: {max(timings):.3f} ms")
            print(f"Minimum: {min(timings):.3f} ms")

            db.session.remove()
            db.drop_all()


if __name__ == "__main__":
    print("SALES TRANSACTION PERFORMANCE BASELINE")
    print("Database: temporary SQLite")
    print("Timing includes create_sale() and database commit.")

    for count in (1, 10, 50, 100):
        run_benchmark(count)


