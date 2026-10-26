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
from sqlalchemy.exc import IntegrityError

from app.data.extensions import db
from app.data.models import Supplier
from app.presentation.authz import admin_required

supplier_bp = Blueprint("supplier", __name__)


@supplier_bp.route("/suppliers", methods=["GET"], endpoint="list_suppliers")
@supplier_bp.route("/suppliers/list", methods=["GET"], endpoint="suppliers_list")
@admin_required
def list_suppliers():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("suppliers.html", suppliers=suppliers)


@supplier_bp.route("/suppliers/create", methods=["GET", "POST"], endpoint="create_supplier")
@supplier_bp.route("/suppliers/add", methods=["GET", "POST"], endpoint="add_supplier")
@supplier_bp.route("/suppliers/new", methods=["GET", "POST"], endpoint="new_supplier")
@admin_required
def create_supplier():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact_info = (
            request.form.get("contact_info")
            or request.form.get("contact_information")
            or request.form.get("contact")
            or ""
        ).strip()
        address = request.form.get("address", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            return render_template("create_supplier.html"), 400

        if len(name) > 200:
            flash("Supplier name must be 200 characters or fewer.", "error")
            return render_template("create_supplier.html"), 400

        if contact_info and len(contact_info) > 255:
            flash("Contact information must be 255 characters or fewer.", "error")
            return render_template("create_supplier.html"), 400

        if address and len(address) > 500:
            flash("Address must be 500 characters or fewer.", "error")
            return render_template("create_supplier.html"), 400

        if not contact_info and (email or phone):
            contact_parts = [p for p in (email, phone) if p]
            contact_info = ", ".join(contact_parts)

        supplier = Supplier(
            name=name,
            contact_info=contact_info if contact_info else None,
            address=address if address else None,
            email=email if email else None,
            phone=phone if phone else None,
        )
        db.session.add(supplier)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Could not save supplier.", "error")
            return render_template("create_supplier.html"), 400
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to create supplier")
            flash("The supplier could not be created. Please try again.", "error")
            return render_template("create_supplier.html"), 500

        flash("Supplier added successfully.", "success")
        return redirect(url_for("supplier.list_suppliers"))

    return render_template("create_supplier.html")


@supplier_bp.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"], endpoint="edit_supplier")
@supplier_bp.route("/suppliers/<int:supplier_id>/update", methods=["GET", "POST"], endpoint="update_supplier")
@admin_required
def edit_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        abort(404, description="Supplier not found.")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact_info = (
            request.form.get("contact_info")
            or request.form.get("contact_information")
            or request.form.get("contact")
            or ""
        ).strip()
        address = request.form.get("address", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            return render_template("edit_supplier.html", supplier=supplier), 400

        if len(name) > 200:
            flash("Supplier name must be 200 characters or fewer.", "error")
            return render_template("edit_supplier.html", supplier=supplier), 400

        if contact_info and len(contact_info) > 255:
            flash("Contact information must be 255 characters or fewer.", "error")
            return render_template("edit_supplier.html", supplier=supplier), 400

        if address and len(address) > 500:
            flash("Address must be 500 characters or fewer.", "error")
            return render_template("edit_supplier.html", supplier=supplier), 400

        if not contact_info and (email or phone):
            contact_parts = [p for p in (email, phone) if p]
            contact_info = ", ".join(contact_parts)

        supplier.name = name
        supplier.contact_info = contact_info if contact_info else None
        supplier.address = address if address else None
        if email:
            supplier.email = email
        if phone:
            supplier.phone = phone

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Could not update supplier.", "error")
            return render_template("edit_supplier.html", supplier=supplier), 400
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unable to update supplier")
            flash("The supplier could not be updated. Please try again.", "error")
            return render_template("edit_supplier.html", supplier=supplier), 500

        flash("Supplier updated successfully.", "success")
        return redirect(url_for("supplier.list_suppliers"))

    return render_template("edit_supplier.html", supplier=supplier)


@supplier_bp.route("/suppliers/<int:supplier_id>", methods=["GET"], endpoint="view_supplier")
@admin_required
def view_supplier(supplier_id):
    supplier = db.session.get(Supplier, supplier_id)
    if supplier is None:
        abort(404, description="Supplier not found.")
    return render_template("edit_supplier.html", supplier=supplier)
