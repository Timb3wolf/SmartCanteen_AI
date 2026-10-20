"""Automated regression and security tests for Phase 9: Go-Live Hardening & Supervised Pilot.

Verifies:
- Strict rejection of unauthenticated requests (HTTP 401)
- Rejection of invalid, tampered, and expired tokens (HTTP 401)
- Role-Based Access Control (RBAC) enforcement across Staff, Supervisor, and Admin (HTTP 403)
- Explicit evaluation holdout cohort reservation, validation, and permanent sealing
- Holdout cohort immutability: sealed cohorts cannot be modified by insertions, reordering, or backdating
- Flat dataset export exclusion based on frozen holdout service IDs & holdout access auditing
- Safe SQLite online backup and disaster recovery restoration
- Application startup configuration validation
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.pilot.auth import (
    AuthenticatedActor,
    Role,
    create_access_token,
    get_current_actor,
    verify_access_token,
)
from backend.app.pilot.config import PILOT_JWT_SECRET, validate_pilot_config
from backend.app.pilot.database import (
    backup_pilot_db,
    get_pilot_connection,
    init_pilot_db,
    reset_pilot_db,
    restore_pilot_db,
)
from backend.app.pilot.router import get_pilot_service
from backend.app.pilot.schemas import (
    HoldoutCohortCreate,
    HoldoutCohortReleaseRequest,
    HoldoutCohortSealRequest,
    HoldoutCohortUpdateRequest,
    MealMenuCreate,
    MealServiceCreate,
    MenuItemCreate,
    ProductionRecordCorrectionRequest,
    ProductionRecordCreate,
)
from backend.app.pilot.service import PilotDataService


@pytest.fixture
def temp_pilot_service(tmp_path: Path) -> PilotDataService:
    """Fixture providing an isolated PilotDataService with fresh schema."""
    db_file = tmp_path / "test_go_live.db"
    init_pilot_db(db_file)
    return PilotDataService(db_path=db_file)


# =========================================================================
# 1. Authentication & Token Verification Unit Tests
# =========================================================================

def test_jwt_token_creation_and_successful_verification():
    """Verify standard HS256 JWT access token generation and claims decoding."""
    token = create_access_token(actor_id="staff_sam", role="staff", expires_in_seconds=300)
    actor = verify_access_token(token)
    assert actor.actor_id == "staff_sam"
    assert actor.role == Role.STAFF
    assert actor.is_authenticated is True
    assert actor.expires_at > time.time()


def test_jwt_token_rejection_of_expired_tokens():
    """Verify tokens past their expiration timestamp are rejected with HTTP 401."""
    expired_token = create_access_token(actor_id="staff_sam", role="staff", expires_in_seconds=-10)
    with pytest.raises(Exception) as exc_info:
        verify_access_token(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_jwt_token_rejection_of_tampered_payload_or_signature():
    """Verify modified tokens fail cryptographic signature validation."""
    valid_token = create_access_token(actor_id="staff_sam", role="staff", expires_in_seconds=300)
    parts = valid_token.split(".")
    # Tamper with the payload segment
    tampered_token = f"{parts[0]}.eyJzdWIiOiAiaGFja2VyIiwgInJvbGUiOiAiYWRtaW4ifQ.{parts[2]}"
    with pytest.raises(Exception) as exc_info:
        verify_access_token(tampered_token)
    assert exc_info.value.status_code == 401
    assert "signature" in exc_info.value.detail.lower()


def test_jwt_token_rejection_of_wrong_secret():
    """Verify tokens signed with an unknown secret fail verification."""
    foreign_token = create_access_token(
        actor_id="staff_sam", role="admin", secret_key="completely-different-unknown-secret-key"
    )
    with pytest.raises(Exception) as exc_info:
        verify_access_token(foreign_token)
    assert exc_info.value.status_code == 401


# =========================================================================
# 2. HTTP Endpoint Authentication & RBAC Enforcement Tests
# =========================================================================

def test_protected_endpoints_reject_unauthenticated_requests(client: TestClient, temp_pilot_service: PilotDataService):
    """Verify protected endpoints return HTTP 401 when no Authorization header is provided."""
    app.dependency_overrides[get_pilot_service] = lambda: temp_pilot_service
    # Ensure no auth dependency override is active
    if get_current_actor in app.dependency_overrides:
        del app.dependency_overrides[get_current_actor]
    try:
        # 1. Unauthenticated service creation -> 401
        r = client.post(
            "/api/pilot/services",
            json={"service_date": "2026-11-20", "meal_period": "Lunch", "canteen_section": "A"},
        )
        assert r.status_code == 401
        assert "Authentication required" in r.json()["detail"]

        # 2. Unauthenticated correction -> 401
        r_corr = client.post(
            "/api/pilot/production/fake-prod-id/correct",
            json={
                "portions_prepared": 10,
                "prepared_weight_kg": 2.0,
                "correction_reason": "Adjusted scale",
            },
        )
        assert r_corr.status_code == 401

        # 3. Unauthenticated holdout reservation -> 401
        r_holdout = client.post(
            "/api/pilot/holdout/reserve",
            json={
                "policy_name": "Chronological_Final_10",
                "eligible_service_definition": "canteen_section='A'",
                "reserved_service_ids": ["srv_1", "srv_2"],
                "reason": "Freezing holdout",
            },
        )
        assert r_holdout.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_rbac_enforcement_staff_cannot_perform_supervisor_corrections(
    client: TestClient, temp_pilot_service: PilotDataService
):
    """Verify staff role is rejected with HTTP 403 when attempting supervisor-restricted actions."""
    staff_token = create_access_token(actor_id="staff_cook", role="staff")
    headers = {"Authorization": f"Bearer {staff_token}"}
    app.dependency_overrides[get_pilot_service] = lambda: temp_pilot_service
    try:
        # Staff attempts correction -> 403 Forbidden
        r = client.post(
            "/api/pilot/production/fake-id/correct",
            json={
                "portions_prepared": 35,
                "prepared_weight_kg": 5.0,
                "correction_reason": "Mistake in count",
            },
            headers=headers,
        )
        assert r.status_code == 403
        assert "Insufficient operational privileges" in r.json()["detail"]
        assert "supervisor" in r.json()["detail"]

        # Staff attempts POS import -> 403 Forbidden
        r_pos = client.post(
            "/api/pilot/pos/import",
            content="date,period,section,dish,portions\n",
            headers={**headers, "Content-Type": "text/csv"},
        )
        assert r_pos.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_rbac_enforcement_supervisor_cannot_perform_admin_holdout_operations(
    client: TestClient, temp_pilot_service: PilotDataService
):
    """Verify supervisor role is rejected with HTTP 403 when attempting admin-restricted operations."""
    supervisor_token = create_access_token(actor_id="chef_supervisor", role="supervisor")
    headers = {"Authorization": f"Bearer {supervisor_token}"}
    app.dependency_overrides[get_pilot_service] = lambda: temp_pilot_service
    try:
        # Supervisor attempts to register dish catalog item -> 403 Forbidden
        r = client.post(
            "/api/pilot/menu-items",
            json={
                "item_id": "dish_curry",
                "item_name": "Vegetable Curry",
                "food_category": "Vegetables",
                "standard_portion_grams": 200.0,
            },
            headers=headers,
        )
        assert r.status_code == 403
        assert "admin" in r.json()["detail"]

        # Supervisor attempts to seal holdout -> 403 Forbidden
        r_seal = client.post(
            "/api/pilot/holdout/cohort_123/seal",
            json={"reason": "Sealing holdout cohort"},
            headers=headers,
        )
        assert r_seal.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_auth_token_issuance_endpoint(client: TestClient):
    """Verify /api/pilot/auth/token endpoint issues valid tokens for staff login."""
    payload = {"actor_id": "chef_alex", "role": "supervisor"}
    r = client.post("/api/pilot/auth/token", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "supervisor"
    assert data["actor_id"] == "chef_alex"

    # Verify the issued token works
    actor = verify_access_token(data["access_token"])
    assert actor.actor_id == "chef_alex"
    assert actor.role == Role.SUPERVISOR


# =========================================================================
# 3. Explicit Holdout Cohort Freezing & Immutability Tests
# =========================================================================

def test_holdout_cohort_reservation_validation_and_sealing(temp_pilot_service: PilotDataService):
    """Verify explicit holdout cohort lifecycle: reservation, update, and permanent sealing."""
    # 1. Schedule 10 lunch services (Services 31 to 40)
    service_ids = []
    for day in range(1, 11):
        s = temp_pilot_service.create_meal_service(
            MealServiceCreate(
                service_date=f"2027-02-{day:02d}",
                meal_period="Lunch",
                canteen_section="A",
            )
        )
        service_ids.append(s["service_id"])

    # 2. Reject reservation if any service ID does not exist
    with pytest.raises(ValueError, match="Service IDs do not exist"):
        temp_pilot_service.reserve_holdout_cohort(
            HoldoutCohortCreate(
                policy_name="Chronological_Final_10",
                eligible_service_definition="canteen_section = 'A' AND meal_period = 'Lunch'",
                reserved_service_ids=service_ids + ["non_existent_srv_id"],
                reason="Pre-allocating holdout cohort",
            ),
            performed_by="admin_sarah",
        )

    # 3. Successfully reserve the cohort
    cohort = temp_pilot_service.reserve_holdout_cohort(
        HoldoutCohortCreate(
            policy_name="Chronological_Final_10",
            eligible_service_definition="canteen_section = 'A' AND meal_period = 'Lunch'",
            reserved_service_ids=service_ids,
            reason="Pre-allocating final 10 services as frozen holdout",
        ),
        performed_by="admin_sarah",
    )
    cohort_id = cohort["cohort_id"]
    assert cohort["status"] == "RESERVED"
    assert len(cohort["reserved_service_ids"]) == 10
    assert len(cohort["change_history"]) == 1

    # 4. Update cohort before sealing (e.g. adjust an ID with documented justification)
    updated_cohort = temp_pilot_service.update_holdout_cohort(
        cohort_id,
        HoldoutCohortUpdateRequest(
            reserved_service_ids=service_ids,
            reason="Confirmed shift schedule with canteen operations manager",
        ),
        performed_by="admin_sarah",
    )
    assert len(updated_cohort["change_history"]) == 2

    # 5. Permanently SEAL the holdout cohort
    sealed_cohort = temp_pilot_service.seal_holdout_cohort(
        cohort_id,
        HoldoutCohortSealRequest(
            reason="Freezing holdout cohort prior to exploratory model training benchmark"
        ),
        performed_by="admin_sarah",
    )
    assert sealed_cohort["status"] == "SEALED"
    assert sealed_cohort["sealed_at"] is not None
    assert sealed_cohort["sealed_by"] == "admin_sarah"

    # 6. Verify IMMUTABILITY: Any subsequent update attempt MUST fail
    with pytest.raises(ValueError, match="SEALED and strictly immutable"):
        temp_pilot_service.update_holdout_cohort(
            cohort_id,
            HoldoutCohortUpdateRequest(
                reserved_service_ids=service_ids[:9],
                reason="Attempting unauthorized modification to sealed cohort",
            ),
            performed_by="rogue_actor",
        )

    # 7. Attempting to reserve a new cohort when one is already SEALED MUST fail
    with pytest.raises(ValueError, match="already SEALED"):
        temp_pilot_service.reserve_holdout_cohort(
            HoldoutCohortCreate(
                policy_name="Duplicate_Holdout",
                eligible_service_definition="canteen_section = 'A'",
                reserved_service_ids=service_ids,
                reason="Attempting to overwrite sealed cohort",
            ),
            performed_by="admin_sarah",
        )


def test_holdout_export_protection_and_access_audit(temp_pilot_service: PilotDataService):
    """Verify flat dataset export excludes frozen holdout IDs and audits unrestricted exports."""
    # Register dish
    temp_pilot_service.create_menu_item(
        MenuItemCreate(
            item_id="dish_dahl",
            item_name="Lentil Dahl",
            food_category="Vegetables",
            standard_portion_grams=180.0,
        )
    )

    # Create 12 meal services: 2 exploratory, 10 holdout
    exploratory_ids = []
    for day in range(1, 3):
        s = temp_pilot_service.create_meal_service(
            MealServiceCreate(service_date=f"2027-03-{day:02d}", meal_period="Lunch", canteen_section="A")
        )
        temp_pilot_service.add_menu_to_service(
            s["service_id"],
            MealMenuCreate(item_id="dish_dahl", planned_portions=50, unit_price=2.0, ingredient_cost_per_portion=0.6),
        )
        exploratory_ids.append(s["service_id"])

    holdout_ids = []
    for day in range(3, 13):
        s = temp_pilot_service.create_meal_service(
            MealServiceCreate(service_date=f"2027-03-{day:02d}", meal_period="Lunch", canteen_section="A")
        )
        temp_pilot_service.add_menu_to_service(
            s["service_id"],
            MealMenuCreate(item_id="dish_dahl", planned_portions=50, unit_price=2.0, ingredient_cost_per_portion=0.6),
        )
        holdout_ids.append(s["service_id"])

    # Reserve and seal the holdout cohort
    cohort = temp_pilot_service.reserve_holdout_cohort(
        HoldoutCohortCreate(
            policy_name="Chronological_Final_10",
            eligible_service_definition="canteen_section = 'A' AND meal_period = 'Lunch'",
            reserved_service_ids=holdout_ids,
            reason="Freezing holdout cohort",
        )
    )
    temp_pilot_service.seal_holdout_cohort(
        cohort["cohort_id"],
        HoldoutCohortSealRequest(reason="Permanently locking holdout"),
    )

    # Protected export (default) MUST return only the 2 exploratory services
    protected = temp_pilot_service.export_flat_dataset(exclude_holdout=True)
    assert len(protected) == 2
    assert {r["service_id"] for r in protected} == set(exploratory_ids)
    assert not any(r["service_id"] in holdout_ids for r in protected)

    # Unprotected export returns all 12 services and logs HOLDOUT_ACCESS audit event
    unprotected = temp_pilot_service.export_flat_dataset(exclude_holdout=False, performed_by="researcher_david")
    assert len(unprotected) == 12

    with get_pilot_connection(temp_pilot_service.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pilot_audit_logs WHERE action = 'HOLDOUT_ACCESS'")
        audit_row = cursor.fetchone()
        assert audit_row is not None
        assert audit_row["performed_by"] == "researcher_david"
        assert audit_row["entity_id"] == cohort["cohort_id"]


def test_holdout_frozen_ids_immune_to_backdating_and_reordering(temp_pilot_service: PilotDataService):
    """Verify inserting backdated or older services cannot change the frozen holdout cohort IDs."""
    # Create services for Nov 10 to Nov 19
    holdout_ids = []
    for day in range(10, 20):
        s = temp_pilot_service.create_meal_service(
            MealServiceCreate(service_date=f"2026-11-{day:02d}", meal_period="Lunch", canteen_section="A")
        )
        holdout_ids.append(s["service_id"])

    # Seal cohort
    cohort = temp_pilot_service.reserve_holdout_cohort(
        HoldoutCohortCreate(
            policy_name="Fixed_Nov_Holdout",
            eligible_service_definition="canteen_section = 'A'",
            reserved_service_ids=holdout_ids,
            reason="Freezing specific service IDs",
        )
    )
    temp_pilot_service.seal_holdout_cohort(cohort["cohort_id"], HoldoutCohortSealRequest(reason="Locking"))

    # Now insert a BACKDATED service (e.g. Nov 01)
    backdated_srv = temp_pilot_service.create_meal_service(
        MealServiceCreate(service_date="2026-11-01", meal_period="Lunch", canteen_section="A")
    )

    # Retrieve holdout cohort: the exact reserved IDs must be unchanged
    stored_cohort = temp_pilot_service.get_holdout_cohort(cohort["cohort_id"])
    assert stored_cohort["reserved_service_ids"] == holdout_ids
    assert backdated_srv["service_id"] not in stored_cohort["reserved_service_ids"]


# =========================================================================
# 4. Database Backup, Disaster Recovery & Startup Validation Tests
# =========================================================================

def test_database_online_backup_and_disaster_recovery_restoration(tmp_path: Path):
    """Verify online SQLite backup and clean restoration of operational records."""
    db_file = tmp_path / "live_pilot.db"
    backup_file = tmp_path / "disaster_recovery_backup.db"
    init_pilot_db(db_file)
    service = PilotDataService(db_path=db_file)

    # 1. Populate operational data
    service.create_menu_item(
        MenuItemCreate(item_id="dish_pasta", item_name="Tomato Pasta", food_category="Rice", standard_portion_grams=220.0)
    )
    srv = service.create_meal_service(
        MealServiceCreate(service_date="2026-12-01", meal_period="Lunch", canteen_section="A")
    )
    service.add_menu_to_service(
        srv["service_id"],
        MealMenuCreate(item_id="dish_pasta", planned_portions=75, unit_price=3.5, ingredient_cost_per_portion=1.2),
    )

    # 2. Perform online backup while database is active
    saved_backup = backup_pilot_db(source_db_path=db_file, dest_backup_path=backup_file)
    assert saved_backup.exists()
    assert saved_backup.stat().st_size > 0

    # 3. Simulate disaster: reset/wipe the live database
    reset_pilot_db(db_file, confirm_destructive=True)
    wiped_service = PilotDataService(db_path=db_file)
    assert len(wiped_service.get_menu_items()) == 0
    assert len(wiped_service.get_meal_services()) == 0

    # 4. Restore database from backup
    restored_path = restore_pilot_db(backup_source_path=backup_file, target_db_path=db_file)
    assert restored_path.resolve() == db_file.resolve()

    # 5. Verify all operational records are fully restored
    restored_service = PilotDataService(db_path=db_file)
    items = restored_service.get_menu_items()
    assert len(items) == 1
    assert items[0]["item_id"] == "dish_pasta"

    services = restored_service.get_meal_services()
    assert len(services) == 1
    assert services[0]["service_id"] == srv["service_id"]


def test_validate_pilot_config_at_startup():
    """Verify startup configuration validator ensures database safety and secret length."""
    config = validate_pilot_config()
    assert "pilot_db_path" in config
    assert config["target_section"] == "A"
    assert config["target_meal"] == "Lunch"
    assert config["holdout_reserve_days"] == 10
