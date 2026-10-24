from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
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
from app.data.models import Product, Sale, SaleItem


main_bp = Blueprint("main", __name__)


def normalize_stock_status(val):
    if not val:
        return ""
    normalized = str(val).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"in_stock", "instock"}:
        return "in_stock"
    if normalized in {"out_of_stock", "outofstock", "out"}:
        return "out_of_stock"
    if normalized in {"low_stock", "lowstock", "low"}:
        return "low_stock"
    return ""


@main_bp.route("/")
def home():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    raw_status = request.args.get("stock_status") or request.args.get("status") or ""
    stock_status = normalize_stock_status(raw_status)

    query_obj = Product.query
    if q:
        conditions = [Product.name.ilike(f"%{q}%")]
        if hasattr(Product, "sku"):
            conditions.append(Product.sku.ilike(f"%{q}%"))
        query_obj = query_obj.filter(or_(*conditions))

    if category and hasattr(Product, "category"):
        query_obj = query_obj.filter(func.lower(Product.category) == category.lower())

    if hasattr(Product, "stock"):
        if stock_status == "in_stock":
            query_obj = query_obj.filter(Product.stock > 0)
        elif stock_status == "out_of_stock":
            query_obj = query_obj.filter(Product.stock == 0)
        elif stock_status == "low_stock":
            query_obj = query_obj.filter(Product.stock > 0, Product.stock <= 5)

    products = query_obj.order_by(Product.name).all()
    all_products = Product.query.order_by(Product.name).all()

    categories = []
    if hasattr(Product, "category"):
        raw_cats = (
            db.session.query(Product.category)
            .filter(Product.category.isnot(None), Product.category != "")
            .distinct()
            .order_by(Product.category)
            .all()
        )
        categories = [c[0] for c in raw_cats if c[0]]
        if category and category.lower() not in [c.lower() for c in categories]:
            categories.append(category)
            categories.sort(key=str.lower)

    return render_template(
        "index.html",
        products=products,
        all_products=all_products,
        q=q,
        query=q,
        categories=categories,
        selected_category=category,
        category=category,
        selected_stock_status=stock_status,
        stock_status=stock_status,
    )


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
        raw_sku = request.form.get("sku", "").strip()
        raw_category = request.form.get("category", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()

        if not name:
            flash("Product name is required.", "error")
            return render_template("create_product.html")

        if len(name) > 200:
            flash("Product name must be 200 characters or fewer.", "error")
            return render_template("create_product.html")

        sku = raw_sku if raw_sku else None
        if sku:
            if len(sku) > 100:
                flash("SKU must be 100 characters or fewer.", "error")
                return render_template("create_product.html")

            existing_sku = db.session.execute(
                db.select(Product).filter_by(sku=sku)
            ).scalar_one_or_none()
            if existing_sku:
                flash("A product with this SKU already exists.", "error")
                return render_template("create_product.html")

        category = raw_category if raw_category else None
        if category and len(category) > 100:
            flash("Category must be 100 characters or fewer.", "error")
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

        kwargs = {"name": name, "sku": sku, "price": price, "stock": stock}
        if hasattr(Product, "category"):
            kwargs["category"] = category
        product = Product(**kwargs)
        db.session.add(product)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("A product with this SKU already exists.", "error")
            return render_template("create_product.html")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to create product")
            flash("The product could not be created. Please try again.", "error")
            return render_template("create_product.html")

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
        raw_sku = request.form.get("sku", "").strip()
        raw_category = request.form.get("category", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()

        if not name:
            flash("Product name is required.", "error")
            return render_template("edit_product.html", product=product)

        if len(name) > 200:
            flash("Product name must be 200 characters or fewer.", "error")
            return render_template("edit_product.html", product=product)

        sku = raw_sku if raw_sku else None
        if sku:
            if len(sku) > 100:
                flash("SKU must be 100 characters or fewer.", "error")
                return render_template("edit_product.html", product=product)

            existing_sku = db.session.execute(
                db.select(Product).filter_by(sku=sku)
            ).scalar_one_or_none()
            if existing_sku and existing_sku.id != product.id:
                flash("A product with this SKU already exists.", "error")
                return render_template("edit_product.html", product=product)

        category = raw_category if raw_category else None
        if category and len(category) > 100:
            flash("Category must be 100 characters or fewer.", "error")
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
        product.sku = sku
        if hasattr(product, "category"):
            product.category = category
        product.price = price
        product.stock = stock
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("A product with this SKU already exists.", "error")
            return render_template("edit_product.html", product=product)
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


@main_bp.route("/products/<int:product_id>/delete", methods=["POST", "DELETE"])
def delete_product(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404, description="Product not found.")

    has_sales = db.session.execute(
        db.select(SaleItem).filter_by(product_id=product.id)
    ).first() is not None

    if has_sales:
        flash("Cannot delete product with existing sales records.", "error")
        return redirect(url_for("main.home"))

    try:
        db.session.delete(product)
        db.session.commit()
        flash("Product deleted successfully.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to delete product")
        flash("The product could not be deleted. Please try again.", "error")

    return redirect(url_for("main.home"))
