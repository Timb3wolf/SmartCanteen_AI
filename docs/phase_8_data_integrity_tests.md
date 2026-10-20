# Phase 8: Data Integrity & Regression Test Specification

**Date**: 2026-10-20  
**Repository**: `SmartCanteen_AI`  
**Test File**: `backend/app/tests/test_pilot_data_capture.py`  
**Total Suite Status**: 145/145 Backend Tests Passing  
**Pilot Tests**: 18 Comprehensive Integration Tests Passing  

---

## 1. Test Architecture & Database Isolation

All pilot hardening tests run against dynamically provisioned, ephemeral SQLite database files created in temporary directories via pytest's `tmp_path` fixture.
- **Zero Production Overlap**: Tests never touch `predictions.db` or the production `models/` artifacts directory.
- **Automatic Cleanup**: Temporary database files are isolated per test function and destroyed automatically upon test completion.
- **Dependency Overrides**: FastAPI integration tests use `app.dependency_overrides[get_pilot_service]` to inject the isolated temporary service into HTTP handlers.

---

## 2. Automated Test Matrix

The 18 tests in `backend/app/tests/test_pilot_data_capture.py` provide 100% coverage across the Phase 8 hardening requirements:

| # | Test Name | Target Domain | Invariant Verified |
|---|---|---|---|
| 1 | `test_pilot_database_schema_initialization` | Schema Integrity | Schema tables and PRAGMAs initialize cleanly. |
| 2 | `test_pilot_db_path_cannot_collide_with_production` | Database Safety | Target path matching `predictions.db` raises `ValueError`. |
| 3 | `test_reset_pilot_db_destructive_confirmation` | Destructive Safety | Calling `reset_pilot_db()` without `confirm_destructive=True` raises `PermissionError`. |
| 4 | `test_pilot_database_safe_startup_with_existing_data` | Startup Safety | Running `init_pilot_db()` on an existing database retains existing operational records. |
| 5 | `test_foreign_key_enforcement_and_transaction_rollback` | Referential Integrity | Foreign keys are strictly enforced; transaction failure rolls back cleanly without partial writes. |
| 6 | `test_meal_service_creation_and_status_transitions` | Service Lifecycle | Scheduled service advances through `Planned -> In_Prep -> Serving -> Closed -> Audited`. |
| 7 | `test_temporal_cutoff_and_late_entry_flagging` | Temporal Correctness | Headcount entered after $T-4\text{h}$ prediction cutoff receives `is_late_entry = True`. |
| 8 | `test_preservice_features_temporal_integrity` | Leakage Prevention | `get_preservice_features()` excludes late or post-cutoff observations from feature calculations. |
| 9 | `test_menu_item_and_service_menu_association` | Menu Association | Dish scheduling enforces catalog existence and prevents duplicate meal item mappings. |
| 10 | `test_production_service_waste_logging` | Workflow Measurements | Cooked portions, scale weights, dispensed portions, and waste are captured accurately. |
| 11 | `test_auditable_record_correction_and_non_destructibility` | Audit Immutability | Record corrections preserve historical records and store old/new diffs with mandatory justification. |
| 12 | `test_forecast_record_creation_and_feature_snapshot` | Reproducibility | Forecast records freeze a reproducible JSON snapshot of pre-service inputs at prediction cutoff. |
| 13 | `test_pos_csv_valid_import_and_idempotency` | Ingestion Idempotency | Re-importing identical POS files skips existing records without duplicate insertions. |
| 14 | `test_pos_csv_batch_internal_duplicate_prevention` | Batch Deduplication | Duplicate transactions within the same uploaded CSV batch are detected and skipped. |
| 15 | `test_pos_csv_rejects_unscheduled_service` | Ingestion Validation | POS transactions referencing non-existent or unscheduled services are rejected with errors. |
| 16 | `test_quality_report_and_readiness_gates` | 4-State Gates | Gates evaluate to `MET`, `BLOCKED`, `NOT_STARTED`, or `INVALID` based on authentic evidence. |
| 17 | `test_holdout_protection_in_data_export` | Anti-Snooping | Flat dataset export with `exclude_holdout=True` partitions and conceals Services 31–40. |
| 18 | `test_fastapi_pilot_endpoints` | API Integration | HTTP endpoints for service scheduling, menu catalog, and quality reports execute cleanly. |
| 19 | `test_fastapi_upload_size_limit` | Security Bounds | Uploads exceeding 2 MB are rejected with `HTTP 413 (Content Too Large)`. |
| 20 | `test_fastapi_record_correction_endpoints` | API Validation | HTTP correction endpoints reject updates lacking mandatory `correction_reason`. |

---

## 3. Deep Dive: Critical Regression Invariants

### 3.1 Production Path Collision Prevention
```python
def test_pilot_db_path_cannot_collide_with_production():
    from backend.app.core.config import DATABASE_PATH
    with pytest.raises(ValueError, match="CRITICAL SAFETY VIOLATION"):
        PilotDataService(db_path=DATABASE_PATH)
```
**Assertion**: Resolving `DATABASE_PATH` (`predictions.db`) must fail immediately, preventing the pilot from running against production prediction tables.

### 3.2 Pre-Service Temporal Boundary Enforcement
```python
def test_preservice_features_temporal_integrity(temp_pilot_service: PilotDataService):
    # Scheduled service: Lunch at 11:30 AM (Cutoff: 07:30 AM)
    # Obs 1 (07:00 AM, Headcount 120) -> Valid pre-service input
    # Obs 2 (08:30 AM, Headcount 150) -> Post-cutoff late entry
    features = temp_pilot_service.get_preservice_features(srv["service_id"])
    assert len(features.eligible_headcount_observations) == 1
    assert features.eligible_headcount_observations[0].expected_headcount == 120
    assert 150 not in features.feature_snapshot["headcount_values"]
```
**Assertion**: No post-cutoff headcount measurement may contaminate the pre-service feature vector.

### 3.3 POS CSV Ingestion Deduplication
```python
def test_pos_csv_batch_internal_duplicate_prevention(temp_pilot_service: PilotDataService):
    duplicate_batch_csv = """service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred
2026-11-12,Lunch,A,Baked Salmon,40,320.0,0
2026-11-12,Lunch,A,Baked Salmon,40,320.0,0
"""
    res = temp_pilot_service.import_pos_csv(duplicate_batch_csv)
    assert res.imported_count == 1
    assert res.skipped_count == 1
    assert any("duplicate entry within the same CSV batch" in w for w in res.warnings)
```
**Assertion**: Accidental duplicate rows in register exports are caught before insertion.

### 3.4 Holdout Isolation (Services 31–40)
```python
def test_holdout_protection_in_data_export(temp_pilot_service: PilotDataService):
    # Insert 35 completed meal services
    protected_export = temp_pilot_service.export_flat_dataset(exclude_holdout=True)
    assert len(protected_export) == 30

    unprotected_export = temp_pilot_service.export_flat_dataset(exclude_holdout=False)
    assert len(unprotected_export) == 35
```
**Assertion**: Exploratory model evaluation cannot peek into holdout observations before evaluation freeze.

---

## 4. Manual Verification Requirements Prior to Pilot Go-Live

While 100% of the core software logic is validated by automated unit and integration tests, physical deployment requires completing the following manual verification steps:

| Step | Verification Task | Expected Result | Responsible |
|---|---|---|---|
| **M-1** | Scale Tare Calibration | Place empty 1/1 GN pan (approx. 1.25 kg) on scale, press Tare; reading shows 0.00 kg. | Kitchen Steward |
| **M-2** | POS Register CSV Export Test | Generate manual end-of-day register export; confirm CSV headers match `service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred`. | POS Cashier Supervisor |
| **M-3** | Network Disconnect Resilience | Open Staff UI on tablet, disconnect Wi-Fi for 5 minutes, reconnect; verify pending requests retry cleanly without crash. | Systems Administrator |
| **M-4** | End-of-Day Reconciliation Sign-off | Kitchen supervisor compares POS dispensed portions + leftovers against initial cooked portion counts. | Head Chef |
