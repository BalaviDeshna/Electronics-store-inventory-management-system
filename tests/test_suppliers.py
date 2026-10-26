import pytest
from app.data.extensions import db
from app.data.models import Supplier


# ==========================================
# 1. Model Unit Tests
# ==========================================


def test_supplier_model_creation_and_properties(app):
    with app.app_context():
        supplier = Supplier(
            name="Alpha Components",
            contact_info="alpha@example.com",
            address="123 Tech Park, San Jose, CA",
        )
        db.session.add(supplier)
        db.session.commit()

        loaded = db.session.get(Supplier, supplier.id)
        assert loaded is not None
        assert loaded.name == "Alpha Components"
        assert loaded.contact_info == "alpha@example.com"
        assert loaded.contact_information == "alpha@example.com"
        assert loaded.address == "123 Tech Park, San Jose, CA"

        # Test property setter
        loaded.contact_information = "support@alpha.com"
        db.session.commit()

        reloaded = db.session.get(Supplier, supplier.id)
        assert reloaded.contact_info == "support@alpha.com"
        assert reloaded.contact_information == "support@alpha.com"


def test_supplier_init_accepts_contact_information_kwarg(app):
    with app.app_context():
        supplier = Supplier(
            name="Beta Distributors",
            contact_information="beta@distro.com",
            address="456 Industrial Way, Austin, TX",
        )
        db.session.add(supplier)
        db.session.commit()

        loaded = db.session.get(Supplier, supplier.id)
        assert loaded.contact_info == "beta@distro.com"
        assert loaded.contact_information == "beta@distro.com"


def test_supplier_to_dict_and_repr(app):
    with app.app_context():
        supplier = Supplier(
            name="Gamma Electronics",
            contact_info="gamma@test.com",
            address="789 Silicon Ave",
        )
        db.session.add(supplier)
        db.session.commit()

        data = supplier.to_dict()
        assert data["name"] == "Gamma Electronics"
        assert data["contact_info"] == "gamma@test.com"
        assert data["contact_information"] == "gamma@test.com"
        assert data["address"] == "789 Silicon Ave"
        assert "Gamma Electronics" in repr(supplier)


# ==========================================
# 2. Authorization / Access Control Tests
# ==========================================


def test_suppliers_list_requires_authentication(client):
    response = client.get("/suppliers")
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")


def test_suppliers_list_rejects_staff(client, logged_in_staff):
    response = client.get("/suppliers")
    assert response.status_code == 403


def test_suppliers_list_rejects_manager(client, logged_in_manager):
    response = client.get("/suppliers")
    assert response.status_code == 403


def test_suppliers_list_allows_admin(client, logged_in_admin):
    response = client.get("/suppliers")
    assert response.status_code == 200
    assert b"Suppliers" in response.data


def test_create_supplier_get_requires_admin(client, logged_in_staff):
    # Unauthenticated -> redirect
    client.post("/logout")
    resp_anon = client.get("/suppliers/create")
    assert resp_anon.status_code == 302

    # Staff -> 403
    client.post("/login", data={"username": "test-staff", "password": "StaffPass123"})
    resp_staff = client.get("/suppliers/create")
    assert resp_staff.status_code == 403


def test_create_supplier_post_requires_admin(client, logged_in_staff):
    # Staff cannot POST
    response = client.post(
        "/suppliers/create",
        data={"name": "Hacked Supplier", "contact_info": "hack@test.com"},
    )
    assert response.status_code == 403
    assert Supplier.query.filter_by(name="Hacked Supplier").first() is None


def test_edit_supplier_requires_admin(client, logged_in_staff):
    supplier = Supplier(name="Target Supplier")
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    # Staff cannot GET edit
    resp_get = client.get(f"/suppliers/{supplier_id}/edit")
    assert resp_get.status_code == 403

    # Staff cannot POST edit
    resp_post = client.post(
        f"/suppliers/{supplier_id}/edit",
        data={"name": "Modified by Staff"},
    )
    assert resp_post.status_code == 403
    assert db.session.get(Supplier, supplier_id).name == "Target Supplier"


# ==========================================
# 3. Create (Add) Supplier Tests
# ==========================================


def test_admin_can_create_supplier_with_all_fields(client, logged_in_admin):
    response = client.post(
        "/suppliers/create",
        data={
            "name": "Pacific Microchips",
            "contact_info": "sales@pacificmicro.com | +1-800-555-0123",
            "address": "500 Ocean Blvd, Seattle, WA 98101",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Supplier added successfully." in response.data or b"Supplier created successfully." in response.data

    supplier = Supplier.query.filter_by(name="Pacific Microchips").first()
    assert supplier is not None
    assert supplier.contact_info == "sales@pacificmicro.com | +1-800-555-0123"
    assert supplier.address == "500 Ocean Blvd, Seattle, WA 98101"


def test_admin_can_create_supplier_with_contact_information_field(client, logged_in_admin):
    response = client.post(
        "/suppliers/create",
        data={
            "name": "Nordic Semiconductors",
            "contact_information": "nordic@supplier.se",
            "address": "Kungsgatan 12, Stockholm",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    supplier = Supplier.query.filter_by(name="Nordic Semiconductors").first()
    assert supplier is not None
    assert supplier.contact_info == "nordic@supplier.se"
    assert supplier.contact_information == "nordic@supplier.se"


def test_admin_can_create_supplier_with_name_only(client, logged_in_admin):
    response = client.post(
        "/suppliers/create",
        data={"name": "Minimal Supplier"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    supplier = Supplier.query.filter_by(name="Minimal Supplier").first()
    assert supplier is not None
    assert supplier.contact_info is None
    assert supplier.address is None


def test_create_supplier_rejects_empty_name(client, logged_in_admin):
    response = client.post(
        "/suppliers/create",
        data={"name": "   ", "contact_info": "test@info.com"},
    )
    assert response.status_code in (400, 200)
    assert b"Supplier name is required." in response.data
    assert Supplier.query.count() == 0


def test_create_supplier_rejects_missing_name(client, logged_in_admin):
    response = client.post(
        "/suppliers/create",
        data={"contact_info": "test@info.com"},
    )
    assert response.status_code in (400, 200)
    assert b"Supplier name is required." in response.data
    assert Supplier.query.count() == 0


def test_create_supplier_rejects_name_over_200_chars(client, logged_in_admin):
    long_name = "A" * 201
    response = client.post(
        "/suppliers/create",
        data={"name": long_name},
    )
    assert response.status_code in (400, 200)
    assert b"Supplier name must be 200 characters or fewer." in response.data
    assert Supplier.query.count() == 0


def test_create_supplier_rejects_contact_info_over_255_chars(client, logged_in_admin):
    long_contact = "c" * 256
    response = client.post(
        "/suppliers/create",
        data={"name": "Valid Name", "contact_info": long_contact},
    )
    assert response.status_code in (400, 200)
    assert b"Contact information must be 255 characters or fewer." in response.data
    assert Supplier.query.count() == 0


def test_create_supplier_rejects_address_over_500_chars(client, logged_in_admin):
    long_address = "d" * 501
    response = client.post(
        "/suppliers/create",
        data={"name": "Valid Name", "address": long_address},
    )
    assert response.status_code in (400, 200)
    assert b"Address must be 500 characters or fewer." in response.data
    assert Supplier.query.count() == 0


def test_create_supplier_via_add_alias(client, logged_in_admin):
    response = client.post(
        "/suppliers/add",
        data={"name": "Alias Supplier", "contact_info": "alias@test.com"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert Supplier.query.filter_by(name="Alias Supplier").first() is not None


# ==========================================
# 4. Edit (Update) Supplier Tests
# ==========================================


def test_admin_can_edit_supplier_details(client, logged_in_admin):
    supplier = Supplier(
        name="Original Supplier",
        contact_info="orig@supplier.com",
        address="100 Old St",
    )
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    response = client.post(
        f"/suppliers/{supplier_id}/edit",
        data={
            "name": "Updated Supplier Inc",
            "contact_info": "updated@supplier.com",
            "address": "200 New Ave, Suite 10",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Supplier updated successfully." in response.data

    updated = db.session.get(Supplier, supplier_id)
    assert updated.name == "Updated Supplier Inc"
    assert updated.contact_info == "updated@supplier.com"
    assert updated.address == "200 New Ave, Suite 10"


def test_admin_can_edit_supplier_via_update_alias(client, logged_in_admin):
    supplier = Supplier(name="Alias Edit Co", contact_info="co@test.com")
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    response = client.post(
        f"/suppliers/{supplier_id}/update",
        data={
            "name": "Alias Edit Co Updated",
            "contact_info": "newco@test.com",
            "address": "Updated Address",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Supplier updated successfully." in response.data

    updated = db.session.get(Supplier, supplier_id)
    assert updated.name == "Alias Edit Co Updated"
    assert updated.contact_info == "newco@test.com"
    assert updated.address == "Updated Address"


def test_edit_supplier_rejects_empty_name(client, logged_in_admin):
    supplier = Supplier(name="Keep This Name")
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    response = client.post(
        f"/suppliers/{supplier_id}/edit",
        data={"name": "   "},
    )
    assert response.status_code in (400, 200)
    assert b"Supplier name is required." in response.data
    assert db.session.get(Supplier, supplier_id).name == "Keep This Name"


def test_edit_supplier_rejects_name_over_200_chars(client, logged_in_admin):
    supplier = Supplier(name="Valid Before Edit")
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    response = client.post(
        f"/suppliers/{supplier_id}/edit",
        data={"name": "Z" * 201},
    )
    assert response.status_code in (400, 200)
    assert b"Supplier name must be 200 characters or fewer." in response.data
    assert db.session.get(Supplier, supplier_id).name == "Valid Before Edit"


def test_edit_supplier_rejects_contact_info_over_255_chars(client, logged_in_admin):
    supplier = Supplier(name="Valid Supplier")
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    response = client.post(
        f"/suppliers/{supplier_id}/edit",
        data={"name": "Valid Supplier", "contact_info": "X" * 256},
    )
    assert response.status_code in (400, 200)
    assert b"Contact information must be 255 characters or fewer." in response.data


def test_edit_supplier_rejects_address_over_500_chars(client, logged_in_admin):
    supplier = Supplier(name="Valid Supplier")
    db.session.add(supplier)
    db.session.commit()
    supplier_id = supplier.id

    response = client.post(
        f"/suppliers/{supplier_id}/edit",
        data={"name": "Valid Supplier", "address": "Y" * 501},
    )
    assert response.status_code in (400, 200)
    assert b"Address must be 500 characters or fewer." in response.data


def test_edit_supplier_404_for_nonexistent_supplier(client, logged_in_admin):
    response = client.get("/suppliers/999999/edit")
    assert response.status_code == 404

    resp_post = client.post("/suppliers/999999/edit", data={"name": "Ghost"})
    assert resp_post.status_code == 404


# ==========================================
# 5. UI and Listing Tests
# ==========================================


def test_suppliers_list_displays_all_suppliers_ordered_by_name(client, logged_in_admin):
    s1 = Supplier(name="Zeta Logistics", contact_info="zeta@test.com", address="Zeta Rd")
    s2 = Supplier(name="Apex Parts", contact_info="apex@test.com", address="Apex St")
    s3 = Supplier(name="Midwest Electronics", contact_info="midwest@test.com", address="Midwest Ave")
    db.session.add_all([s1, s2, s3])
    db.session.commit()

    response = client.get("/suppliers")
    assert response.status_code == 200
    assert b"Apex Parts" in response.data
    assert b"Midwest Electronics" in response.data
    assert b"Zeta Logistics" in response.data

    # Verify alphabetical ordering in rendered table
    apex_pos = response.data.find(b"Apex Parts")
    midwest_pos = response.data.find(b"Midwest Electronics")
    zeta_pos = response.data.find(b"Zeta Logistics")
    assert apex_pos < midwest_pos < zeta_pos


def test_suppliers_list_empty_state(client, logged_in_admin):
    response = client.get("/suppliers")
    assert response.status_code == 200
    assert b"No suppliers found" in response.data


def test_view_supplier_route(client, logged_in_admin):
    supplier = Supplier(name="Direct View Supplier", contact_info="view@test.com", address="100 View St")
    db.session.add(supplier)
    db.session.commit()

    response = client.get(f"/suppliers/{supplier.id}")
    assert response.status_code == 200
    assert b"Direct View Supplier" in response.data
    assert b"view@test.com" in response.data
