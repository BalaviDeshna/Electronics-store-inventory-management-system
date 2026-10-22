from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.data.extensions import db
from app.data.models.product import Product

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    return render_template("index.html")


@main_bp.route("/sales/<int:sale_id>/invoice")
def invoice(sale_id):
    from flask import abort
    from app.data.extensions import db
    from app.data.models.sale import Sale

    sale = db.session.get(Sale, sale_id)

    if sale is None:
        abort(404)

    return render_template("invoice.html", sale=sale)


@main_bp.route("/products/create", methods=["GET", "POST"])
def create_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()

        if not name:
            flash("Product name is required.", "error")
            return render_template("create_product.html")

        try:
            price = Decimal(raw_price)
            if not price.is_finite() or price < 0:
                raise ValueError
            price = price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            flash("Enter a valid, non-negative price.", "error")
            return render_template("create_product.html")

        try:
            stock = int(raw_stock)
            if stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Stock must be a non-negative whole number.", "error")
            return render_template("create_product.html")

        product = Product(name=name, price=price, stock=stock)
        db.session.add(product)
        db.session.commit()

        flash("Product created successfully.", "success")
        return redirect(url_for("main.create_product"))

    return render_template("create_product.html")

