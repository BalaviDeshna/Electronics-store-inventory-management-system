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
    receive_purchase_order,
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

    return render_template(
        "create_purchase_order.html",
        suppliers=suppliers,
        products=products,
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
