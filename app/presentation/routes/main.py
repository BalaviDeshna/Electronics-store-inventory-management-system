from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from app.business.audit import record_audit

from sqlalchemy import and_, func, or_
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


from app.business.sales import (
    SaleValidationError,
    calculate_totals,
    create_sale,
)



from app.business.stock import (
    StockUpdateError,
    process_return,
    restock_product,
)
from app.data.extensions import db
from app.data.models import (
    Product,
    ProductRestock,
    ProductReturn,
    Sale,
    SaleItem,
    Supplier,
)
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


def parse_supplier_id(raw_val):
    if raw_val is None:
        return None
    s = str(raw_val).strip()
    if not s or s.lower() in {"none", "null", "0"}:
        return None
    try:
        val = int(s)
        if val <= 0:
            raise ValueError
        return val
    except (ValueError, TypeError):
        raise ValueError("Please select a valid supplier.")


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
            if hasattr(Product, "reorder_threshold"):
                query_obj = query_obj.filter(
                    or_(
                        and_(
                            Product.reorder_threshold > 0,
                            Product.stock < Product.reorder_threshold,
                        ),
                        and_(
                            or_(
                                Product.reorder_threshold == 0,
                                Product.reorder_threshold.is_(None),
                            ),
                            Product.stock > 0,
                            Product.stock <= 5,
                        ),
                    )
                )
            else:
                query_obj = query_obj.filter(Product.stock > 0, Product.stock <= 5)

    products = query_obj.order_by(Product.name).all()
    all_products = Product.query.order_by(Product.name).all()

    low_stock_alerts = [
        p
        for p in all_products
        if getattr(p, "is_below_reorder_threshold", False)
        or (
            getattr(p, "reorder_threshold", 0) is not None
            and getattr(p, "reorder_threshold", 0) > 0
            and getattr(p, "stock", 0) < getattr(p, "reorder_threshold", 0)
        )
    ]

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
        low_stock_alerts=low_stock_alerts,
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
@main_bp.route("/sales/<int:sale_id>/invoice")
def invoice(sale_id):
    sale = db.session.get(Sale, sale_id)
    if sale is None:
        abort(404)

    subtotal = sum(
        (Decimal(str(item.line_total)) for item in sale.items),
        Decimal("0.00"),
    )
    subtotal, tax_amount, final_total = calculate_totals(subtotal)

    return render_template(
        "invoice.html",
        sale=sale,
        subtotal=subtotal,
        tax_amount=tax_amount,
        final_total=final_total,
    )

@main_bp.route("/products/create", methods=["GET", "POST"])
def create_product():
    suppliers = Supplier.query.order_by(Supplier.name).all() if hasattr(Supplier, "query") else []
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        raw_sku = request.form.get("sku", "").strip()
        raw_category = request.form.get("category", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()
        raw_threshold = request.form.get("reorder_threshold")
        raw_supplier_id = request.form.get("supplier_id")

        if not name:
            flash("Product name is required.", "error")
            return render_template("create_product.html", suppliers=suppliers)

        if len(name) > 200:
            flash("Product name must be 200 characters or fewer.", "error")
            return render_template("create_product.html", suppliers=suppliers)

        sku = raw_sku if raw_sku else None
        if sku:
            if len(sku) > 100:
                flash("SKU must be 100 characters or fewer.", "error")
                return render_template("create_product.html", suppliers=suppliers)

            existing_sku = db.session.execute(
                db.select(Product).filter_by(sku=sku)
            ).scalar_one_or_none()
            if existing_sku:
                flash("A product with this SKU already exists.", "error")
                return render_template("create_product.html", suppliers=suppliers)

        category = raw_category if raw_category else None
        if category and len(category) > 100:
            flash("Category must be 100 characters or fewer.", "error")
            return render_template("create_product.html", suppliers=suppliers)

        try:
            price = Decimal(raw_price)
            if not price.is_finite() or price < 0:
                raise ValueError
            price = price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            flash("Enter a valid, non-negative price.", "error")
            return render_template("create_product.html", suppliers=suppliers)

        try:
            stock = int(raw_stock)
            if stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Stock must be a non-negative whole number.", "error")
            return render_template("create_product.html", suppliers=suppliers)

        try:
            threshold = parse_reorder_threshold(raw_threshold, default=0, required=False)
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("create_product.html", suppliers=suppliers)

        if current_user.is_authenticated and current_user.role not in {"manager", "admin"}:
            if threshold != 0:
                abort(403)

        supplier_id = None
        if raw_supplier_id is not None:
            try:
                supplier_id = parse_supplier_id(raw_supplier_id)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("create_product.html", suppliers=suppliers)

            if supplier_id is not None:
                supplier = db.session.get(Supplier, supplier_id)
                if supplier is None:
                    flash("Selected supplier does not exist.", "error")
                    return render_template("create_product.html", suppliers=suppliers)

            if current_user.is_authenticated and current_user.role != "admin":
                if supplier_id is not None:
                    abort(403)

        kwargs = {"name": name, "sku": sku, "price": price, "stock": stock}
        if hasattr(Product, "category"):
            kwargs["category"] = category
        if hasattr(Product, "reorder_threshold"):
            kwargs["reorder_threshold"] = threshold
        if hasattr(Product, "supplier_id"):
            kwargs["supplier_id"] = supplier_id
        product = Product(**kwargs)
        db.session.add(product)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("A product with this SKU already exists.", "error")
            return render_template("create_product.html", suppliers=suppliers)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to create product")
            flash("The product could not be created. Please try again.", "error")
            return render_template("create_product.html", suppliers=suppliers)

        flash("Product created successfully.", "success")
        return redirect(url_for("main.create_product"))

    return render_template("create_product.html", suppliers=suppliers)


@main_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
def edit_product(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404, description="Product not found.")

    suppliers = Supplier.query.order_by(Supplier.name).all() if hasattr(Supplier, "query") else []

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        raw_sku = request.form.get("sku", "").strip()
        raw_category = request.form.get("category", "").strip()
        raw_price = request.form.get("price", "").strip()
        raw_stock = request.form.get("stock", "").strip()
        raw_threshold = request.form.get("reorder_threshold")
        raw_supplier_id = request.form.get("supplier_id")

        if not name:
            flash("Product name is required.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)

        if len(name) > 200:
            flash("Product name must be 200 characters or fewer.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)

        sku = raw_sku if raw_sku else None
        if sku:
            if len(sku) > 100:
                flash("SKU must be 100 characters or fewer.", "error")
                return render_template("edit_product.html", product=product, suppliers=suppliers)

            existing_sku = db.session.execute(
                db.select(Product).filter_by(sku=sku)
            ).scalar_one_or_none()
            if existing_sku and existing_sku.id != product.id:
                flash("A product with this SKU already exists.", "error")
                return render_template("edit_product.html", product=product, suppliers=suppliers)

        category = raw_category if raw_category else None
        if category and len(category) > 100:
            flash("Category must be 100 characters or fewer.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)

        try:
            price = Decimal(raw_price)
            if not price.is_finite() or price < 0:
                raise ValueError
            price = price.quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            flash("Enter a valid, non-negative price.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)

        try:
            stock = int(raw_stock)
            if stock < 0:
                raise ValueError
        except (ValueError, TypeError):
            flash("Stock must be a non-negative whole number.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)

        threshold = None
        if raw_threshold is not None:
            if not str(raw_threshold).strip():
                flash("Reorder threshold is required.", "error")
                return render_template("edit_product.html", product=product, suppliers=suppliers)
            try:
                threshold = parse_reorder_threshold(raw_threshold, required=True)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("edit_product.html", product=product, suppliers=suppliers)

            if current_user.is_authenticated and current_user.role not in {"manager", "admin"}:
                current_threshold = getattr(product, "reorder_threshold", 0)
                if threshold != current_threshold:
                    abort(403)

        update_supplier = False
        supplier_id = None
        if raw_supplier_id is not None:
            try:
                supplier_id = parse_supplier_id(raw_supplier_id)
            except ValueError as exc:
                flash(str(exc), "error")
                return render_template("edit_product.html", product=product, suppliers=suppliers)

            if supplier_id is not None:
                supplier = db.session.get(Supplier, supplier_id)
                if supplier is None:
                    flash("Selected supplier does not exist.", "error")
                    return render_template("edit_product.html", product=product, suppliers=suppliers)

            if current_user.is_authenticated and current_user.role != "admin":
                current_supplier_id = getattr(product, "supplier_id", None)
                if supplier_id != current_supplier_id:
                    abort(403)

            update_supplier = True

        old_price = product.price
        old_stock = product.stock
        product.name = name
        product.sku = sku
        if hasattr(product, "category"):
            product.category = category
        product.price = price
        product.stock = stock
        if threshold is not None and hasattr(product, "reorder_threshold"):
            product.reorder_threshold = threshold
        if update_supplier and hasattr(product, "supplier_id"):
            product.supplier_id = supplier_id

        try:
            if old_stock != product.stock:
                record_audit(
                    action="stock_edit",
                    entity_type="product",
                    entity_id=product.id,
                    details=f"Stock changed from {old_stock} to {product.stock}",
                )

            if old_price != product.price:
                record_audit(
                    action="price_change",
                    entity_type="product",
                    entity_id=product.id,
                    details=f"Price changed from {old_price} to {product.price}",
                )
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("A product with this SKU already exists.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to update product")
            flash("The product could not be updated. Please try again.", "error")
            return render_template("edit_product.html", product=product, suppliers=suppliers)

        flash("Product updated successfully.", "success")
        return redirect(url_for("main.edit_product", product_id=product.id))

    return render_template("edit_product.html", product=product, suppliers=suppliers)


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
        record_audit(
            action="product_delete",
            entity_type="product",
            entity_id=product.id,
            details=f"Deleted product: {product.name}",
        )

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




@main_bp.route("/reports/revenue", methods=["GET"])
@manager_required
def revenue_report():
    raw_start = request.args.get("start_date", "").strip()
    raw_end = request.args.get("end_date", "").strip()

    sales = []
    daily_totals = []
    total_revenue = Decimal("0.00")
    error = None
    report_generated = False

    if raw_start or raw_end:
        if not raw_start or not raw_end:
            error = "Select both a start date and an end date."
        else:
            try:
                start = datetime.strptime(
                    raw_start, "%Y-%m-%d"
                ).date()
                end = datetime.strptime(
                    raw_end, "%Y-%m-%d"
                ).date()

                if (
                    start.isoformat() != raw_start
                    or end.isoformat() != raw_end
                ):
                    raise ValueError

                if start > end:
                    error = (
                        "The start date cannot be after the end date."
                    )
            except ValueError:
                error = (
                    "Enter valid dates and ensure the start date "
                    "is not after the end date."
                )

            if error is None:
                start_dt = datetime.combine(
                    start, datetime.min.time()
                )
                end_exclusive = datetime.combine(
                    end + timedelta(days=1),
                    datetime.min.time(),
                )

                sales = (
                    Sale.query
                    .filter(
                        Sale.created_at >= start_dt,
                        Sale.created_at < end_exclusive,
                    )
                    .order_by(Sale.created_at.asc(), Sale.id.asc())
                    .all()
                )

                for sale in sales:
                    amount = sale.total_amount or Decimal("0.00")
                    total_revenue += amount

                    sale_day = sale.created_at.date()
                    if (
                        not daily_totals
                        or daily_totals[-1]["date"] != sale_day
                    ):
                        daily_totals.append({
                            "date": sale_day,
                            "revenue": Decimal("0.00"),
                            "transactions": 0,
                        })

                    daily_totals[-1]["revenue"] += amount
                    daily_totals[-1]["transactions"] += 1

                report_generated = True

    return render_template(
        "revenue_report.html",
        start_date=raw_start,
        end_date=raw_end,
        sales=sales,
        daily_totals=daily_totals,
        total_revenue=total_revenue,
        transaction_count=len(sales),
        error=error,
        report_generated=report_generated,
    )
@main_bp.route("/reports/sales", methods=["GET"])
@manager_required
def sales_report():
    raw_start = request.args.get("start_date", "").strip()
    raw_end = request.args.get("end_date", "").strip()

    sales = []
    error = None

    if raw_start or raw_end:
        if not raw_start or not raw_end:
            error = "Select both a start date and an end date."
        else:
            try:
                start = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end = datetime.strptime(raw_end, "%Y-%m-%d").date()

                if (
                    start.isoformat() != raw_start
                    or end.isoformat() != raw_end
                ):
                    raise ValueError

                if start > end:
                    error = "The start date cannot be after the end date."

            except ValueError:
                error = (
                    "Enter valid dates and ensure the start date "
                    "is not after the end date."
                )

            if error is None:
                start_dt = datetime.combine(
                    start,
                    datetime.min.time(),
                )
                end_exclusive = datetime.combine(
                    end + timedelta(days=1),
                    datetime.min.time(),
                )

                sales = (
                    Sale.query
                    .filter(
                        Sale.created_at >= start_dt,
                        Sale.created_at < end_exclusive,
                    )
                    .order_by(
                        Sale.created_at.desc(),
                        Sale.id.desc(),
                    )
                    .all()
                )

    return render_template(
        "sales_report.html",
        start_date=raw_start,
        end_date=raw_end,
        sales=sales,
        error=error,
    )
@main_bp.route("/reports/stock", methods=["GET"])
@manager_required
def stock_report():
    raw_start = request.args.get("start_date", "").strip()
    raw_end = request.args.get("end_date", "").strip()

    report_rows = []
    error = None

    if raw_start or raw_end:
        if not raw_start or not raw_end:
            error = "Select both a start date and an end date."
        else:
            try:
                start = datetime.strptime(raw_start, "%Y-%m-%d").date()
                end = datetime.strptime(raw_end, "%Y-%m-%d").date()

                if (
                    start.isoformat() != raw_start
                    or end.isoformat() != raw_end
                ):
                    raise ValueError

                if start > end:
                    error = (
                        "Enter valid dates and ensure the start date "
                        "is not after the end date."
                    )
            except ValueError:
                error = (
                    "Enter valid dates and ensure the start date "
                    "is not after the end date."
                )

            if error is None:
                start_dt = datetime.combine(start, datetime.min.time())
                end_exclusive = datetime.combine(
                    end + timedelta(days=1),
                    datetime.min.time(),
                )

                def totals_by_product(query):
                    return {
                        product_id: int(quantity or 0)
                        for product_id, quantity in query.all()
                    }

                sold = totals_by_product(
                    db.session.query(
                        SaleItem.product_id,
                        func.sum(SaleItem.quantity),
                    )
                    .join(Sale, Sale.id == SaleItem.sale_id)
                    .filter(
                        Sale.created_at >= start_dt,
                        Sale.created_at < end_exclusive,
                    )
                    .group_by(SaleItem.product_id)
                )

                restocked = totals_by_product(
                    db.session.query(
                        ProductRestock.product_id,
                        func.sum(ProductRestock.quantity),
                    )
                    .filter(
                        ProductRestock.created_at >= start_dt,
                        ProductRestock.created_at < end_exclusive,
                    )
                    .group_by(ProductRestock.product_id)
                )

                returned = totals_by_product(
                    db.session.query(
                        ProductReturn.product_id,
                        func.sum(ProductReturn.quantity),
                    )
                    .filter(
                        ProductReturn.created_at >= start_dt,
                        ProductReturn.created_at < end_exclusive,
                    )
                    .group_by(ProductReturn.product_id)
                )

                for product in Product.query.order_by(Product.name).all():
                    sold_qty = sold.get(product.id, 0)
                    restock_qty = restocked.get(product.id, 0)
                    return_qty = returned.get(product.id, 0)

                    report_rows.append(
                        {
                            "product": product,
                            "sold": sold_qty,
                            "restocked": restock_qty,
                            "returned": return_qty,
                            "net_change": (
                                restock_qty + return_qty - sold_qty
                            ),
                        }
                    )

    return render_template(
        "stock_report.html",
        start_date=raw_start,
        end_date=raw_end,
        report_rows=report_rows,
        error=error,
    )
