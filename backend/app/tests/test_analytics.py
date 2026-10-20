"""Tests for analytics summary, distribution, recommendations, records, and CSV export."""


def test_analytics_summary_unfiltered(client):
    response = client.get("/api/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["record_count"] == 2600
    assert data["total_waste_kg"] > 0
    assert data["total_financial_loss"] > 0
    assert data["avg_waste_per_record_kg"] > 0
    assert data["avg_waste_per_service_kg"] > 0


def test_analytics_summary_filtered(client):
    response = client.get("/api/analytics/summary?meal=Lunch&food_category=Rice")
    assert response.status_code == 200
    data = response.json()
    assert 0 < data["record_count"] < 2600
    assert data["total_waste_kg"] > 0


def test_analytics_distribution(client):
    response = client.get("/api/analytics/distribution")
    assert response.status_code == 200
    data = response.json()

    assert len(data["waste_by_category"]) == 4
    assert len(data["waste_by_meal"]) == 3
    assert len(data["waste_by_section"]) == 4
    assert len(data["risk_distribution"]) == 3

    # Check percentages sum close to 100
    cat_pct_sum = sum(item["percentage"] for item in data["waste_by_category"])
    assert 99.0 <= cat_pct_sum <= 101.0

    risk_names = [item["risk"] for item in data["risk_distribution"]]
    assert risk_names == ["Low", "Medium", "High"]

    assert len(data["daily_waste_trend"]) > 0


def test_analytics_recommendations(client):
    response = client.get("/api/analytics/recommendations")
    assert response.status_code == 200
    data = response.json()
    recs = data["recommendations"]
    assert len(recs) >= 4
    for r in recs:
        assert r["id"]
        assert r["title"]
        assert r["description"]
        assert r["action_item"]


def test_analytics_records_pagination(client):
    response = client.get("/api/analytics/records?page=1&page_size=15&sort_by=Waste_Weight_kg&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 15
    assert data["total"] == 2600
    assert data["page"] == 1
    assert data["page_size"] == 15
    assert data["total_pages"] == (2600 + 15 - 1) // 15

    # Check descending order
    first_waste = data["items"][0]["Waste_Weight_kg"]
    second_waste = data["items"][1]["Waste_Weight_kg"]
    assert first_waste >= second_waste


def test_analytics_export_csv(client):
    response = client.get("/api/analytics/export?meal=Breakfast")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.strip().split("\n")
    assert len(lines) > 1
    assert "Waste_Weight_kg" in lines[0]
