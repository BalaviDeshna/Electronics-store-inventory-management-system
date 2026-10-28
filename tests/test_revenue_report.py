
from datetime import datetime
from decimal import Decimal

from app.data.extensions import db
from app.data.models import Sale, SaleItem


def add_sale(created_at, total, items=None):
    sale = Sale(
        created_at=created_at,
        total_amount=Decimal(total),
    )
    db.session.add(sale)
    db.session.flush()

    if items is None:
        items = [("Test Product", 1, total)]

    for name, quantity, line_total in items:
        db.session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=1,
                product_name=name,
                quantity=quantity,
                unit_price=Decimal(line_total) / quantity,
                line_total=Decimal(line_total),
            )
        )

    db.session.commit()
    return sale


def report_url(start="2026-10-10", end="2026-10-15"):
    return f"/reports/revenue?start_date={start}&end_date={end}"


def test_manager_can_open_revenue_report(client, logged_in_manager):
    response = client.get("/reports/revenue")
    assert response.status_code == 200
    assert b"Revenue Report" in response.data


def test_admin_can_open_revenue_report(client, logged_in_admin):
    response = client.get("/reports/revenue")
    assert response.status_code == 200
    assert b"Revenue Report" in response.data


def test_staff_cannot_open_revenue_report(client, logged_in_staff):
    response = client.get("/reports/revenue")
    assert response.status_code == 403


def test_revenue_report_requires_both_dates(client, logged_in_manager):
    response = client.get("/reports/revenue?start_date=2026-10-10")
    assert response.status_code == 200
    assert b"Select both a start date and an end date." in response.data


def test_revenue_report_rejects_invalid_date(client, logged_in_manager):
    response = client.get(report_url("not-a-date", "2026-10-15"))
    assert response.status_code == 200
    assert b"Enter valid dates" in response.data


def test_revenue_report_rejects_reversed_dates(client, logged_in_manager):
    response = client.get(report_url("2026-10-15", "2026-10-10"))
    assert response.status_code == 200
    assert b"start date cannot be after the end date" in response.data


def test_revenue_report_includes_full_end_date(client, logged_in_manager):
    add_sale(
        datetime(2026, 10, 15, 23, 59, 59),
        "40.00",
        [("End Date Keyboard", 2, "40.00")],
    )
    response = client.get(report_url())
    assert response.status_code == 200
    assert b"End Date Keyboard" in response.data
    assert b"40.00" in response.data


def test_revenue_report_excludes_following_day(client, logged_in_manager):
    add_sale(
        datetime(2026, 10, 16, 0, 0, 0),
        "25.00",
        [("Following Day Mouse", 1, "25.00")],
    )
    response = client.get(report_url())
    assert response.status_code == 200
    assert b"Following Day Mouse" not in response.data
    assert b"0.00" in response.data


def test_revenue_report_sums_decimal_totals(client, logged_in_manager):
    add_sale(
        datetime(2026, 10, 12, 10, 0, 0),
        "10.10",
        [("USB Cable", 1, "10.10")],
    )
    add_sale(
        datetime(2026, 10, 12, 11, 0, 0),
        "20.20",
        [("Keyboard", 2, "20.20")],
    )
    add_sale(
        datetime(2026, 10, 13, 12, 0, 0),
        "0.30",
        [("Small Part", 1, "0.30")],
    )

    response = client.get(report_url())
    assert response.status_code == 200
    assert b"30.30" in response.data
    assert b"0.30" in response.data
    assert b"3" in response.data


def test_revenue_report_shows_empty_period(client, logged_in_manager):
    response = client.get(report_url())
    assert response.status_code == 200
    assert b"No sales were recorded for the selected date range." in response.data
    assert b"0.00" in response.data


def test_revenue_report_shows_daily_breakdown(client, logged_in_manager):
    add_sale(
        datetime(2026, 10, 12, 10, 0, 0),
        "12.50",
        [("Mouse", 1, "12.50")],
    )
    add_sale(
        datetime(2026, 10, 12, 15, 0, 0),
        "7.50",
        [("Cable", 1, "7.50")],
    )
    add_sale(
        datetime(2026, 10, 13, 9, 0, 0),
        "5.00",
        [("Adapter", 1, "5.00")],
    )

    response = client.get(report_url())
    assert response.status_code == 200
    assert b"Daily Revenue" in response.data
    assert b"20.00" in response.data
    assert b"5.00" in response.data


def test_revenue_report_documents_refund_limitation(
    client, logged_in_manager
):
    response = client.get(report_url())
    assert response.status_code == 200
    assert b"Refunds are not deducted" in response.data
