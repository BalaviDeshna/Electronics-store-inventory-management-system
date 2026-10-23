from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

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


@main_bp.route("/products/create", methods=["GET", "POST"])
def create_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()

        if not name:
            flash("Product name is required.", "error")
            return render_template("create_product.html")

        if len(name) > 200:
            flash("Product name must be 200 characters or fewer.", "error")
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


@main_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def edit_product(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404, description="Product not found.")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()

        if not name:
            flash("Product name is required.", "error")
            return render_template("edit_product.html", product=product)

        if len(name) > 200:
            flash("Product name must be 200 characters or fewer.", "error")
            return render_template("edit_product.html", product=product)

        try:
            price = Decimal(raw_price)
            if not price.is_finite() or price < 0:
                raise ValueError
            price = price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            flash("Enter a valid, non-negative price.", "error")
            return render_template("edit_product.html", product=product)

        try:
            stock = int(raw_stock)
            if stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Stock must be a non-negative whole number.", "error")
            return render_template("edit_product.html", product=product)

        product.name = name
        product.price = price
        product.stock = stock
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to update product")
            flash("The product could not be updated. Please try again.", "error")
            return render_template("edit_product.html", product=product)

        flash("Product updated successfully.", "success")
        return redirect(url_for("main.edit_product", product_id=product.id))

    return render_template("edit_product.html", product=product)


@main_bp.route("/products/<int:product_id>/update", methods=["GET", "POST"])
def update_product(product_id):
    return edit_product(product_id)
