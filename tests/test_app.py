def test_home_page_returns_success(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Electronics Store Inventory Management" in response.data
    assert b"Application Setup Successful" in response.data
