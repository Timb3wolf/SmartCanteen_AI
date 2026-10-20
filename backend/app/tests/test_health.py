"""Tests for health and metadata endpoints."""


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "SmartCanteen" in data["app"]


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["dataset_available"] is True
    assert data["record_count"] == 2600
    assert data["models_loaded"] is True
    assert data["models"]["regression_model"] is True
    assert data["models"]["classifier_model"] is True


def test_metadata_endpoint(client):
    response = client.get("/api/metadata")
    assert response.status_code == 200
    data = response.json()
    assert set(data["meals"]) == {"Breakfast", "Lunch", "Dinner"}
    assert set(data["canteen_sections"]) == {"A", "B", "C", "D"}
    assert set(data["food_categories"]) == {"Meat", "Rice", "Soup", "Vegetables"}
    assert data["risk_categories"] == ["Low", "Medium", "High"]
    assert len(data["feature_columns"]) == 13
    assert data["total_dataset_records"] == 2600
