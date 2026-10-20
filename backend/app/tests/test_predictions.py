"""Tests for ML prediction, history persistence, and model metrics."""


def test_predict_success(client):
    payload = {
        "date": "2025-07-20",
        "meal": "Dinner",
        "canteen_section": "C",
        "food_category": "Vegetables",
        "unit_price_per_kg": 3.8,
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["predicted_waste_kg"] >= 0.0
    assert data["predicted_risk"] in ["Low", "Medium", "High"]
    expected_loss = round(data["predicted_waste_kg"] * 3.8, 2)
    assert data["estimated_financial_loss"] == expected_loss
    assert len(data["warnings"]) > 0


def test_predict_validation_errors(client):
    # Invalid negative price
    response = client.post(
        "/api/predict",
        json={
            "date": "2025-07-20",
            "meal": "Lunch",
            "canteen_section": "A",
            "food_category": "Rice",
            "unit_price_per_kg": -2.0,
        },
    )
    assert response.status_code == 422

    # Invalid date string
    response = client.post(
        "/api/predict",
        json={
            "date": "not-a-date",
            "meal": "Lunch",
            "canteen_section": "A",
            "food_category": "Rice",
            "unit_price_per_kg": 4.0,
        },
    )
    assert response.status_code == 422


def test_prediction_history_lifecycle(client):
    # Post a prediction
    post_res = client.post(
        "/api/predict",
        json={
            "date": "2025-07-25",
            "meal": "Breakfast",
            "canteen_section": "A",
            "food_category": "Meat",
            "unit_price_per_kg": 5.5,
        },
    )
    assert post_res.status_code == 201
    created_id = post_res.json()["id"]

    # Verify present in history
    hist_res = client.get("/api/predictions/history")
    assert hist_res.status_code == 200
    hist_data = hist_res.json()
    assert hist_data["total"] >= 1
    ids = [p["id"] for p in hist_data["predictions"]]
    assert created_id in ids

    # Clear history
    clear_res = client.delete("/api/predictions/history")
    assert clear_res.status_code == 200
    assert clear_res.json()["deleted_count"] >= 1

    # Verify now empty
    empty_res = client.get("/api/predictions/history")
    assert empty_res.status_code == 200
    assert empty_res.json()["total"] == 0


def test_model_metrics_transparency(client):
    response = client.get("/api/models/metrics")
    assert response.status_code == 200
    data = response.json()

    # Exact verified test metrics
    assert round(data["regression"]["mae"], 2) == 1.32
    assert round(data["regression"]["rmse"], 2) == 1.55
    assert round(data["regression"]["r2_score"], 3) == -0.128

    assert round(data["classification"]["accuracy"] * 100, 2) == 35.38
    assert round(data["classification"]["macro_f1"] * 100, 2) == 35.42

    assert data["features_count"] == 13
    assert len(data["limitations"]) >= 3
