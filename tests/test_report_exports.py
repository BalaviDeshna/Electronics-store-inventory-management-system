import pytest
from datetime import datetime
from decimal import Decimal
from app.data.extensions import db
from app.data.models import Product, Sale, SaleItem, ProductRestock, ProductReturn, User
from app.business.report_exports import build_csv_response, build_pdf_response


def test_build_csv_response_with_date_and_totals():
    resp = build_csv_response(
        title="Sample CSV Report",
        columns=["Col A", "Col B"],
        rows=[["Val 1", "Val 2"], ["Val 3", "Val 4"]],
        filename="sample.csv",
        date_range="2026-01-01 to 2026-01-31",
        totals=["Total A", "Total B"],
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    assert 'attachment; filename="sample.csv"' in resp.headers["Content-Disposition"]
    data = resp.get_data(as_text=True)
    assert "Sample CSV Report" in data
    assert "Report period,2026-01-01 to 2026-01-31" in data
    assert "Col A,Col B" in data
    assert "Totals,Total A,Total B" in data


def test_build_csv_response_without_date_and_totals():
    resp = build_csv_response(
        title="Minimal CSV Report",
        columns=["Col 1"],
        rows=[["A"], ["B"]],
        filename="minimal.csv",
        date_range=None,
        totals=None,
    )
    assert resp.status_code == 200
    data = resp.get_data(as_text=True)
    assert "Report period" not in data
    assert "Totals" not in data


def test_build_pdf_response_with_data_and_totals():
    resp = build_pdf_response(
        title="Sample PDF Report",
        columns=["Product", "Quantity", "Amount"],
        rows=[["Widget", 5, "50.00"]],
        filename="sample.pdf",
        date_range="2026-01-01 to 2026-01-31",
        totals=["Total", 5, "50.00"],
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert 'attachment; filename="sample.pdf"' in resp.headers["Content-Disposition"]
    assert resp.data.startswith(b"%PDF")


def test_build_pdf_response_empty_records():
    resp = build_pdf_response(
        title="Empty PDF Report",
        columns=["ID", "Name"],
        rows=[],
        filename="empty.pdf",
        date_range=None,
        totals=None,
    )
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")


def test_export_sales_report_routes(app, client, logged_in_manager):
    with app.app_context():
        p = Product(name="Headphones", price=Decimal("75.00"), stock=20)
        db.session.add(p)
        db.session.commit()

        s = Sale(total_amount=Decimal("150.00"), created_at=datetime(2026, 1, 15, 12, 0))
        db.session.add(s)
        db.session.flush()

        item = SaleItem(sale_id=s.id, product_id=p.id, product_name=p.name, quantity=2, unit_price=Decimal("75.00"), line_total=Decimal("150.00"))
        db.session.add(item)
        db.session.commit()

    # Invalid format -> 404
    r = client.get("/reports/sales/export/json?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 404

    # Missing dates -> 400
    r = client.get("/reports/sales/export/csv")
    assert r.status_code == 400
    assert b"Select both a start date and an end date" in r.data

    # Invalid dates -> 400
    r = client.get("/reports/sales/export/csv?start_date=invalid&end_date=2026-01-31")
    assert r.status_code == 400
    assert b"Enter valid dates" in r.data

    # Non-ISO date format -> 400
    r = client.get("/reports/sales/export/csv?start_date=2026-1-1&end_date=2026-01-31")
    assert r.status_code == 400
    assert b"Enter valid dates" in r.data

    # Start date after end date -> 400
    r = client.get("/reports/sales/export/csv?start_date=2026-02-01&end_date=2026-01-01")
    assert r.status_code == 400
    assert b"start date cannot be after the end date" in r.data

    # Valid CSV export
    r = client.get("/reports/sales/export/csv?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert "Headphones x 2" in r.get_data(as_text=True)

    # Valid PDF export
    r = client.get("/reports/sales/export/pdf?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"
    assert r.data.startswith(b"%PDF")


def test_export_revenue_report_routes(app, client, logged_in_manager):
    with app.app_context():
        p = Product(name="Keyboard", price=Decimal("40.00"), stock=15)
        db.session.add(p)
        db.session.commit()

        s = Sale(total_amount=Decimal("80.00"), created_at=datetime(2026, 1, 10, 10, 0))
        db.session.add(s)
        db.session.flush()

        item = SaleItem(sale_id=s.id, product_id=p.id, product_name=p.name, quantity=2, unit_price=Decimal("40.00"), line_total=Decimal("80.00"))
        db.session.add(item)
        db.session.commit()

    # Valid CSV export
    r = client.get("/reports/revenue/export/csv?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert "Daily Revenue" in r.get_data(as_text=True)

    # Valid PDF export
    r = client.get("/reports/revenue/export/pdf?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"
    assert r.data.startswith(b"%PDF")


def test_export_stock_report_routes(app, client, logged_in_manager):
    with app.app_context():
        p = Product(name="Monitor", sku="MON-001", price=Decimal("200.00"), stock=10)
        db.session.add(p)
        db.session.commit()

        restock = ProductRestock(product_id=p.id, quantity=5, created_at=datetime(2026, 1, 5, 9, 0))
        ret = ProductReturn(product_id=p.id, quantity=1, created_at=datetime(2026, 1, 6, 9, 0))
        db.session.add_all([restock, ret])
        db.session.commit()

    # Valid CSV export
    r = client.get("/reports/stock/export/csv?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 200
    assert "text/csv" in r.headers["Content-Type"]
    assert "Monitor" in r.get_data(as_text=True)

    # Valid PDF export
    r = client.get("/reports/stock/export/pdf?start_date=2026-01-01&end_date=2026-01-31")
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "application/pdf"
    assert r.data.startswith(b"%PDF")
