
from decimal import Decimal
from app.data.extensions import db
from app.data.models.product import Product
from app.data.models.audit_log import AuditLog


def test_create_product_page_loads(client):
    response = client.get("/products/create")

    assert response.status_code == 200
    assert b"Create Product" in response.data
    assert b"Product name" in response.data


def test_create_product_success(client):
    response = client.post(
        "/products/create",
        data={"name": "Wireless Mouse", "price": "799.99", "stock": "10"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    product = db.session.execute(
        db.select(Product).filter_by(name="Wireless Mouse")
    ).scalar_one()

    assert product.price == Decimal("799.99")
    assert product.stock == 10


def test_create_product_rejects_empty_name(client):
    response = client.post(
        "/products/create",
        data={"name": "  ", "price": "100.00", "stock": "5"},
    )

    assert response.status_code == 200
    assert b"Product name is required." in response.data
    assert db.session.execute(db.select(Product)).scalars().all() == []


def test_create_product_rejects_negative_price(client):
    response = client.post(
        "/products/create",
        data={"name": "Keyboard", "price": "-10", "stock": "5"},
    )

    assert response.status_code == 200
    assert b"Enter a valid, non-negative price." in response.data
    assert db.session.execute(db.select(Product)).scalars().all() == []


def test_create_product_rejects_negative_stock(client):
    response = client.post(
        "/products/create",
        data={"name": "Keyboard", "price": "100", "stock": "-1"},
    )

    assert response.status_code == 200
    assert b"Stock must be a non-negative whole number." in response.data
    assert db.session.execute(db.select(Product)).scalars().all() == []


def test_edit_product_page_loads(client):
    product = Product(name="Gaming Mouse", price=Decimal("120.00"), stock=15)
    db.session.add(product)
    db.session.commit()

    response = client.get(f"/products/{product.id}/edit")

    assert response.status_code == 200
    assert b"Edit Product" in response.data
    assert b"Gaming Mouse" in response.data
    assert b"120.00" in response.data
    assert b"15" in response.data


def test_update_product_success(client):
    product = Product(name="Gaming Mouse", price=Decimal("120.00"), stock=15)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Pro Gaming Mouse", "price": "149.99", "stock": "20"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated_product = db.session.get(Product, product_id)
    assert updated_product.name == "Pro Gaming Mouse"
    assert updated_product.price == Decimal("149.99")
    assert updated_product.stock == 20


def test_update_product_preserves_id_and_does_not_create_duplicate(client):
    product = Product(name="Headphones", price=Decimal("89.99"), stock=8)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Wireless Headphones", "price": "99.99", "stock": "10"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    all_products = db.session.execute(db.select(Product)).scalars().all()
    assert len(all_products) == 1
    assert all_products[0].id == product_id
    assert all_products[0].name == "Wireless Headphones"


def test_update_product_rejects_empty_name(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "   ", "price": "55.00", "stock": "7"},
    )

    assert response.status_code == 200
    assert b"Product name is required." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_name_exceeding_max_length(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "A" * 201, "price": "55.00", "stock": "7"},
    )

    assert response.status_code == 200
    assert b"Product name must be 200 characters or fewer." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_negative_price(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Mechanical Keyboard", "price": "-20.00", "stock": "5"},
    )

    assert response.status_code == 200
    assert b"Enter a valid, non-negative price." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_negative_stock(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Mechanical Keyboard", "price": "60.00", "stock": "-1"},
    )

    assert response.status_code == 200
    assert b"Stock must be a non-negative whole number." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.name == "Keyboard"
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_product_rejects_invalid_price_and_stock(client):
    product = Product(name="Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    resp_price = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Keyboard", "price": "not-a-price", "stock": "5"},
    )
    assert resp_price.status_code == 200
    assert b"Enter a valid, non-negative price." in resp_price.data

    resp_stock = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Keyboard", "price": "50.00", "stock": "not-an-int"},
    )
    assert resp_stock.status_code == 200
    assert b"Stock must be a non-negative whole number." in resp_stock.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.price == Decimal("50.00")
    assert unchanged.stock == 5


def test_update_nonexistent_product_returns_404(client):
    resp_get = client.get("/products/999999/edit")
    assert resp_get.status_code == 404
    assert b"Product not found." in resp_get.data

    resp_post = client.post(
        "/products/999999/edit",
        data={"name": "Ghost", "price": "10.00", "stock": "1"},
    )
    assert resp_post.status_code == 404
    assert b"Product not found." in resp_post.data


def test_update_product_via_update_route(client):
    product = Product(name="Webcam", price=Decimal("45.00"), stock=6)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    resp_get = client.get(f"/products/{product_id}/update")
    assert resp_get.status_code == 200
    assert b"Webcam" in resp_get.data

    resp_post = client.post(
        f"/products/{product_id}/update",
        data={"name": "HD Webcam", "price": "55.00", "stock": "10"},
        follow_redirects=True,
    )
    assert resp_post.status_code == 200
    assert b"Product updated successfully." in resp_post.data

    updated = db.session.get(Product, product_id)
    assert updated.name == "HD Webcam"
    assert updated.price == Decimal("55.00")
    assert updated.stock == 10


def test_delete_action_is_available_for_existing_product(client):
    product = Product(name="Wireless Earbuds", price=Decimal("49.99"), stock=10)
    db.session.add(product)
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert f"/products/{product.id}/delete".encode() in response.data
    assert b"Delete" in response.data
    assert b"confirm(" in response.data

    edit_response = client.get(f"/products/{product.id}/edit")
    assert edit_response.status_code == 200
    assert f"/products/{product.id}/delete".encode() in edit_response.data


def test_delete_product_success(client):
    product = Product(name="To Delete", price=Decimal("19.99"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(f"/products/{product_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Product deleted successfully." in response.data

    deleted = db.session.get(Product, product_id)
    assert deleted is None


def test_delete_nonexistent_product_returns_404(client):
    response = client.post("/products/999999/delete")
    assert response.status_code == 404
    assert b"Product not found." in response.data


def test_repeated_deletion_returns_404(client):
    product = Product(name="Single Use", price=Decimal("9.99"), stock=2)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    res1 = client.post(f"/products/{product_id}/delete", follow_redirects=True)
    assert res1.status_code == 200
    assert b"Product deleted successfully." in res1.data

    res2 = client.post(f"/products/{product_id}/delete")
    assert res2.status_code == 404
    assert b"Product not found." in res2.data


def test_delete_product_rejects_get_request(client):
    product = Product(name="Safe Product", price=Decimal("29.99"), stock=4)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.get(f"/products/{product_id}/delete")
    assert response.status_code in (405, 302, 400)

    still_exists = db.session.get(Product, product_id)
    assert still_exists is not None


def test_failed_deletion_rolls_back_cleanly(client, monkeypatch):
    product = Product(name="Error Product", price=Decimal("15.00"), stock=3)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    def mock_commit():
        raise Exception("Database failure simulation")

    monkeypatch.setattr(db.session, "commit", mock_commit)

    response = client.post(f"/products/{product_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"The product could not be deleted. Please try again." in response.data

    monkeypatch.undo()
    still_exists = db.session.get(Product, product_id)
    assert still_exists is not None


def test_delete_product_with_sales_history_is_rejected_and_preserves_records(client):
    from app.business.sales import create_sale

    product = Product(name="Historical Item", price=Decimal("100.00"), stock=10)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    sale = create_sale([{"product_id": product_id, "quantity": 2}], Product)
    sale_id = sale.id

    response = client.post(f"/products/{product_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Cannot delete product with existing sales records." in response.data

    still_exists = db.session.get(Product, product_id)
    assert still_exists is not None
    assert still_exists.name == "Historical Item"

    invoice_resp = client.get(f"/sales/{sale_id}/invoice")
    assert invoice_resp.status_code == 200
    assert b"Sales Invoice" in invoice_resp.data
    assert b"Historical Item" in invoice_resp.data
    assert b"200.00" in invoice_resp.data


def test_search_by_exact_product_name(client):
    p1 = Product(name="Wireless Mouse", sku="MOU-001", price=Decimal("25.00"), stock=10)
    p2 = Product(name="Mechanical Keyboard", sku="KEY-001", price=Decimal("75.00"), stock=5)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?q=Wireless+Mouse")
    assert response.status_code == 200
    assert b"Wireless Mouse" in response.data
    assert b"MOU-001" in response.data
    assert b"KEY-001" not in response.data


def test_search_by_partial_product_name(client):
    p1 = Product(name="Wireless Mouse", sku="MOU-001", price=Decimal("25.00"), stock=10)
    p2 = Product(name="Mechanical Keyboard", sku="KEY-001", price=Decimal("75.00"), stock=5)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?q=mouse")
    assert response.status_code == 200
    assert b"Wireless Mouse" in response.data
    assert b"KEY-001" not in response.data


def test_search_by_exact_sku(client):
    p1 = Product(name="Wireless Mouse", sku="MOU-001", price=Decimal("25.00"), stock=10)
    p2 = Product(name="Mechanical Keyboard", sku="KEY-001", price=Decimal("75.00"), stock=5)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?q=MOU-001")
    assert response.status_code == 200
    assert b"Wireless Mouse" in response.data
    assert b"KEY-001" not in response.data


def test_search_by_partial_sku(client):
    p1 = Product(name="Wireless Mouse", sku="MOU-001", price=Decimal("25.00"), stock=10)
    p2 = Product(name="Mechanical Keyboard", sku="KEY-001", price=Decimal("75.00"), stock=5)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?q=KEY")
    assert response.status_code == 200
    assert b"Mechanical Keyboard" in response.data
    assert b"MOU-001" not in response.data


def test_search_case_insensitive(client):
    p1 = Product(name="Gaming Headset", sku="HEAD-PRO-9", price=Decimal("59.99"), stock=4)
    db.session.add(p1)
    db.session.commit()

    res_name = client.get("/?q=gAmInG")
    assert res_name.status_code == 200
    assert b"Gaming Headset" in res_name.data

    res_sku = client.get("/?q=head-pro-9")
    assert res_sku.status_code == 200
    assert b"Gaming Headset" in res_sku.data


def test_search_matches_either_name_or_sku(client):
    p1 = Product(name="Studio Monitor", sku="SPEAKER-01", price=Decimal("150.00"), stock=2)
    p2 = Product(name="Desktop Mic", sku="MONITOR-AUDIO", price=Decimal("80.00"), stock=3)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?q=monitor")
    assert response.status_code == 200
    assert b"Studio Monitor" in response.data
    assert b"Desktop Mic" in response.data


def test_search_trims_whitespace_and_preserves_input(client):
    p1 = Product(name="USB Hub", sku="HUB-4PORT", price=Decimal("15.00"), stock=12)
    db.session.add(p1)
    db.session.commit()

    response = client.get("/?q=+++USB+Hub+++")
    assert response.status_code == 200
    assert b"USB Hub" in response.data
    assert b'value="USB Hub"' in response.data


def test_search_no_matching_results(client):
    p1 = Product(name="USB Hub", sku="HUB-4PORT", price=Decimal("15.00"), stock=12)
    db.session.add(p1)
    db.session.commit()

    response = client.get("/?q=NonexistentDevice12345")
    assert response.status_code == 200
    assert b"No products found matching your search." in response.data
    assert b"Clear search" in response.data
    assert b"HUB-4PORT" not in response.data


def test_empty_search_shows_all_products(client):
    p1 = Product(name="Item One", sku="SKU-1", price=Decimal("10.00"), stock=1)
    p2 = Product(name="Item Two", sku="SKU-2", price=Decimal("20.00"), stock=2)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?q=+++")
    assert response.status_code == 200
    assert b"Item One" in response.data
    assert b"Item Two" in response.data


def test_create_product_with_sku_success(client):
    response = client.post(
        "/products/create",
        data={
            "name": "Bluetooth Speaker",
            "sku": "SPK-BT-100",
            "price": "39.99",
            "stock": "20",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    created = db.session.execute(
        db.select(Product).filter_by(name="Bluetooth Speaker")
    ).scalar_one()
    assert created.sku == "SPK-BT-100"


def test_create_product_rejects_duplicate_sku(client):
    p1 = Product(name="First Item", sku="UNIQUE-SKU", price=Decimal("10.00"), stock=5)
    db.session.add(p1)
    db.session.commit()

    response = client.post(
        "/products/create",
        data={
            "name": "Second Item",
            "sku": "UNIQUE-SKU",
            "price": "20.00",
            "stock": "3",
        },
    )
    assert response.status_code == 200
    assert b"A product with this SKU already exists." in response.data

    items = db.session.execute(db.select(Product).filter_by(sku="UNIQUE-SKU")).scalars().all()
    assert len(items) == 1
    assert items[0].name == "First Item"


def test_edit_product_with_sku_success(client):
    product = Product(name="Webcam", sku="CAM-720P", price=Decimal("30.00"), stock=4)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "HD Webcam 1080P",
            "sku": "CAM-1080P",
            "price": "45.00",
            "stock": "6",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.sku == "CAM-1080P"
    assert updated.name == "HD Webcam 1080P"


def test_edit_product_rejects_duplicate_sku(client):
    p1 = Product(name="Item A", sku="SKU-AAA", price=Decimal("10.00"), stock=2)
    p2 = Product(name="Item B", sku="SKU-BBB", price=Decimal("15.00"), stock=3)
    db.session.add_all([p1, p2])
    db.session.commit()
    p2_id = p2.id

    response = client.post(
        f"/products/{p2_id}/edit",
        data={
            "name": "Item B Modified",
            "sku": "SKU-AAA",
            "price": "18.00",
            "stock": "3",
        },
    )
    assert response.status_code == 200
    assert b"A product with this SKU already exists." in response.data

    unchanged = db.session.get(Product, p2_id)
    assert unchanged.sku == "SKU-BBB"
    assert unchanged.name == "Item B"


def test_edit_product_allows_retaining_same_sku(client):
    product = Product(name="Tablet", sku="TAB-001", price=Decimal("200.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Tablet Pro",
            "sku": "TAB-001",
            "price": "220.00",
            "stock": "5",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.name == "Tablet Pro"
    assert updated.sku == "TAB-001"


def test_sku_displayed_in_inventory_table(client):
    product = Product(name="Power Bank", sku="PB-20000", price=Decimal("29.99"), stock=15)
    db.session.add(product)
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"PB-20000" in response.data
    assert b"Power Bank" in response.data


def test_category_displayed_in_inventory_table(client):
    product = Product(name="Smart Watch", sku="SW-01", category="Wearables", price=Decimal("199.99"), stock=8)
    db.session.add(product)
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Wearables" in response.data
    assert b"Smart Watch" in response.data


def test_filter_by_category_exact(client):
    p1 = Product(name="Noise Cancelling Headphones", sku="AUDIO-01", category="Audio", price=Decimal("250.00"), stock=5)
    p2 = Product(name="Gaming Laptop", sku="COMP-01", category="Computers", price=Decimal("1200.00"), stock=3)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?category=Audio")
    assert response.status_code == 200
    assert b"<td>Noise Cancelling Headphones</td>" in response.data
    assert b"<td>Gaming Laptop</td>" not in response.data
    assert b"COMP-01" not in response.data


def test_filter_by_category_case_insensitive(client):
    p1 = Product(name="Galaxy S24", sku="PHONE-01", category="Smartphones", price=Decimal("899.99"), stock=10)
    db.session.add(p1)
    db.session.commit()

    response = client.get("/?category=smartphones")
    assert response.status_code == 200
    assert b"<td>Galaxy S24</td>" in response.data


def test_filter_by_category_preserves_selected_option(client):
    p1 = Product(name="Headset", sku="HEAD-01", category="Audio", price=Decimal("49.99"), stock=4)
    db.session.add(p1)
    db.session.commit()

    response = client.get("/?category=Audio")
    assert response.status_code == 200
    assert b'<option value="Audio" selected>Audio</option>' in response.data or b'selected>Audio</option>' in response.data


def test_filter_by_stock_status_in_stock(client):
    p1 = Product(name="In Stock Mouse", sku="STK-IN", price=Decimal("20.00"), stock=10)
    p2 = Product(name="Out of Stock Keyboard", sku="STK-OUT", price=Decimal("50.00"), stock=0)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?stock_status=in_stock")
    assert response.status_code == 200
    assert b"<td>In Stock Mouse</td>" in response.data
    assert b"<td>Out of Stock Keyboard</td>" not in response.data
    assert b"STK-OUT" not in response.data


def test_filter_by_stock_status_out_of_stock(client):
    p1 = Product(name="In Stock Mouse", sku="STK-IN", price=Decimal("20.00"), stock=10)
    p2 = Product(name="Out of Stock Keyboard", sku="STK-OUT", price=Decimal("50.00"), stock=0)
    db.session.add_all([p1, p2])
    db.session.commit()

    response = client.get("/?stock_status=out_of_stock")
    assert response.status_code == 200
    assert b"<td>Out of Stock Keyboard</td>" in response.data
    assert b"<td>In Stock Mouse</td>" not in response.data
    assert b"STK-IN" not in response.data


def test_filter_by_stock_status_low_stock(client):
    p_low1 = Product(name="Low Stock Item 1", sku="LOW-1", price=Decimal("10.00"), stock=1)
    p_low5 = Product(name="Low Stock Item 5", sku="LOW-5", price=Decimal("15.00"), stock=5)
    p_plenty = Product(name="Plenty Stock Item", sku="PLENTY-20", price=Decimal("20.00"), stock=20)
    p_out = Product(name="No Stock Item", sku="NO-0", price=Decimal("30.00"), stock=0)
    db.session.add_all([p_low1, p_low5, p_plenty, p_out])
    db.session.commit()

    response = client.get("/?stock_status=low_stock")
    assert response.status_code == 200
    assert b"<td>Low Stock Item 1</td>" in response.data
    assert b"<td>Low Stock Item 5</td>" in response.data
    assert b"<td>Plenty Stock Item</td>" not in response.data
    assert b"<td>No Stock Item</td>" not in response.data
    assert b"PLENTY-20" not in response.data
    assert b"NO-0" not in response.data


def test_filter_by_combined_category_and_stock_status(client):
    p1 = Product(name="Pro Mouse", sku="PRO-MOU", category="Accessories", price=Decimal("50.00"), stock=3)
    p2 = Product(name="Old Mouse", sku="OLD-MOU", category="Accessories", price=Decimal("15.00"), stock=0)
    p3 = Product(name="Gaming Monitor", sku="DISP-01", category="Displays", price=Decimal("300.00"), stock=4)
    db.session.add_all([p1, p2, p3])
    db.session.commit()

    response = client.get("/?category=Accessories&stock_status=in_stock")
    assert response.status_code == 200
    assert b"<td>Pro Mouse</td>" in response.data
    assert b"<td>Old Mouse</td>" not in response.data
    assert b"<td>Gaming Monitor</td>" not in response.data
    assert b"OLD-MOU" not in response.data
    assert b"DISP-01" not in response.data


def test_filter_combined_with_search_query(client):
    p1 = Product(name="Gaming Mouse", sku="GM-01", category="Accessories", price=Decimal("60.00"), stock=8)
    p2 = Product(name="Gaming Laptop", sku="GL-01", category="Computers", price=Decimal("1500.00"), stock=5)
    p3 = Product(name="Office Mouse", sku="OM-01", category="Accessories", price=Decimal("20.00"), stock=10)
    db.session.add_all([p1, p2, p3])
    db.session.commit()

    response = client.get("/?q=Gaming&category=Accessories&stock_status=in_stock")
    assert response.status_code == 200
    assert b"<td>Gaming Mouse</td>" in response.data
    assert b"<td>Gaming Laptop</td>" not in response.data
    assert b"<td>Office Mouse</td>" not in response.data
    assert b"GL-01" not in response.data
    assert b"OM-01" not in response.data


def test_filter_empty_results_shows_message_and_clear_filters(client):
    p1 = Product(name="USB Cable", sku="CABLE-01", category="Accessories", price=Decimal("5.00"), stock=10)
    db.session.add(p1)
    db.session.commit()

    response = client.get("/?category=Appliances")
    assert response.status_code == 200
    assert b"No products found matching your filters." in response.data
    assert b"Clear filters" in response.data
    assert b"<td>USB Cable</td>" not in response.data
    assert b"CABLE-01" not in response.data


def test_invalid_stock_status_ignored_safely(client):
    p1 = Product(name="Monitor", price=Decimal("200.00"), stock=5)
    db.session.add(p1)
    db.session.commit()

    response = client.get("/?stock_status=invalid_random_status")
    assert response.status_code == 200
    assert b"Monitor" in response.data


def test_categories_dropdown_lists_distinct_categories(client):
    p1 = Product(name="Mouse", category="Peripherals", price=Decimal("20.00"), stock=5)
    p2 = Product(name="Keyboard", category="Peripherals", price=Decimal("50.00"), stock=3)
    p3 = Product(name="Speakers", category="Audio", price=Decimal("80.00"), stock=2)
    p4 = Product(name="Generic Cable", category=None, price=Decimal("10.00"), stock=10)
    db.session.add_all([p1, p2, p3, p4])
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b'value="Peripherals"' in response.data
    assert b'value="Audio"' in response.data


def test_create_product_with_category_success(client):
    response = client.post(
        "/products/create",
        data={
            "name": "Noise Cancelling Earbuds",
            "sku": "EAR-NC-100",
            "category": "Audio",
            "price": "129.99",
            "stock": "15",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    created = db.session.execute(
        db.select(Product).filter_by(name="Noise Cancelling Earbuds")
    ).scalar_one()
    assert created.category == "Audio"
    assert created.sku == "EAR-NC-100"


def test_edit_product_with_category_success(client):
    product = Product(name="Microphone", sku="MIC-001", category="Audio", price=Decimal("79.99"), stock=7)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Studio Microphone",
            "sku": "MIC-001",
            "category": "Studio Equipment",
            "price": "99.99",
            "stock": "7",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.name == "Studio Microphone"
    assert updated.category == "Studio Equipment"


# --- US-22: Configure Reorder Thresholds per Product Tests ---


def test_product_model_reorder_threshold_default_and_storage(client):
    product = Product(name="Desk Fan", price=Decimal("29.99"), stock=10)
    db.session.add(product)
    db.session.commit()

    saved = db.session.get(Product, product.id)
    assert saved.reorder_threshold == 0

    saved.reorder_threshold = 8
    db.session.commit()

    reloaded = db.session.get(Product, product.id)
    assert reloaded.reorder_threshold == 8


def test_product_model_check_constraint_rejects_negative_threshold(client):
    from sqlalchemy.exc import IntegrityError
    product = Product(name="Bad Product", price=Decimal("10.00"), stock=5, reorder_threshold=-2)
    db.session.add(product)
    try:
        db.session.commit()
        assert False, "Expected IntegrityError on negative reorder_threshold"
    except IntegrityError:
        db.session.rollback()


def test_create_product_page_shows_reorder_threshold_field(client):
    response = client.get("/products/create")
    assert response.status_code == 200
    assert b"Reorder threshold" in response.data
    assert b'name="reorder_threshold"' in response.data


def test_create_product_with_reorder_threshold_success(client):
    response = client.post(
        "/products/create",
        data={
            "name": "Mechanical Keyboard",
            "price": "89.99",
            "stock": "25",
            "reorder_threshold": "12",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    product = db.session.execute(
        db.select(Product).filter_by(name="Mechanical Keyboard")
    ).scalar_one()
    assert product.reorder_threshold == 12
    assert product.stock == 25


def test_create_product_defaults_reorder_threshold_to_zero_when_omitted(client):
    response = client.post(
        "/products/create",
        data={
            "name": "USB-C Hub",
            "price": "39.99",
            "stock": "14",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    product = db.session.execute(
        db.select(Product).filter_by(name="USB-C Hub")
    ).scalar_one()
    assert product.reorder_threshold == 0


def test_create_product_rejects_negative_reorder_threshold(client):
    response = client.post(
        "/products/create",
        data={
            "name": "Webcam",
            "price": "59.99",
            "stock": "10",
            "reorder_threshold": "-3",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data
    assert db.session.execute(db.select(Product).filter_by(name="Webcam")).scalar_one_or_none() is None


def test_create_product_rejects_decimal_reorder_threshold(client):
    response = client.post(
        "/products/create",
        data={
            "name": "Webcam HD",
            "price": "59.99",
            "stock": "10",
            "reorder_threshold": "4.5",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data
    assert db.session.execute(db.select(Product).filter_by(name="Webcam HD")).scalar_one_or_none() is None


def test_create_product_rejects_non_numeric_reorder_threshold(client):
    response = client.post(
        "/products/create",
        data={
            "name": "Webcam 4K",
            "price": "99.99",
            "stock": "10",
            "reorder_threshold": "five",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data
    assert db.session.execute(db.select(Product).filter_by(name="Webcam 4K")).scalar_one_or_none() is None


def test_edit_product_page_shows_reorder_threshold_field(client):
    product = Product(name="Monitor Stand", price=Decimal("45.00"), stock=8, reorder_threshold=6)
    db.session.add(product)
    db.session.commit()

    response = client.get(f"/products/{product.id}/edit")
    assert response.status_code == 200
    assert b"Reorder threshold" in response.data
    assert b'value="6"' in response.data


def test_edit_product_updates_reorder_threshold_success(client):
    product = Product(name="Desk Lamp", price=Decimal("35.00"), stock=15, reorder_threshold=4)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Desk Lamp LED",
            "price": "35.00",
            "stock": "15",
            "reorder_threshold": "10",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.reorder_threshold == 10
    assert updated.stock == 15


def test_edit_product_rejects_negative_reorder_threshold(client):
    product = Product(name="Desk Pad", price=Decimal("19.99"), stock=20, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Desk Pad",
            "price": "19.99",
            "stock": "20",
            "reorder_threshold": "-2",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 5


def test_edit_product_rejects_decimal_reorder_threshold(client):
    product = Product(name="Desk Pad XL", price=Decimal("24.99"), stock=20, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Desk Pad XL",
            "price": "24.99",
            "stock": "20",
            "reorder_threshold": "7.5",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 5


def test_edit_product_rejects_invalid_string_reorder_threshold(client):
    product = Product(name="Desk Pad XXL", price=Decimal("29.99"), stock=20, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Desk Pad XXL",
            "price": "29.99",
            "stock": "20",
            "reorder_threshold": "not_a_number",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 5


def test_edit_product_rejects_empty_reorder_threshold(client):
    product = Product(name="Desk Pad Pro", price=Decimal("34.99"), stock=20, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Desk Pad Pro",
            "price": "34.99",
            "stock": "20",
            "reorder_threshold": "  ",
        },
    )
    assert response.status_code == 200
    assert b"Reorder threshold is required." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 5


def test_edit_product_omitted_threshold_preserves_existing_value(client):
    product = Product(name="Desk Organizer", price=Decimal("22.00"), stock=10, reorder_threshold=7)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Desk Organizer Updated",
            "price": "25.00",
            "stock": "12",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.name == "Desk Organizer Updated"
    assert updated.stock == 12
    assert updated.reorder_threshold == 7


def test_manager_can_update_threshold_via_dedicated_route(client, logged_in_manager):
    product = Product(name="Smart Watch", price=Decimal("199.99"), stock=30, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "15"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Reorder threshold updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.reorder_threshold == 15
    assert updated.stock == 30


def test_admin_can_update_threshold_via_dedicated_route(client, logged_in_admin):
    product = Product(name="Fitness Tracker", price=Decimal("49.99"), stock=40, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "20"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Reorder threshold updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.reorder_threshold == 20
    assert updated.stock == 40


def test_unauthenticated_cannot_update_threshold_via_dedicated_route(client):
    product = Product(name="Power Bank", price=Decimal("29.99"), stock=50, reorder_threshold=10)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "25"},
    )
    assert response.status_code == 302
    assert "/login" in response.headers.get("Location", "")

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 10


def test_staff_cannot_update_threshold_via_dedicated_route(client, logged_in_staff):
    product = Product(name="HDMI Cable", price=Decimal("12.99"), stock=60, reorder_threshold=10)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "25"},
    )
    assert response.status_code == 403

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 10


def test_dedicated_route_rejects_negative_value(client, logged_in_manager):
    product = Product(name="Ethernet Cable", price=Decimal("9.99"), stock=50, reorder_threshold=8)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "-4"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Reorder threshold must be a non-negative whole number." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 8


def test_dedicated_route_rejects_empty_value(client, logged_in_manager):
    product = Product(name="VGA Cable", price=Decimal("7.99"), stock=20, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "   "},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Reorder threshold is required." in response.data

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 5


def test_dedicated_route_404_for_nonexistent_product(client, logged_in_manager):
    response = client.post(
        "/products/999999/reorder-threshold",
        data={"reorder_threshold": "10"},
    )
    assert response.status_code == 404


def test_staff_cannot_change_threshold_via_edit_product(client, logged_in_staff):
    product = Product(name="DisplayPort Cable", price=Decimal("15.99"), stock=30, reorder_threshold=6)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "DisplayPort Cable 1.4",
            "price": "15.99",
            "stock": "30",
            "reorder_threshold": "12",
        },
    )
    assert response.status_code == 403

    unchanged = db.session.get(Product, product_id)
    assert unchanged.reorder_threshold == 6


def test_staff_can_edit_product_keeping_threshold_same(client, logged_in_staff):
    product = Product(name="Audio Cable", price=Decimal("8.99"), stock=25, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Audio Cable 3.5mm",
            "price": "9.99",
            "stock": "25",
            "reorder_threshold": "5",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.name == "Audio Cable 3.5mm"
    assert updated.reorder_threshold == 5


def test_staff_cannot_set_nonzero_threshold_on_create(client, logged_in_staff):
    response = client.post(
        "/products/create",
        data={
            "name": "USB Cable",
            "price": "5.99",
            "stock": "50",
            "reorder_threshold": "10",
        },
    )
    assert response.status_code == 403
    assert db.session.execute(db.select(Product).filter_by(name="USB Cable")).scalar_one_or_none() is None


def test_reorder_threshold_displayed_in_inventory_table(client):
    product1 = Product(name="Tablet", price=Decimal("299.99"), stock=15, reorder_threshold=5)
    product2 = Product(name="E-Reader", price=Decimal("119.99"), stock=8, reorder_threshold=2)
    db.session.add_all([product1, product2])
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Threshold" in response.data
    assert b"<td>5</td>" in response.data
    assert b"<td>2</td>" in response.data


def test_threshold_separate_from_stock_updates(client, logged_in_manager):
    product = Product(name="Smart Lightbulb", price=Decimal("14.99"), stock=50, reorder_threshold=10)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    # Updating threshold does not touch stock
    response = client.post(
        f"/products/{product_id}/reorder-threshold",
        data={"reorder_threshold": "15"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    updated = db.session.get(Product, product_id)
    assert updated.reorder_threshold == 15
    assert updated.stock == 50

    # Restocking updates stock, leaves threshold unchanged
    response = client.post(
        f"/products/{product_id}/restock",
        data={"quantity": "20"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    reloaded = db.session.get(Product, product_id)
    assert reloaded.stock == 70
    assert reloaded.reorder_threshold == 15


# --- US-18: Link Products to Suppliers Tests ---


def test_product_supplier_relationship_model(app):
    from app.data.models import Supplier
    with app.app_context():
        supplier = Supplier(name="Apex Chipsets", contact_info="apex@chips.com")
        db.session.add(supplier)
        db.session.commit()

        product = Product(
            name="Graphic Processor",
            price=Decimal("499.99"),
            stock=12,
            supplier_id=supplier.id,
        )
        db.session.add(product)
        db.session.commit()

        loaded_product = db.session.get(Product, product.id)
        assert loaded_product.supplier_id == supplier.id
        assert loaded_product.supplier.name == "Apex Chipsets"
        assert product in supplier.products


def test_create_product_with_supplier_assignment(client, logged_in_admin):
    from app.data.models import Supplier
    supplier = Supplier(name="SoundWave Audio", contact_info="sound@wave.com")
    db.session.add(supplier)
    db.session.commit()

    response = client.post(
        "/products/create",
        data={
            "name": "Studio Speakers",
            "price": "199.99",
            "stock": "10",
            "supplier_id": str(supplier.id),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product created successfully." in response.data

    created = Product.query.filter_by(name="Studio Speakers").first()
    assert created is not None
    assert created.supplier_id == supplier.id
    assert created.supplier.name == "SoundWave Audio"


def test_edit_product_change_supplier(client, logged_in_admin):
    from app.data.models import Supplier
    s1 = Supplier(name="Supplier Alpha")
    s2 = Supplier(name="Supplier Beta")
    db.session.add_all([s1, s2])
    db.session.commit()

    product = Product(name="Smart Bulb", price=Decimal("19.99"), stock=30, supplier_id=s1.id)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Smart Bulb v2",
            "price": "21.99",
            "stock": "30",
            "supplier_id": str(s2.id),
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.supplier_id == s2.id
    assert updated.supplier.name == "Supplier Beta"


def test_edit_product_unassign_supplier(client, logged_in_admin):
    from app.data.models import Supplier
    supplier = Supplier(name="Temporary Supplier")
    db.session.add(supplier)
    db.session.commit()

    product = Product(name="Generic Cable", price=Decimal("5.99"), stock=100, supplier_id=supplier.id)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Generic Cable",
            "price": "5.99",
            "stock": "100",
            "supplier_id": "",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Product updated successfully." in response.data

    updated = db.session.get(Product, product_id)
    assert updated.supplier_id is None
    assert updated.supplier is None


def test_product_supplier_validation_rejects_nonexistent_supplier(client, logged_in_admin):
    # On creation
    resp_create = client.post(
        "/products/create",
        data={
            "name": "Invalid Supplier Product",
            "price": "50.00",
            "stock": "10",
            "supplier_id": "999999",
        },
    )
    assert resp_create.status_code == 200
    assert b"Selected supplier does not exist." in resp_create.data
    assert Product.query.filter_by(name="Invalid Supplier Product").first() is None

    # On edit
    product = Product(name="Valid Existing Product", price=Decimal("50.00"), stock=10)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    resp_edit = client.post(
        f"/products/{product_id}/edit",
        data={
            "name": "Valid Existing Product",
            "price": "50.00",
            "stock": "10",
            "supplier_id": "999999",
        },
    )
    assert resp_edit.status_code == 200
    assert b"Selected supplier does not exist." in resp_edit.data
    assert db.session.get(Product, product_id).supplier_id is None


def test_staff_cannot_assign_or_change_supplier(client, logged_in_staff):
    from app.data.models import Supplier
    supplier = Supplier(name="Protected Supplier")
    db.session.add(supplier)
    db.session.commit()

    # Staff cannot set supplier during create
    resp_create = client.post(
        "/products/create",
        data={
            "name": "Staff Attempt Product",
            "price": "20.00",
            "stock": "5",
            "supplier_id": str(supplier.id),
        },
    )
    assert resp_create.status_code == 403

    # Staff cannot change supplier during edit
    product = Product(name="Staff Edit Product", price=Decimal("20.00"), stock=5, supplier_id=None)
    db.session.add(product)
    db.session.commit()

    resp_edit = client.post(
        f"/products/{product.id}/edit",
        data={
            "name": "Staff Edit Product",
            "price": "20.00",
            "stock": "5",
            "supplier_id": str(supplier.id),
        },
    )
    assert resp_edit.status_code == 403
    assert db.session.get(Product, product.id).supplier_id is None


def test_product_supplier_displayed_in_inventory_and_edit_form(client, logged_in_admin):
    from app.data.models import Supplier
    supplier = Supplier(name="Visible Supplier Corp")
    db.session.add(supplier)
    db.session.commit()

    product = Product(
        name="Visible Product",
        price=Decimal("150.00"),
        stock=20,
        supplier_id=supplier.id,
    )
    db.session.add(product)
    db.session.commit()

    # Inventory listing displays supplier
    resp_list = client.get("/")
    assert resp_list.status_code == 200
    assert b"Visible Supplier Corp" in resp_list.data

    # Edit form has supplier selected
    resp_edit = client.get(f"/products/{product.id}/edit")
    assert resp_edit.status_code == 200
    assert b"Visible Supplier Corp" in resp_edit.data
    assert f'value="{supplier.id}" selected'.encode() in resp_edit.data


# --- US-23: Low-Stock Alerts Tests ---


def test_product_model_below_reorder_threshold_boundary(client):
    p_below = Product(name="Below", price=Decimal("10.00"), stock=3, reorder_threshold=5)
    assert p_below.is_below_reorder_threshold is True
    assert p_below.is_low_stock is True

    p_exact = Product(name="Exact", price=Decimal("10.00"), stock=5, reorder_threshold=5)
    assert p_exact.is_below_reorder_threshold is False
    assert p_exact.is_low_stock is False

    p_above = Product(name="Above", price=Decimal("10.00"), stock=8, reorder_threshold=5)
    assert p_above.is_below_reorder_threshold is False
    assert p_above.is_low_stock is False

    p_zero = Product(name="ZeroThreshold", price=Decimal("10.00"), stock=0, reorder_threshold=0)
    assert p_zero.is_below_reorder_threshold is False
    assert p_zero.is_low_stock is False


def test_low_stock_alert_displayed_when_stock_below_threshold(client):
    product = Product(name="Gaming Mousepad", price=Decimal("15.00"), stock=2, reorder_threshold=5)
    db.session.add(product)
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Low-Stock Alert" in response.data
    assert b"Gaming Mousepad" in response.data
    assert b"Low Stock Alert" in response.data


def test_no_alert_when_stock_at_or_above_threshold(client):
    p_exact = Product(name="USB Adapter", price=Decimal("8.00"), stock=10, reorder_threshold=10)
    p_above = Product(name="Ethernet Switch", price=Decimal("45.00"), stock=15, reorder_threshold=10)
    db.session.add_all([p_exact, p_above])
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Low-Stock Alert:" not in response.data
    assert b"low-stock-alert" not in response.data


def test_no_alert_when_reorder_threshold_is_zero_or_unconfigured(client):
    product = Product(name="Bulk Screws", price=Decimal("1.99"), stock=0, reorder_threshold=0)
    db.session.add(product)
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Low-Stock Alert:" not in response.data
    assert b"low-stock-alert" not in response.data


def test_manager_receives_low_stock_alert_on_dashboard(client, logged_in_manager):
    product = Product(name="Graphics Card", sku="GPU-4070", price=Decimal("599.99"), stock=1, reorder_threshold=4)
    db.session.add(product)
    db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"Low-Stock Alert" in response.data
    assert b"Graphics Card" in response.data
    assert b"GPU-4070" in response.data
    assert b"Restock / Edit" in response.data


def test_sale_dropping_stock_below_threshold_triggers_alert(client):
    from app.business.sales import create_sale

    product = Product(name="Wireless Earphones", price=Decimal("49.99"), stock=10, reorder_threshold=8)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    res_before = client.get("/")
    assert b"Low-Stock Alert:" not in res_before.data

    create_sale([{"product_id": product_id, "quantity": 3}], Product)

    res_after = client.get("/")
    assert b"Low-Stock Alert" in res_after.data
    assert b"Wireless Earphones" in res_after.data


def test_edit_product_page_shows_alert_when_stock_below_threshold(client):
    product = Product(name="Thermal Paste", price=Decimal("9.99"), stock=2, reorder_threshold=10)
    db.session.add(product)
    db.session.commit()

    response = client.get(f"/products/{product.id}/edit")
    assert response.status_code == 200
    assert b"Low-Stock Alert" in response.data
    assert b"Restocking is required." in response.data




def test_stock_edit_creates_audit_entry(client, logged_in_admin):
    from datetime import datetime

    product = Product(name="Audit Mouse", price=Decimal("20.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Audit Mouse", "price": "20.00", "stock": "10"},
    )

    assert response.status_code == 302

    entry = db.session.execute(
        db.select(AuditLog).filter_by(
            action="stock_edit",
            entity_type="product",
            entity_id=product_id,
        )
    ).scalar_one()

    assert "5 to 10" in entry.details
    assert entry.user_id == logged_in_admin.id
    assert isinstance(entry.created_at, datetime)



def test_audit_actor_cannot_be_spoofed_by_request_data(client, logged_in_admin):
    from app.data.models import User

    other_user = User(username="other-audit-user", role="admin")
    other_user.set_password("OtherPass123")
    db.session.add(other_user)
    db.session.commit()

    product = Product(name="Audit Spoof Test", price=Decimal("20.00"), stock=5)
    db.session.add(product)
    db.session.commit()

    response = client.post(
        f"/products/{product.id}/edit",
        data={
            "name": product.name,
            "price": "20.00",
            "stock": "10",
            "user_id": str(other_user.id),
        },
    )

    assert response.status_code == 302

    entry = db.session.execute(
        db.select(AuditLog).filter_by(
            action="stock_edit",
            entity_type="product",
            entity_id=product.id,
        )
    ).scalar_one()

    assert entry.user_id == logged_in_admin.id
    assert entry.user_id != other_user.id


def test_price_change_creates_audit_entry(client):
    product = Product(name="Audit Keyboard", price=Decimal("50.00"), stock=5)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Audit Keyboard", "price": "60.00", "stock": "5"},
    )

    assert response.status_code == 302

    entry = db.session.execute(
        db.select(AuditLog).filter_by(
            action="price_change",
            entity_type="product",
            entity_id=product_id,
        )
    ).scalar_one()

    assert "50.00" in entry.details
    assert "60.00" in entry.details


def test_invalid_product_edit_does_not_create_audit_entry(client):
    product = Product(name="Audit Headphones", price=Decimal("30.00"), stock=4)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(
        f"/products/{product_id}/edit",
        data={"name": "Audit Headphones", "price": "-1", "stock": "10"},
    )

    assert response.status_code == 200

    entries = db.session.execute(
        db.select(AuditLog).filter_by(entity_id=product_id)
    ).scalars().all()

    assert entries == []


def test_product_deletion_creates_audit_entry(client):
    product = Product(name="Audit Delete", price=Decimal("15.00"), stock=3)
    db.session.add(product)
    db.session.commit()
    product_id = product.id

    response = client.post(f"/products/{product_id}/delete")

    assert response.status_code == 302

    entry = db.session.execute(
        db.select(AuditLog).filter_by(
            action="product_delete",
            entity_type="product",
            entity_id=product_id,
        )
    ).scalar_one()

    assert "Audit Delete" in entry.details
    assert db.session.get(Product, product_id) is None


def test_audit_entries_preserve_different_users_ids(app):
    from flask_login import login_user
    from app.data.models import User
    from app.business.audit import record_audit

    first_user = User(username="audit-first-user", role="admin")
    first_user.set_password("FirstPass123")
    second_user = User(username="audit-second-user", role="admin")
    second_user.set_password("SecondPass123")

    db.session.add_all([first_user, second_user])
    db.session.commit()

    first_user_id = first_user.id
    second_user_id = second_user.id

    with app.test_request_context("/test-audit-first"):
        login_user(db.session.get(User, first_user_id))
        first_entry = record_audit(
            action="test_action",
            entity_type="test",
            entity_id=1,
            details="First user's action",
        )
        db.session.commit()
        first_entry_id = first_entry.id

    with app.test_request_context("/test-audit-second"):
        login_user(db.session.get(User, second_user_id))
        second_entry = record_audit(
            action="test_action",
            entity_type="test",
            entity_id=2,
            details="Second user's action",
        )
        db.session.commit()
        second_entry_id = second_entry.id

    first_entry = db.session.get(AuditLog, first_entry_id)
    second_entry = db.session.get(AuditLog, second_entry_id)

    assert first_entry.user_id == first_user_id
    assert second_entry.user_id == second_user_id
    assert first_entry.user_id != second_entry.user_id
    assert first_entry.created_at is not None
    assert second_entry.created_at is not None


def test_audit_log_older_than_six_months_remains_available(app):
    from datetime import datetime, timedelta, timezone

    old_timestamp = datetime.now(timezone.utc) - timedelta(days=190)
    entry = AuditLog(
        action="retention_test",
        entity_type="test",
        entity_id=999,
        details="Record must remain available",
        created_at=old_timestamp,
    )
    db.session.add(entry)
    db.session.commit()
    entry_id = entry.id

    db.session.expire_all()
    retained_entry = db.session.get(AuditLog, entry_id)

    assert retained_entry is not None
    assert retained_entry.action == "retention_test"
    assert retained_entry.details == "Record must remain available"
    assert retained_entry.created_at.replace(tzinfo=timezone.utc) == old_timestamp
