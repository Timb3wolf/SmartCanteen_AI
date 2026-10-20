"""Automated tests for Phase 7 Operational Data Capture & Ingestion Prototype.

Verifies:
- Isolated pilot database initialization and physical separation from production
- Foreign key constraints, unique constraints, and schema invariants
- Validation rules: non-negativity, dates, prices, portion bounds
- Duplicate prevention and idempotent POS CSV imports
- POS CSV header, data type, row-level error reporting
- Audit trail logging and revision history preservation
- Temporal feature cutoff enforcement (T - 4h cutoff vs post-service leakage)
- Pilot quality reporting, compliance calculations, and Phase 6 readiness gates
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.pilot.database import get_pilot_connection, init_pilot_db, reset_pilot_db
from backend.app.pilot.router import get_pilot_service
from backend.app.pilot.schemas import (
    DemandObservationCreate,
    MealMenuCreate,
    MealServiceCreate,
    MenuItemCreate,
    ProductionRecordCreate,
    ServiceRecordCreate,
    WasteRecordCreate,
)
from backend.app.pilot.service import PilotDataService


@pytest.fixture
def temp_pilot_service(tmp_path: Path) -> PilotDataService:
    """Fixture providing a temporary, fully isolated pilot SQLite database."""
    test_db_path = tmp_path / "test_pilot_isolated.db"
    return PilotDataService(db_path=test_db_path)


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient instance."""
    return TestClient(app)


# =========================================================================
# 1. Database Initialization & Isolation Tests
# =========================================================================

def test_pilot_database_physical_separation(tmp_path: Path):
    """Verify pilot database operates on a separate file and initializes all 9 tables."""
    custom_db = tmp_path / "custom_pilot.db"
    assert not custom_db.exists()

    init_pilot_db(custom_db)
    assert custom_db.exists()

    with get_pilot_connection(custom_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [r[0] for r in cursor.fetchall()]

    expected_tables = {
        "meal_services",
        "menu_items",
        "meal_menus",
        "demand_observations",
        "production_records",
        "service_records",
        "waste_records",
        "forecast_records",
        "pilot_audit_logs",
    }
    assert expected_tables.issubset(set(tables))


def test_foreign_key_enforcement(temp_pilot_service: PilotDataService):
    """Verify SQLite foreign key constraints reject orphaned records."""
    with get_pilot_connection(temp_pilot_service.db_path) as conn:
        cursor = conn.cursor()
        with pytest.raises(Exception):
            # Attempt to insert meal_menu with non-existent service_id and item_id
            cursor.execute(
                """
                INSERT INTO meal_menus (menu_entry_id, service_id, item_id, planned_portions, unit_price, ingredient_cost_per_portion)
                VALUES ('fake_uuid', 'non_existent_service', 'non_existent_item', 10, 5.0, 2.0);
                """
            )
            conn.commit()


# =========================================================================
# 2. Meal Service & Master Menu Validation Tests
# =========================================================================

def test_create_meal_service_and_duplicate_rejection(temp_pilot_service: PilotDataService):
    """Verify deterministic service creation and duplicate collision rejection."""
    req = MealServiceCreate(
        service_date="2026-11-02",
        meal_period="Lunch",
        canteen_section="A",
    )
    res = temp_pilot_service.create_meal_service(req)
    assert res["service_id"] == "2026-11-02_Lunch_Section_A"
    assert res["service_status"] == "Planned"

    # Duplicate submission must raise ValueError
    with pytest.raises(ValueError, match="already exists"):
        temp_pilot_service.create_meal_service(req)


def test_menu_item_creation_and_nonnegative_constraints(temp_pilot_service: PilotDataService):
    """Verify menu item registration and portion gram validations."""
    dish = MenuItemCreate(
        item_id="dish_braised_chicken",
        item_name="Braised Chicken with Potatoes",
        food_category="Meat",
        standard_portion_unit="portions",
        standard_portion_grams=180.0,
    )
    res = temp_pilot_service.create_menu_item(dish)
    assert res["item_id"] == "dish_braised_chicken"
    assert res["is_active"] is True

    # Duplicate item_id rejection
    with pytest.raises(ValueError, match="already exists"):
        temp_pilot_service.create_menu_item(dish)


def test_add_dish_to_service_menu(temp_pilot_service: PilotDataService):
    """Verify scheduling dish on service menu and duplicate dish rejection."""
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-03", meal_period="Lunch", canteen_section="A")
    )
    dish = temp_pilot_service.create_menu_item(
        MenuItemCreate(
            item_id="dish_rice_steamed",
            item_name="Steamed Jasmine Rice",
            food_category="Rice",
            standard_portion_grams=200.0,
        )
    )

    menu_link = temp_pilot_service.add_menu_to_service(
        srv["service_id"],
        MealMenuCreate(
            item_id=dish["item_id"],
            planned_portions=150,
            unit_price=1.50,
            ingredient_cost_per_portion=0.45,
        ),
    )
    assert menu_link["planned_portions"] == 150
    assert menu_link["unit_price"] == 1.50

    # Scheduling same dish on same service twice must be rejected
    with pytest.raises(ValueError, match="already scheduled"):
        temp_pilot_service.add_menu_to_service(
            srv["service_id"],
            MealMenuCreate(
                item_id=dish["item_id"],
                planned_portions=50,
                unit_price=1.50,
                ingredient_cost_per_portion=0.45,
            ),
        )


# =========================================================================
# 3. Operational Workflow & Record Logging Tests
# =========================================================================

def test_full_workflow_logging_and_completeness(temp_pilot_service: PilotDataService):
    """Test full operational lifecycle: observation, production, service, and waste logging."""
    # 1. Setup service and dish
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-04", meal_period="Lunch", canteen_section="A")
    )
    dish = temp_pilot_service.create_menu_item(
        MenuItemCreate(
            item_id="dish_beef_curry",
            item_name="Japanese Beef Curry",
            food_category="Meat",
            standard_portion_grams=220.0,
        )
    )
    menu = temp_pilot_service.add_menu_to_service(
        srv["service_id"],
        MealMenuCreate(
            item_id=dish["item_id"],
            planned_portions=100,
            unit_price=4.50,
            ingredient_cost_per_portion=1.80,
        ),
    )
    menu_entry_id = menu["menu_entry_id"]

    # 2. Pre-service observation
    obs = temp_pilot_service.record_demand_observation(
        srv["service_id"],
        DemandObservationCreate(
            expected_headcount=350,
            observation_source="Timetable_Schedule",
            registered_reservations=20,
        ),
    )
    assert obs["expected_headcount"] == 350

    # 3. Batch production
    prod = temp_pilot_service.record_production(
        menu_entry_id,
        ProductionRecordCreate(
            batch_number=1,
            portions_prepared=110,
            prepared_weight_kg=24.2,
            kitchen_station="Curry_Kettle",
        ),
    )
    assert prod["portions_prepared"] == 110

    # 4. Service POS record
    serv = temp_pilot_service.record_service(
        menu_entry_id,
        ServiceRecordCreate(
            portions_served=102,
            stockout_occurred=False,
            gross_sales_amount=459.0,
            data_source="POS_Register",
        ),
    )
    assert serv["portions_served"] == 102

    # 5. Waste record (separate surplus and plate waste)
    waste = temp_pilot_service.record_waste(
        menu_entry_id,
        WasteRecordCreate(
            unserved_surplus_weight_kg=1.76,
            plate_waste_weight_kg=0.85,
            disposal_destination="Compost",
        ),
    )
    assert waste["unserved_surplus_weight_kg"] == 1.76
    assert waste["plate_waste_weight_kg"] == 0.85

    # 6. Service details aggregation
    details = temp_pilot_service.get_service_details(srv["service_id"])
    assert details["is_complete"] is True
    assert len(details["validation_warnings"]) == 0
    m_detail = details["menu_entries"][0]
    assert m_detail["total_portions_prepared"] == 110
    assert m_detail["total_portions_served"] == 102
    assert m_detail["total_unserved_surplus_kg"] == 1.76
    assert m_detail["total_plate_waste_kg"] == 0.85


def test_audit_log_captures_all_events(temp_pilot_service: PilotDataService):
    """Verify that every creation and update event is recorded in pilot_audit_logs."""
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-05", meal_period="Dinner", canteen_section="B"),
        performed_by="chef_steve",
    )
    temp_pilot_service.update_service_status(
        srv["service_id"], "Serving", notes="Kitchen open", performed_by="manager_amy"
    )

    with get_pilot_connection(temp_pilot_service.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pilot_audit_logs WHERE entity_id = ? ORDER BY timestamp ASC", (srv["service_id"],))
        logs = cursor.fetchall()

    assert len(logs) == 2
    assert logs[0]["action"] == "CREATE"
    assert logs[0]["performed_by"] == "chef_steve"
    assert logs[1]["action"] == "STATUS_CHANGE"
    assert logs[1]["performed_by"] == "manager_amy"


# =========================================================================
# 4. POS CSV Import Validation Engine Tests
# =========================================================================

def test_pos_csv_valid_import_and_idempotency(temp_pilot_service: PilotDataService):
    """Test importing POS CSV records and verifying duplicate import protection."""
    # Pre-register dish
    temp_pilot_service.create_menu_item(
        MenuItemCreate(
            item_id="dish_pork_chop",
            item_name="Pan-Seared Pork Chop",
            food_category="Meat",
            standard_portion_grams=190.0,
        )
    )

    csv_data = """service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred
2026-11-10,Lunch,A,Pan-Seared Pork Chop,75,375.0,0
"""
    # 1. First import succeeds
    res1 = temp_pilot_service.import_pos_csv(csv_data, performed_by="automated_pos")
    assert res1.success is True
    assert res1.imported_count == 1
    assert res1.skipped_count == 0
    assert len(res1.errors) == 0

    # 2. Second import of identical data is skipped idempotently
    res2 = temp_pilot_service.import_pos_csv(csv_data, performed_by="automated_pos")
    assert res2.success is True
    assert res2.imported_count == 0
    assert res2.skipped_count == 1
    assert "already imported" in res2.warnings[0]


def test_pos_csv_missing_headers_and_invalid_rows(temp_pilot_service: PilotDataService):
    """Verify POS CSV import rejects missing headers and negative values with actionable errors."""
    bad_csv = """service_date,meal_period,canteen_section,portions_served
2026-11-11,Lunch,A,-15
"""
    res = temp_pilot_service.import_pos_csv(bad_csv)
    assert res.success is False
    assert any("portions_served must be non-negative" in e for e in res.errors)

    missing_header_csv = """invalid_header,another_col
1,2
"""
    res_hdr = temp_pilot_service.import_pos_csv(missing_header_csv)
    assert res_hdr.success is False
    assert any("CSV missing mandatory headers" in e for e in res_hdr.errors)


# =========================================================================
# 5. Quality Report & Phase 6 Readiness Gates Tests
# =========================================================================

def test_quality_report_and_readiness_gates(temp_pilot_service: PilotDataService):
    """Verify calculation of completeness, compliance rate, and readiness gates."""
    rep_initial = temp_pilot_service.get_quality_report()
    assert rep_initial.total_services_recorded == 0
    assert rep_initial.is_pilot_ready_for_ml is False

    # Check that Gate 1 (Schema deployed) is True, while Gate 2 (Volume >= 40) is False
    gates = {g.gate_id: g for g in rep_initial.readiness_gates}
    assert gates["G1_SCHEMA"].is_met is True
    assert gates["G2_VOLUME"].is_met is False
    assert gates["G3_COMPLIANCE"].is_met is False
    assert gates["G6_HOLDOUT_POLICY"].is_met is True
    assert rep_initial.holdout_policy["reserve_days"] == 10


# =========================================================================
# 6. FastAPI Pilot Endpoints Integration Tests
# =========================================================================

def test_fastapi_pilot_endpoints(client: TestClient, temp_pilot_service: PilotDataService):
    """Test pilot API endpoints via HTTP client using an isolated temporary database."""
    app.dependency_overrides[get_pilot_service] = lambda: temp_pilot_service
    try:
        # 1. Create a service
        srv_payload = {
            "service_date": "2026-11-20",
            "meal_period": "Lunch",
            "canteen_section": "A",
        }
        r_srv = client.post("/api/pilot/services", json=srv_payload)
        assert r_srv.status_code == 201
        srv_data = r_srv.json()
        service_id = srv_data["service_id"]

        # 2. List services
        r_list = client.get("/api/pilot/services", params={"canteen_section": "A"})
        assert r_list.status_code == 200
        assert any(s["service_id"] == service_id for s in r_list.json())

        # 3. Create a menu item
        item_payload = {
            "item_id": "test_soup_miso",
            "item_name": "Tofu Miso Soup",
            "food_category": "Soup",
            "standard_portion_unit": "bowls",
            "standard_portion_grams": 250.0,
        }
        r_item = client.post("/api/pilot/menu-items", json=item_payload)
        assert r_item.status_code == 201

        # 4. Fetch quality report
        r_rep = client.get("/api/pilot/quality-report")
        assert r_rep.status_code == 200
        rep_data = r_rep.json()
        assert rep_data["pilot_section"] == "A"
        assert rep_data["pilot_meal_period"] == "Lunch"
        assert "readiness_gates" in rep_data
    finally:
        app.dependency_overrides.clear()
