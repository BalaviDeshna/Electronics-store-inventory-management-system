from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from app.business.purchase_order import (
    PurchaseOrderValidationError,
    create_purchase_order,
    create_purchase_order_from_low_stock,
    receive_purchase_order,
    record_partial_delivery,
)
from app.data.extensions import db
from app.data.models import Product, PurchaseOrder, Supplier
from app.presentation.authz import manager_required

purchase_order_bp = Blueprint("purchase_order", __name__)


@purchase_order_bp.route(
    "/purchase-orders/create",
    methods=["GET", "POST"],
    endpoint="create_purchase_order",
)
@purchase_order_bp.route(
    "/purchase-orders/new",
    methods=["GET", "POST"],
    endpoint="new_purchase_order",
)
@purchase_order_bp.route(
    "/purchase-orders",
    methods=["POST"],
    endpoint="create_purchase_order_post",
)
@manager_required
def create_purchase_order_view():
    suppliers = Supplier.query.order_by(Supplier.name).all() if hasattr(Supplier, "query") else []
    products = Product.query.order_by(Product.name).all() if hasattr(Product, "query") else []

    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
            raw_supplier_id = data.get("supplier_id")
            raw_items = data.get("items") or []
            items = raw_items
        else:
            raw_supplier_id = request.form.get("supplier_id")
            product_ids = request.form.getlist("product_id")
            quantities = request.form.getlist("quantity")

            if not product_ids and request.form.get("product_id"):
                product_ids = [request.form.get("product_id")]
            if not quantities and request.form.get("quantity"):
                quantities = [request.form.get("quantity")]

            items = [
                {"product_id": pid, "quantity": qty}
                for pid, qty in zip(product_ids, quantities)
                if (pid and str(pid).strip()) or (qty and str(qty).strip())
            ]

        try:
            po = create_purchase_order(raw_supplier_id, items)
            flash(f"Purchase order #{po.id} created successfully.", "success")
            if request.is_json:
                return jsonify({"success": True, "purchase_order": po.to_dict()}), 201
            return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))

        except PurchaseOrderValidationError as exc:
            if request.is_json:
                return jsonify({"error": str(exc)}), 400
            flash(str(exc), "error")
            return (
                render_template(
                    "create_purchase_order.html",
                    suppliers=suppliers,
                    products=products,
                    selected_supplier_id=raw_supplier_id,
                ),
                400,
            )
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to create purchase order")
            if request.is_json:
                return jsonify({"error": "The purchase order could not be created."}), 500
            flash("The purchase order could not be created. Please try again.", "error")
            return (
                render_template(
                    "create_purchase_order.html",
                    suppliers=suppliers,
                    products=products,
                    selected_supplier_id=raw_supplier_id,
                ),
                500,
            )

    prefill_pid = request.args.get("product_id")
    selected_product_id = None
    selected_supplier_id = None
    selected_quantity = None
    if prefill_pid:
        matching_p = next(
            (p for p in products if str(p.id) == str(prefill_pid)), None
        )
        if matching_p:
            selected_product_id = matching_p.id
            selected_supplier_id = matching_p.supplier_id
            selected_quantity = getattr(
                matching_p, "suggested_reorder_quantity", None
            )

    return render_template(
        "create_purchase_order.html",
        suppliers=suppliers,
        products=products,
        selected_product_id=selected_product_id,
        selected_supplier_id=selected_supplier_id,
        selected_quantity=selected_quantity,
    )


@purchase_order_bp.route(
    "/purchase-orders",
    methods=["GET"],
    endpoint="list_purchase_orders",
)
@purchase_order_bp.route(
    "/purchase-orders/list",
    methods=["GET"],
    endpoint="purchase_orders_list",
)
@manager_required
def list_purchase_orders_view():
    purchase_orders = (
        PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
        if hasattr(PurchaseOrder, "query")
        else []
    )
    if request.is_json:
        return jsonify([po.to_dict() for po in purchase_orders]), 200

    return render_template(
        "purchase_orders.html",
        purchase_orders=purchase_orders,
    )


@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>",
    methods=["GET"],
    endpoint="view_purchase_order",
)
@manager_required
def view_purchase_order_view(po_id):
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        if request.is_json:
            return jsonify({"error": "Purchase order not found."}), 404
        abort(404, description="Purchase order not found.")

    if request.is_json:
        return jsonify(po.to_dict()), 200

    return render_template(
        "purchase_order.html",
        purchase_order=po,
    )


@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>/receive",
    methods=["POST"],
    endpoint="receive_purchase_order",
)
@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>/mark-received",
    methods=["POST"],
    endpoint="mark_received",
)
@manager_required
def receive_purchase_order_view(po_id):
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        if request.is_json:
            return jsonify({"error": "Purchase order not found."}), 404
        abort(404, description="Purchase order not found.")

    try:
        updated_po = receive_purchase_order(po_id)
        flash(
            f"Purchase order #{updated_po.id} marked as received. Stock updated successfully.",
            "success",
        )
        if request.is_json:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Purchase order received and stock updated.",
                        "purchase_order": updated_po.to_dict(),
                    }
                ),
                200,
            )
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))

    except PurchaseOrderValidationError as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to receive purchase order")
        if request.is_json:
            return jsonify({"error": "Failed to receive purchase order."}), 500
        flash("An error occurred while receiving the purchase order.", "error")
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))


@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>/partial-receive",
    methods=["GET", "POST"],
    endpoint="record_partial_delivery",
)
@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>/record-delivery",
    methods=["GET", "POST"],
    endpoint="record_delivery",
)
@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>/deliveries",
    methods=["GET", "POST"],
    endpoint="deliveries",
)
@purchase_order_bp.route(
    "/purchase-orders/<int:po_id>/receive-partial",
    methods=["GET", "POST"],
    endpoint="receive_partial",
)
@manager_required
def record_partial_delivery_view(po_id):
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        if request.is_json:
            return jsonify({"error": "Purchase order not found."}), 404
        abort(404, description="Purchase order not found.")

    if request.method == "GET":
        if request.is_json:
            return jsonify(po.to_dict()), 200
        return render_template("purchase_order.html", purchase_order=po)

    deliveries = []
    if request.is_json:
        data = request.get_json(silent=True)
        if data is None:
            data = {}
        if isinstance(data, list):
            deliveries = data
        elif isinstance(data, dict):
            if "deliveries" in data:
                deliveries = data["deliveries"]
            elif "items" in data:
                deliveries = data["items"]
            elif "item_id" in data or "product_id" in data:
                deliveries = [data]
            else:
                deliveries = data
    else:
        # Check standard form fields
        item_ids = request.form.getlist("item_id")
        delivered_qtys = request.form.getlist("delivered_quantity")
        if not delivered_qtys:
            delivered_qtys = request.form.getlist("quantity")

        if item_ids and delivered_qtys:
            for iid, qty in zip(item_ids, delivered_qtys):
                if qty is not None and str(qty).strip() != "":
                    deliveries.append({"item_id": iid, "quantity": qty})
        else:
            product_ids = request.form.getlist("product_id")
            if product_ids and delivered_qtys:
                for pid, qty in zip(product_ids, delivered_qtys):
                    if qty is not None and str(qty).strip() != "":
                        deliveries.append({"product_id": pid, "quantity": qty})
            else:
                # Check for individual inputs like quantity_<id> or delivered_quantity_<id>
                for key, val in request.form.items():
                    if val is not None and str(val).strip() != "":
                        if key.startswith("delivered_quantity_") or key.startswith("quantity_"):
                            raw_id = key.split("_")[-1]
                            deliveries.append({"item_id": raw_id, "quantity": val})
                        elif key.startswith("item_"):
                            raw_id = key.split("_")[-1]
                            deliveries.append({"item_id": raw_id, "quantity": val})

    try:
        updated_po = record_partial_delivery(po_id, deliveries)
        flash(
            f"Delivery recorded successfully for purchase order #{updated_po.id}.",
            "success",
        )
        if request.is_json:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Delivery recorded successfully.",
                        "purchase_order": updated_po.to_dict(),
                    }
                ),
                200,
            )
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))

    except PurchaseOrderValidationError as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to record delivery")
        if request.is_json:
            return jsonify({"error": "Failed to record delivery."}), 500
        flash("An error occurred while recording the delivery.", "error")
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))


@purchase_order_bp.route(
    "/purchase-orders/from-low-stock/<int:product_id>",
    methods=["GET", "POST"],
    endpoint="create_po_from_low_stock",
)
@purchase_order_bp.route(
    "/products/<int:product_id>/create-purchase-order",
    methods=["GET", "POST"],
    endpoint="create_po_from_product",
)
@manager_required
def create_po_from_low_stock_view(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        if request.is_json:
            return jsonify({"error": "Product not found."}), 404
        abort(404, description="Product not found.")

    if request.method == "GET":
        if request.is_json:
            return (
                jsonify(
                    {
                        "product_id": product.id,
                        "product_name": product.name,
                        "sku": product.sku,
                        "supplier_id": product.supplier_id,
                        "supplier_name": product.supplier.name
                        if product.supplier
                        else None,
                        "stock": product.stock,
                        "reorder_threshold": product.reorder_threshold,
                        "is_low_stock": product.is_low_stock,
                        "suggested_quantity": product.suggested_reorder_quantity,
                        "unit_price": str(product.price)
                        if product.price is not None
                        else None,
                    }
                ),
                200,
            )
        return redirect(
            url_for("purchase_order.create_purchase_order", product_id=product.id)
        )

    # POST request: create the purchase order directly
    raw_qty = None
    raw_supplier_id = None
    allow_duplicate = False

    if request.is_json:
        data = request.get_json(silent=True) or {}
        raw_qty = data.get("quantity")
        raw_supplier_id = data.get("supplier_id")
        allow_duplicate = bool(data.get("allow_duplicate", False))
    else:
        raw_qty = request.form.get("quantity")
        raw_supplier_id = request.form.get("supplier_id")
        allow_duplicate = request.form.get("allow_duplicate") == "true"

    try:
        po = create_purchase_order_from_low_stock(
            product_id=product_id,
            quantity=raw_qty,
            supplier_id=raw_supplier_id,
            allow_duplicate=allow_duplicate,
        )
        flash(
            f"Purchase order #{po.id} created successfully for {product.name}.",
            "success",
        )
        if request.is_json:
            return (
                jsonify(
                    {
                        "success": True,
                        "message": f"Purchase order #{po.id} created successfully.",
                        "purchase_order": po.to_dict(),
                        "purchase_order_url": url_for(
                            "purchase_order.view_purchase_order", po_id=po.id
                        ),
                    }
                ),
                201,
            )
        return redirect(url_for("purchase_order.view_purchase_order", po_id=po.id))

    except PurchaseOrderValidationError as exc:
        if request.is_json:
            return jsonify({"error": str(exc)}), 400
        flash(str(exc), "error")
        return redirect(request.referrer or url_for("main.home"))

    except Exception:
        db.session.rollback()
        current_app.logger.exception("Unable to create purchase order from low stock")
        if request.is_json:
            return jsonify({"error": "Failed to create purchase order."}), 500
        flash("An error occurred while creating the purchase order.", "error")
        return redirect(request.referrer or url_for("main.home"))
