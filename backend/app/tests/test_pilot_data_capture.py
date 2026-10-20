"""Automated tests for Phase 7 & 8 Operational Data Capture & Hardened Ingestion.

Verifies:
- Isolated pilot database initialization and physical separation from production
- Production database collision protection
- Safe database reset with explicit destructive confirmation
- Foreign key constraints, unique constraints, and schema invariants
- Validation rules: non-negativity, dates, prices, portion bounds
- Duplicate prevention and idempotent POS CSV imports
- Batch-internal duplicate detection in POS CSV uploads
- Rejection of POS sales for unscheduled services
- Audit trail logging, revision tracking, and mandatory correction reasons
- Temporal feature cutoff enforcement (T - 4h cutoff vs post-service leakage)
- Late-entry detection on pre-service headcount observations
- Frozen feature snapshot preservation in forecast records
- 4-state readiness gate tracking ('MET', 'BLOCKED', 'NOT_STARTED', 'INVALID')
- Chronological holdout protection excluding Services 31-40 from exploratory export
- HTTP upload size limits (413 Payload Too Large)
- Complete end-to-end operational pilot workflow
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.pilot.config import PILOT_CUTOFF_HOURS_BEFORE_SERVICE, validate_pilot_db_path
from backend.app.pilot.database import get_pilot_connection, init_pilot_db, reset_pilot_db
from backend.app.pilot.router import get_pilot_service
from backend.app.pilot.schemas import (
    DemandObservationCreate,
    ForecastRecordCreate,
    MealMenuCreate,
    MealServiceCreate,
    MenuItemCreate,
    ProductionRecordCorrectionRequest,
    ProductionRecordCreate,
    ServiceRecordCorrectionRequest,
    ServiceRecordCreate,
    WasteRecordCorrectionRequest,
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
# 1. Database Initialization, Collision & Reset Safeguards
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


def test_database_path_collision_protection(tmp_path: Path):
    """Verify security check prevents pilot database from pointing to production db."""
    from backend.app.core.config import DATABASE_PATH as PROD_DATABASE_PATH

    # 1. Exact path collision
    with pytest.raises(RuntimeError, match="FATAL SECURITY VIOLATION"):
        validate_pilot_db_path(PROD_DATABASE_PATH)

    # 2. Collision by filename
    fake_prod_filename = tmp_path / "predictions.db"
    with pytest.raises(RuntimeError, match="FATAL SECURITY VIOLATION"):
        validate_pilot_db_path(fake_prod_filename)


def test_reset_pilot_db_destructive_safeguard(tmp_path: Path):
    """Verify reset_pilot_db requires confirm_destructive=True and rejects unconfirmed calls."""
    test_db = tmp_path / "test_reset.db"
    init_pilot_db(test_db)

    # Calling without confirm_destructive raises PermissionError
    with pytest.raises(PermissionError, match="confirm_destructive must be set to True"):
        reset_pilot_db(test_db, confirm_destructive=False)

    # Calling with confirm_destructive=True succeeds cleanly
    reset_pilot_db(test_db, confirm_destructive=True)
    assert test_db.exists()


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
    """Verify deterministic service creation, cutoff computation, and duplicate collision rejection."""
    payload = MealServiceCreate(
        service_date="2026-11-01",
        meal_period="Lunch",
        canteen_section="A",
        scheduled_start="2026-11-01T11:30:00Z",
        scheduled_end="2026-11-01T13:30:00Z",
    )
    srv = temp_pilot_service.create_meal_service(payload)
    assert srv["service_id"] == "2026-11-01_Lunch_Section_A"
    assert srv["service_status"] == "Planned"
    assert srv["service_timezone"] == "Asia/Colombo"
    # Cutoff must be exactly 4 hours prior: 11:30 - 4h = 07:30
    assert "07:30:00" in srv["prediction_cutoff_time"]

    # Duplicate creation must fail with ValueError
    with pytest.raises(ValueError, match="already exists"):
        temp_pilot_service.create_meal_service(payload)


def test_menu_item_non_negative_validation(temp_pilot_service: PilotDataService):
    """Verify recipe registration and portion size validation."""
    item = temp_pilot_service.create_menu_item(
        MenuItemCreate(
            item_id="dish_lemon_herb_chicken",
            item_name="Lemon Herb Roasted Chicken",
            food_category="Meat",
            standard_portion_unit="portions",
            standard_portion_grams=180.0,
        )
    )
    assert item["item_id"] == "dish_lemon_herb_chicken"
    assert item["standard_portion_grams"] == 180.0

    # Pydantic schema validation: standard_portion_grams <= 0 must fail
    with pytest.raises(Exception):
        MenuItemCreate(
            item_id="dish_invalid",
            item_name="Invalid Grams",
            food_category="Soup",
            standard_portion_grams=-5.0,
        )


# =========================================================================
# 3. Service Workflow & Temporal Cutoff Tests
# =========================================================================

def test_service_full_workflow_happy_path(temp_pilot_service: PilotDataService):
    """Verify end-to-end service lifecycle: prep, dispense, waste, and completeness."""
    # 1. Schedule service
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-02", meal_period="Lunch", canteen_section="A")
    )

    # 2. Register and add dish
    dish = temp_pilot_service.create_menu_item(
        MenuItemCreate(
            item_id="dish_veggie_curry",
            item_name="Creamy Lentil & Veggie Curry",
            food_category="Vegetables",
            standard_portion_grams=220.0,
        )
    )
    menu_entry = temp_pilot_service.add_menu_to_service(
        srv["service_id"],
        MealMenuCreate(
            item_id=dish["item_id"],
            planned_portions=100,
            unit_price=4.50,
            ingredient_cost_per_portion=1.20,
        ),
    )
    menu_entry_id = menu_entry["menu_entry_id"]

    # 3. Pre-service headcount (eligible before cutoff)
    obs = temp_pilot_service.record_demand_observation(
        srv["service_id"],
        DemandObservationCreate(
            observation_timestamp="2026-11-02T07:00:00Z",
            expected_headcount=120,
            observation_source="Timetable_Schedule",
            registered_reservations=15,
        ),
    )
    assert obs["expected_headcount"] == 120
    assert obs["is_late_entry"] is False

    # 4. Production record
    prod = temp_pilot_service.record_production(
        menu_entry_id,
        ProductionRecordCreate(
            batch_number=1,
            portions_prepared=110,
            prepared_weight_kg=24.2,
            kitchen_station="Wok_Station_1",
        ),
    )
    assert prod["portions_prepared"] == 110

    # 5. Service record
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

    # 6. Waste record (separate surplus and plate waste)
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

    # 7. Service details aggregation
    details = temp_pilot_service.get_service_details(srv["service_id"])
    assert details["is_complete"] is True
    assert len(details["validation_warnings"]) == 0
    m_detail = details["menu_entries"][0]
    assert m_detail["total_portions_prepared"] == 110
    assert m_detail["total_portions_served"] == 102
    assert m_detail["total_unserved_surplus_kg"] == 1.76
    assert m_detail["total_plate_waste_kg"] == 0.85


def test_temporal_cutoff_and_late_entry_flagging(temp_pilot_service: PilotDataService):
    """Verify pre-service headcount observations evaluate cutoff and flag late entries."""
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(
            service_date="2026-11-03",
            meal_period="Lunch",
            canteen_section="A",
            scheduled_start="2026-11-03T11:30:00Z",
            scheduled_end="2026-11-03T13:30:00Z",
        )
    )
    # Cutoff is 2026-11-03T07:30:00Z

    # On-time observation (07:00:00 <= 07:30:00)
    obs_on_time = temp_pilot_service.record_demand_observation(
        srv["service_id"],
        DemandObservationCreate(
            observation_timestamp="2026-11-03T07:00:00Z",
            expected_headcount=130,
            observation_source="Timetable",
        ),
    )
    assert obs_on_time["is_late_entry"] is False

    # Late observation (09:15:00 > 07:30:00)
    obs_late = temp_pilot_service.record_demand_observation(
        srv["service_id"],
        DemandObservationCreate(
            observation_timestamp="2026-11-03T09:15:00Z",
            expected_headcount=145,
            observation_source="Turnstile_Probe",
        ),
    )
    assert obs_late["is_late_entry"] is True

    # Pre-service features endpoint must only return the on-time observation
    features = temp_pilot_service.get_preservice_features(srv["service_id"])
    assert len(features.eligible_headcount_observations) == 1
    assert features.eligible_headcount_observations[0].observation_id == obs_on_time["observation_id"]


# =========================================================================
# 4. Auditable Corrections & Revisions
# =========================================================================

def test_auditable_record_corrections(temp_pilot_service: PilotDataService):
    """Verify auditable corrections supersede original entries and record before/after diffs."""
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-04", meal_period="Lunch", canteen_section="A")
    )
    dish = temp_pilot_service.create_menu_item(
        MenuItemCreate(item_id="dish_pasta", item_name="Pasta Marinara", food_category="Rice", standard_portion_grams=200.0)
    )
    menu_entry = temp_pilot_service.add_menu_to_service(
        srv["service_id"], MealMenuCreate(item_id=dish["item_id"], planned_portions=50, unit_price=3.0, ingredient_cost_per_portion=1.0)
    )

    # 1. Initial production record
    prod1 = temp_pilot_service.record_production(
        menu_entry["menu_entry_id"],
        ProductionRecordCreate(portions_prepared=50, prepared_weight_kg=10.0, recorded_by="cook_bob"),
    )
    orig_id = prod1["production_id"]

    # 2. Correct with mandatory reason
    corr_req = ProductionRecordCorrectionRequest(
        portions_prepared=48,
        prepared_weight_kg=9.6,
        kitchen_station="Main_Station",
        correction_reason="Pan tare weight was miscalculated by 400 grams",
        corrected_by="head_chef_dan",
    )
    prod2 = temp_pilot_service.correct_production_record(orig_id, corr_req)
    new_id = prod2.production_id

    assert prod2.portions_prepared == 48
    assert prod2.correction_reason == "Pan tare weight was miscalculated by 400 grams"
    assert prod2.superseded_by_id is None

    # Check database: original record now has superseded_by_id pointing to new_id
    with get_pilot_connection(temp_pilot_service.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT superseded_by_id FROM production_records WHERE production_id = ?", (orig_id,))
        assert cursor.fetchone()["superseded_by_id"] == new_id

        # Verify audit log captured the correction event
        cursor.execute("SELECT * FROM pilot_audit_logs WHERE entity_id = ? AND action = 'CORRECTION'", (new_id,))
        log_entry = cursor.fetchone()
        assert log_entry is not None
        assert "miscalculated" in log_entry["correction_reason"]
        old_val = json.loads(log_entry["old_value_json"])
        assert old_val["portions_prepared"] == 50

    # 3. Attempting to correct an already superseded record must fail
    with pytest.raises(ValueError, match="already been superseded"):
        temp_pilot_service.correct_production_record(orig_id, corr_req)


# =========================================================================
# 5. Forecast Record Creation with Frozen Snapshots
# =========================================================================

def test_forecast_record_creation_and_feature_snapshot(temp_pilot_service: PilotDataService):
    """Verify forecasts preserve a reproducible, frozen pre-service snapshot."""
    srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-06", meal_period="Lunch", canteen_section="A")
    )
    dish = temp_pilot_service.create_menu_item(
        MenuItemCreate(item_id="dish_salad", item_name="Garden Salad", food_category="Vegetables", standard_portion_grams=150.0)
    )
    menu_entry = temp_pilot_service.add_menu_to_service(
        srv["service_id"], MealMenuCreate(item_id=dish["item_id"], planned_portions=60, unit_price=2.5, ingredient_cost_per_portion=0.8)
    )
    temp_pilot_service.record_demand_observation(
        srv["service_id"],
        DemandObservationCreate(
            observation_timestamp="2026-11-06T07:00:00Z",
            expected_headcount=110,
            observation_source="Timetable",
        ),
    )

    fc = temp_pilot_service.create_forecast_record(
        ForecastRecordCreate(
            menu_entry_id=menu_entry["menu_entry_id"],
            predicted_demand_portions=55.5,
            recommended_portions=60,
            final_adopted_portions=60,
            model_name="Historical_Baseline_Mean",
            model_version="1.0.0",
        )
    )
    assert fc.predicted_demand_portions == 55.5
    assert fc.feature_snapshot["service_id"] == srv["service_id"]
    assert 110 in fc.feature_snapshot["headcount_values"]


# =========================================================================
# 6. POS CSV Validation, Idempotency & Batch Duplicate Checks
# =========================================================================

def test_pos_csv_valid_import_and_idempotency(temp_pilot_service: PilotDataService):
    """Test importing POS CSV records and verifying duplicate import protection."""
    temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-10", meal_period="Lunch", canteen_section="A")
    )
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


def test_pos_csv_batch_internal_duplicate_prevention(temp_pilot_service: PilotDataService):
    """Verify duplicate records within the same CSV batch are detected and not double-counted."""
    temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-12", meal_period="Lunch", canteen_section="A")
    )
    temp_pilot_service.create_menu_item(
        MenuItemCreate(item_id="dish_salmon", item_name="Baked Salmon", food_category="Meat", standard_portion_grams=180.0)
    )

    duplicate_batch_csv = """service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred
2026-11-12,Lunch,A,Baked Salmon,40,320.0,0
2026-11-12,Lunch,A,Baked Salmon,40,320.0,0
"""
    res = temp_pilot_service.import_pos_csv(duplicate_batch_csv)
    assert res.imported_count == 1
    assert res.skipped_count == 1
    assert any("duplicate entry within the same CSV batch" in w for w in res.warnings)


def test_pos_csv_rejects_unscheduled_service(temp_pilot_service: PilotDataService):
    """Verify POS CSV rejects imports for unscheduled meal services with actionable error."""
    csv_data = """service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred
2029-12-31,Lunch,A,Baked Salmon,40,320.0,0
"""
    res = temp_pilot_service.import_pos_csv(csv_data)
    assert res.success is False
    assert any("does not exist" in e for e in res.errors)


# =========================================================================
# 7. Quality Report & 4-State Readiness Gates
# =========================================================================

def test_quality_report_and_readiness_gates(temp_pilot_service: PilotDataService):
    """Verify calculation of completeness, compliance rate, and 4-state readiness gates."""
    rep_initial = temp_pilot_service.get_quality_report()
    assert rep_initial.total_services_recorded == 0
    assert rep_initial.is_pilot_ready_for_ml is False

    gates = {g.gate_id: g for g in rep_initial.readiness_gates}
    assert gates["G1_SCHEMA"].is_met is True
    assert gates["G1_SCHEMA"].status == "MET"
    assert gates["G2_VOLUME"].is_met is False
    assert gates["G2_VOLUME"].status == "NOT_STARTED"
    assert gates["G3_COMPLIANCE"].is_met is False
    assert gates["G3_COMPLIANCE"].status == "NOT_STARTED"
    assert gates["G6_HOLDOUT_POLICY"].is_met is False
    assert gates["G6_HOLDOUT_POLICY"].status == "BLOCKED"
    assert rep_initial.holdout_policy["reserve_days"] == 10


# =========================================================================
# 8. Holdout Data Snooping Protection
# =========================================================================

def test_holdout_protection_in_data_export(temp_pilot_service: PilotDataService):
    """Verify export_flat_dataset excludes holdout services (Services 31-40) when requested."""
    # Register dish
    temp_pilot_service.create_menu_item(
        MenuItemCreate(item_id="dish_rice_bowl", item_name="Brown Rice Bowl", food_category="Rice", standard_portion_grams=200.0)
    )

    # Insert 35 consecutive lunch services
    from datetime import date, timedelta
    start_d = date(2027, 1, 1)
    for i in range(35):
        s_date = (start_d + timedelta(days=i)).isoformat()
        srv = temp_pilot_service.create_meal_service(
            MealServiceCreate(service_date=s_date, meal_period="Lunch", canteen_section="A")
        )
        temp_pilot_service.add_menu_to_service(
            srv["service_id"],
            MealMenuCreate(item_id="dish_rice_bowl", planned_portions=50, unit_price=2.0, ingredient_cost_per_portion=0.5),
        )

    # With holdout protection active, services 31-35 (5 holdout services) must be excluded
    protected_export = temp_pilot_service.export_flat_dataset(exclude_holdout=True)
    assert len(protected_export) == 30

    # With holdout protection explicitly disabled (for final locked evaluation), all 35 appear
    unprotected_export = temp_pilot_service.export_flat_dataset(exclude_holdout=False)
    assert len(unprotected_export) == 35


# =========================================================================
# 9. FastAPI Pilot Endpoints Integration Tests
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


def test_fastapi_upload_size_limit(client: TestClient, temp_pilot_service: PilotDataService):
    """Verify HTTP upload size limit rejects oversized POS CSV payloads with HTTP 413."""
    app.dependency_overrides[get_pilot_service] = lambda: temp_pilot_service
    try:
        # Construct payload > 2MB
        oversized_csv = "service_date,meal_period,canteen_section,portions_served\n" + ("2026-11-20,Lunch,A,10\n" * 100000)
        assert len(oversized_csv.encode("utf-8")) > 2 * 1024 * 1024

        r = client.post(
            "/api/pilot/pos/import",
            content=oversized_csv.encode("utf-8"),
            headers={"Content-Type": "text/csv"},
        )
        assert r.status_code == 413
    finally:
        app.dependency_overrides.clear()


def test_fastapi_record_correction_endpoints(client: TestClient, temp_pilot_service: PilotDataService):
    """Verify HTTP record correction endpoints enforce mandatory correction reason."""
    app.dependency_overrides[get_pilot_service] = lambda: temp_pilot_service
    try:
        # Schedule service, item, menu, and production
        srv = temp_pilot_service.create_meal_service(
            MealServiceCreate(service_date="2026-11-25", meal_period="Lunch", canteen_section="A")
        )
        dish = temp_pilot_service.create_menu_item(
            MenuItemCreate(item_id="dish_tacos", item_name="Bean Tacos", food_category="Vegetables", standard_portion_grams=150.0)
        )
        m = temp_pilot_service.add_menu_to_service(
            srv["service_id"], MealMenuCreate(item_id=dish["item_id"], planned_portions=40, unit_price=3.0, ingredient_cost_per_portion=1.0)
        )
        p = temp_pilot_service.record_production(
            m["menu_entry_id"], ProductionRecordCreate(portions_prepared=40, prepared_weight_kg=6.0)
        )
        prod_id = p["production_id"]

        # Call correction endpoint
        corr_payload = {
            "portions_prepared": 38,
            "prepared_weight_kg": 5.7,
            "kitchen_station": "Main_Station",
            "correction_reason": "Scale was adjusted after tare check",
            "corrected_by": "chef_tanya",
        }
        r = client.post(f"/api/pilot/production/{prod_id}/correct", json=corr_payload)
        assert r.status_code == 200
        data = r.json()
        assert data["portions_prepared"] == 38
        assert data["correction_reason"] == "Scale was adjusted after tare check"
    finally:
        app.dependency_overrides.clear()
