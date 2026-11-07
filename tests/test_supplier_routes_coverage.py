import pytest
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError

from app.data.extensions import db
from app.data.models import Supplier


def test_supplier_routes_coverage(app, client, logged_in_admin):
    # GET /suppliers/new
    r = client.get("/suppliers/new")
    assert r.status_code == 200

    # POST create supplier with empty contact_info, providing email and phone -> triggers lines 62-63
    r = client.post("/suppliers/create", data={
        "name": "Auto Contact Supplier",
        "contact_info": "",
        "email": "auto@supplier.com",
        "phone": "123-456-7890",
    })
    assert r.status_code == 302
    with app.app_context():
        s = Supplier.query.filter_by(name="Auto Contact Supplier").first()
        assert s is not None
        assert "auto@supplier.com, 123-456-7890" in s.contact_info
        assert s.email == "auto@supplier.com"
        assert s.phone == "123-456-7890"
        sid = s.id

    # IntegrityError in create_supplier -> lines 75-78
    with patch("app.data.extensions.db.session.commit", side_effect=IntegrityError("stmt", "params", "orig")):
        r = client.post("/suppliers/create", data={
            "name": "Integ Supplier",
            "contact_info": "Info",
        })
        assert r.status_code == 400

    # Exception in create_supplier -> lines 79-83
    with patch("app.data.extensions.db.session.commit", side_effect=RuntimeError("create fail")):
        r = client.post("/suppliers/create", data={
            "name": "Err Supplier",
            "contact_info": "Info",
        })
        assert r.status_code == 500

    # GET /suppliers/<id>/edit -> line 154
    r = client.get(f"/suppliers/{sid}/edit")
    assert r.status_code == 200

    # POST edit supplier with empty contact_info, providing email and phone -> lines 128-129, 135, 137
    r = client.post(f"/suppliers/{sid}/edit", data={
        "name": "Updated Supplier Name",
        "contact_info": "",
        "email": "updated@supplier.com",
        "phone": "987-654-3210",
    })
    assert r.status_code == 302
    with app.app_context():
        s_fresh = db.session.get(Supplier, sid)
        assert s_fresh.name == "Updated Supplier Name"
        assert s_fresh.email == "updated@supplier.com"
        assert s_fresh.phone == "987-654-3210"

    # IntegrityError in edit_supplier -> lines 141-144
    with patch("app.data.extensions.db.session.commit", side_effect=IntegrityError("stmt", "params", "orig")):
        r = client.post(f"/suppliers/{sid}/edit", data={
            "name": "Integ Edit",
            "contact_info": "Info",
        })
        assert r.status_code == 400

    # Exception in edit_supplier -> lines 145-149
    with patch("app.data.extensions.db.session.commit", side_effect=RuntimeError("edit fail")):
        r = client.post(f"/suppliers/{sid}/edit", data={
            "name": "Err Edit",
            "contact_info": "Info",
        })
        assert r.status_code == 500

    # GET /suppliers/<id> nonexistent -> line 162
    r = client.get("/suppliers/99999")
    assert r.status_code == 404

