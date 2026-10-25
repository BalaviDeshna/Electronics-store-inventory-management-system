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
from flask_login import current_user

from app.business.sales import SaleValidationError, create_sale
from app.business.stock import (
    StockUpdateError,
    process_return,
    restock_product,
)
from app.data.extensions import db
from app.data.models import Product, Sale, SaleItem
from app.presentation.authz import manager_required


main_bp = Blueprint("main", __name__)


def parse_reorder_threshold(raw_val, default=0, required=False):
    if raw_val is None:
        if required:
            raise ValueError("Reorder threshold is required.")
        return default
    if isinstance(raw_val, bool):
        raise ValueError("Reorder threshold must be a non-negative whole number.")
    s = str(raw_val).strip()
    if not s:
        if required:
            raise ValueError("Reorder threshold is required.")
        return default
    if "." in s or "e" in s.lower() or "E" in s:
        raise ValueError("Reorder threshold must be a non-negative whole number.")
    try:
        val = int(s)
        if val < 0:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("Reorder threshold must be a non-negative whole number.")
    return val


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
        raw_threshold = request.form.get("reorder_threshold")

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

        try:
            threshold = parse_reorder_threshold(raw_threshold, default=0, required=False)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("create_product.html")

        if current_user.is_authenticated and current_user.role not in {"manager", "admin"}:
            if threshold != 0:
                abort(403)

        kwargs = {"name": name, "sku": sku, "price": price, "stock": stock}
        if hasattr(Product, "category"):
            kwargs["category"] = category
        if hasattr(Product, "reorder_threshold"):
            kwargs["reorder_threshold"] = threshold
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
        raw_threshold = request.form.get("reorder_threshold")

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

        threshold = None
        if raw_threshold is not None:
            if not str(raw_threshold).strip():
                flash("Reorder threshold is required.", "error")
                return render_template("edit_product.html", product=product)
            try:
                threshold = parse_reorder_threshold(raw_threshold, required=True)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("edit_product.html", product=product)

            if current_user.is_authenticated and current_user.role not in {"manager", "admin"}:
                current_threshold = getattr(product, "reorder_threshold", 0)
                if threshold != current_threshold:
                    abort(403)

        product.name = name
        product.sku = sku
        if hasattr(product, "category"):
            product.category = category
        product.price = price
        product.stock = stock
        if threshold is not None and hasattr(product, "reorder_threshold"):
            product.reorder_threshold = threshold
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


@main_bp.route("/products/<int:product_id>/reorder-threshold", methods=["POST"])
@manager_required
def update_reorder_threshold(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404, description="Product not found.")

    raw_threshold = request.form.get("reorder_threshold")
    if raw_threshold is None or not str(raw_threshold).strip():
        flash("Reorder threshold is required.", "error")
        return redirect(url_for("main.edit_product", product_id=product.id))

    try:
        val = parse_reorder_threshold(raw_threshold, required=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.edit_product", product_id=product.id))

    initial_stock = product.stock
    if hasattr(product, "reorder_threshold"):
        product.reorder_threshold = val

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to update reorder threshold")
        flash("The reorder threshold could not be updated. Please try again.", "error")
        return redirect(url_for("main.edit_product", product_id=product.id))

    assert product.stock == initial_stock
    flash("Reorder threshold updated successfully.", "success")
    return redirect(url_for("main.edit_product", product_id=product.id))


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


@main_bp.route("/products/<int:product_id>/restock", methods=["POST"])
def restock_product_route(product_id):
    raw_qty = request.form.get("quantity", "").strip()
    reference = request.form.get("reference", "").strip() or None
    try:
        restock_product(
            product_id,
            raw_qty,
            reference=reference,
            product_model=Product,
        )
        flash("Stock updated successfully.", "success")
    except StockUpdateError as exc:
        flash(str(exc), "error")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to restock product")
        flash("The product could not be restocked. Please try again.", "error")
    return redirect(url_for("main.home"))


@main_bp.route("/returns", methods=["POST"])
def process_return_route():
    product_id = request.form.get("product_id")
    sale_item_id = request.form.get("sale_item_id")
    quantity = request.form.get("quantity")
    return_id = request.form.get("return_id")
    try:
        process_return(
            product_id=product_id.strip() if product_id and product_id.strip() else None,
            sale_item_id=sale_item_id.strip() if sale_item_id and sale_item_id.strip() else None,
            quantity=quantity.strip() if quantity and quantity.strip() else None,
            return_id=return_id.strip() if return_id and return_id.strip() else None,
            product_model=Product,
        )
        flash("Return processed successfully and stock updated.", "success")
    except StockUpdateError as exc:
        flash(str(exc), "error")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to process return")
        flash("The return could not be processed. Please try again.", "error")
    return redirect(url_for("main.home"))
