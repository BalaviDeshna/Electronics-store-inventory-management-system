from flask import Blueprint, render_template

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
