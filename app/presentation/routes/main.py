
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.business.sales import SaleValidationError, create_sale
from app.data.extensions import db
from app.data.models import Product, Sale

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def home():
    products = Product.query.order_by(Product.name).all()
    return render_template("index.html", products=products)


@main_bp.route("/sales", methods=["POST"])
def create_sale_route():
    product_ids = request.form.getlist("product_id")
    quantities = request.form.getlist("quantity")

    if len(product_ids) != len(quantities):
        flash("Invalid sale form. Please try again.", "error")
        return redirect(url_for("main.home"))

    items = [
        {"product_id": product_id, "quantity": quantity}
        for product_id, quantity in zip(product_ids, quantities)
        if product_id.strip() or quantity.strip()
    ]

    try:
        sale = create_sale(items, Product)
    except SaleValidationError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.home"))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to complete sale")
        flash("The sale could not be completed. Please try again.", "error")
        return redirect(url_for("main.home"))

    flash(f"Sale #{sale.id} completed successfully.", "success")
    return redirect(url_for("main.invoice", sale_id=sale.id))


@main_bp.route("/sales/<int:sale_id>/invoice")
def invoice(sale_id):
    sale = db.session.get(Sale, sale_id)

    if sale is None:
        abort(404)

    return render_template("invoice.html", sale=sale)
