
from datetime import datetime
from decimal import Decimal

from app.data.extensions import db
from app.data.models import Sale, SaleItem


def add_sale(created_at, total, item_name="Test Mouse", quantity=1):
    sale = Sale(
        created_at=created_at,
        total_amount=Decimal(total),
    )
    db.session.add(sale)
    db.session.flush()

    db.session.add(
        SaleItem(
            sale_id=sale.id,
            product_id=1,
            product_name=item_name,
            quantity=quantity,
            unit_price=Decimal(total),
            line_total=Decimal(total),
        )
    )
    db.session.commit()
    return sale


def test_manager_can_open_sales_report(client, logged_in_manager):
    response = client.get("/reports/sales")

    assert response.status_code == 200
    assert b"Sales Report" in response.data


def test_admin_can_open_sales_report(client, logged_in_admin):
    response = client.get("/reports/sales")

    assert response.status_code == 200
    assert b"Sales Report" in response.data


def test_staff_cannot_open_sales_report(client, logged_in_staff):
    response = client.get("/reports/sales")

    assert response.status_code == 403


def test_sales_report_requires_both_dates(client, logged_in_manager):
    response = client.get("/reports/sales?start_date=2026-10-10")

    assert response.status_code == 200
    assert b"Select both a start date and an end date." in response.data


def test_sales_report_rejects_invalid_date(client, logged_in_manager):
    response = client.get(
        "/reports/sales?start_date=not-a-date&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"Enter valid dates" in response.data


def test_sales_report_rejects_reversed_dates(client, logged_in_manager):
    response = client.get(
        "/reports/sales?start_date=2026-10-15&end_date=2026-10-10"
    )

    assert response.status_code == 200
    assert b"start date cannot be after the end date" in response.data


def test_sales_report_includes_sale_late_on_end_date(
    client, logged_in_manager
):
    add_sale(
        datetime(2026, 10, 15, 23, 59, 59),
        "40.00",
        item_name="End Date Keyboard",
        quantity=2,
    )

    response = client.get(
        "/reports/sales?start_date=2026-10-10&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"End Date Keyboard" in response.data
    assert b"40.00" in response.data


def test_sales_report_excludes_sale_on_following_day(
    client, logged_in_manager
):
    add_sale(
        datetime(2026, 10, 16, 0, 0, 0),
        "25.00",
        item_name="Following Day Mouse",
    )

    response = client.get(
        "/reports/sales?start_date=2026-10-10&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"Following Day Mouse" not in response.data


def test_sales_report_shows_empty_state(client, logged_in_manager):
    response = client.get(
        "/reports/sales?start_date=2026-10-10&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"No sales were found for the selected date range." in response.data


def test_sales_report_shows_sale_details_and_total(
    client, logged_in_manager
):
    add_sale(
        datetime(2026, 10, 12, 14, 30, 0),
        "60.00",
        item_name="USB Keyboard",
        quantity=3,
    )

    response = client.get(
        "/reports/sales?start_date=2026-10-10&end_date=2026-10-15"
    )

    assert response.status_code == 200
    assert b"USB Keyboard" in response.data
    assert b"2026-10-12" in response.data
    assert b"60.00" in response.data
    assert b"View Invoice" in response.data
