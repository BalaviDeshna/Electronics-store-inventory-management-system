
import csv
from io import BytesIO, StringIO
from decimal import Decimal

from flask import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


def build_csv_response(title, columns, rows, filename, date_range=None,
                       totals=None):
    """Build a CSV download from the supplied report data."""
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([title])
    if date_range:
        writer.writerow(["Report period", date_range])
    writer.writerow([])
    writer.writerow(columns)

    for row in rows:
        writer.writerow(row)

    if totals:
        writer.writerow([])
        writer.writerow(["Totals"] + list(totals))

    response = Response(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response


def build_pdf_response(title, columns, rows, filename, date_range=None,
                       totals=None):
    """Build a PDF download from the supplied report data."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=24,
        leftMargin=24,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    if date_range:
        story.append(
            Paragraph(f"Report period: {date_range}", styles["Normal"])
        )
        story.append(Spacer(1, 12))

    table_data = [columns]
    table_data.extend(
        [[str(value) for value in row] for row in rows]
    )

    if totals:
        table_data.append(["Totals"] + [str(value) for value in totals])

    if not rows:
        story.append(Paragraph("No records found for this report.",
                               styles["Normal"]))

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f4e78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)

    document.build(story)
    buffer.seek(0)

    response = Response(
        buffer.getvalue(),
        content_type="application/pdf",
    )
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{filename}"'
    )
    return response


