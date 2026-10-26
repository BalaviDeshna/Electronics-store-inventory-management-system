from datetime import datetime
from decimal import Decimal

from app.data.extensions import db
from app.data.models import (
    Product,
    ProductRestock,
    ProductReturn,
    Sale,
    SaleItem,
)


def test_manager_can_open_stock_report(client, logged_in_manager):
    response = client.get("/reports/stock")
    assert response.status_code == 200
    assert b"Stock Report" in response.data


def test_admin_can_open_stock_report(client, logged_in_admin):
    response = client.get("/reports/stock")
    assert response.status_code == 200


def test_staff_cannot_open_stock_report(client, logged_in_staff):
    response = client.get("/reports/stock")
    assert response.status_code == 403


def test_report_requires_both_dates(client, logged_in_manager):
    response = client.get(
        "/reports/stock?start_date=2026-10-10"
    )
    assert response.status_code == 200
    assert b"Select both a start date and an end date." in response.data


def test_report_rejects_reversed_dates(client, logged_in_manager):
    response = client.get(
        "/reports/stock?start_date=2026-10-15&end_date=2026-10-10"
    )
    assert response.status_code == 200
    assert b"start date is not after the end date" in response.data


def test_report_rejects_invalid_date(client, logged_in_manager):
    response = client.get(
        "/reports/stock?start_date=not-a-date&end_date=2026-10-15"
    )
    assert response.status_code == 200
    assert b"Enter valid dates" in response.data


def test_report_calculates_stock_movements(
    client, app, logged_in_manager
):
    product = Product(
        name="Report Mouse",
        sku="RPT-MOU",
        price=Decimal("20.00"),
        stock=16,
    )
    db.session.add(product)
    db.session.flush()

    sale = Sale(
        created_at=datetime(2026, 10, 12, 10, 0, 0),
        total_amount=Decimal("40.00"),
    )
    db.session.add(sale)
    db.session.flush()

    db.session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            product_name=product.name,
            quantity=2,
            unit_price=Decimal("20.00"),
            line_total=Decimal("40.00"),
        )
    )

    db.session.add(
        ProductRestock(
            product_id=product.id,
            quantity=5,
            created_at=datetime(2026, 10, 13, 11, 0, 0),
        )
    )
    db.session.add(
        ProductReturn(
            product_id=product.id,
            quantity=1,
            created_at=datetime(2026, 10, 14, 12, 0, 0),
        )
    )
    db.session.commit()

    response = client.get(
        "/reports/stock?start_date=2026-10-10&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"Report Mouse" in response.data
    assert b"RPT-MOU" in response.data
    assert b"Units Sold" in response.data
    assert b"Units Restocked" in response.data
    assert b"Units Returned" in response.data
    assert b"Net Movement" in response.data
    assert b"Current Stock" in response.data

    # Sold: 2, restocked: 5, returned: 1.
    # Net movement = 5 + 1 - 2 = 4.
    assert b">2</td>" in response.data
    assert b">5</td>" in response.data
    assert b">1</td>" in response.data
    assert b">4</td>" in response.data
    assert b">16</td>" in response.data


def test_report_includes_movements_on_end_date(
    client, app, logged_in_manager
):
    product = Product(
        name="End Date Keyboard",
        sku="END-KEY",
        price=Decimal("30.00"),
        stock=7,
    )
    db.session.add(product)
    db.session.flush()

    db.session.add(
        ProductRestock(
            product_id=product.id,
            quantity=3,
            created_at=datetime(2026, 10, 15, 23, 59, 59),
        )
    )
    db.session.commit()

    response = client.get(
        "/reports/stock?start_date=2026-10-10&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"End Date Keyboard" in response.data
    assert b">3</td>" in response.data
