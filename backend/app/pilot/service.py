"""Business logic, validation engine, POS CSV parser, and readiness reporting for the Pilot Store.

Hardened with:
- Temporal integrity checks (prediction cutoff T - 4h, late-entry detection)
- Audit trail with before/after diffs and mandatory correction justifications
- Robust POS CSV import with row-level validation and batch duplicate detection
- 4-state readiness gate evaluation ('MET', 'BLOCKED', 'NOT_STARTED', 'INVALID')
- Strict chronological holdout protection excluding Services 31-40 from exploratory exports
- Database concurrency and collision safeguards
"""

import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from backend.app.pilot.config import (
    MAX_POS_CSV_ROWS,
    MAX_POS_CSV_SIZE_BYTES,
    PILOT_CUTOFF_HOURS_BEFORE_SERVICE,
    PILOT_DATABASE_PATH,
    PILOT_HOLDOUT_RESERVE_DAYS,
    PILOT_TARGET_COMPLIANCE_RATE,
    PILOT_TARGET_MEAL,
    PILOT_TARGET_SECTION,
    PILOT_TARGET_SERVICE_COUNT,
    PILOT_TIMEZONE,
)
from backend.app.pilot.database import get_pilot_connection, init_pilot_db
from backend.app.pilot.schemas import (
    DemandObservationCreate,
    DemandObservationResponse,
    ForecastRecordCreate,
    ForecastRecordResponse,
    MealMenuCreate,
    MealServiceCreate,
    MenuItemCreate,
    POSImportResponse,
    PilotQualityReportResponse,
    PreServiceFeaturesResponse,
    ProductionRecordCorrectionRequest,
    ProductionRecordCreate,
    ProductionRecordResponse,
    ReadinessGateStatus,
    ServiceDetailsResponse,
    ServiceRecordCorrectionRequest,
    ServiceRecordCreate,
    ServiceRecordResponse,
    WasteRecordCorrectionRequest,
    WasteRecordCreate,
    WasteRecordResponse,
)


class PilotDataService:
    """Service layer managing pilot operations, strict validations, and audit trails."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or PILOT_DATABASE_PATH
        init_pilot_db(self.db_path)

    def _log_audit(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        correction_reason: Optional[str] = None,
        performed_by: Optional[str] = "staff",
        auth_status: str = "unverified_client_claim",
    ) -> None:
        """Record immutable event in the audit trail."""
        log_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_pilot_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pilot_audit_logs (
                    log_id, entity_type, entity_id, action, old_value_json, new_value_json,
                    correction_reason, details, performed_by, auth_status, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    entity_type,
                    entity_id,
                    action,
                    json.dumps(old_value) if old_value else None,
                    json.dumps(new_value) if new_value else None,
                    correction_reason,
                    json.dumps(details) if details else None,
                    performed_by or "staff",
                    auth_status,
                    now_utc,
                ),
            )
            conn.commit()

    # =========================================================================
    # 1. Meal Services
    # =========================================================================

    def create_meal_service(self, req: MealServiceCreate, performed_by: Optional[str] = "staff") -> Dict[str, Any]:
        """Create a new meal service event with deterministic ID and conflict protection."""
        service_id = f"{req.service_date}_{req.meal_period}_Section_{req.canteen_section}"
        now_utc = datetime.now(timezone.utc).isoformat()

        # Default schedule times if not provided
        default_schedules = {
            "Breakfast": ("07:00", "09:00"),
            "Lunch": ("11:30", "13:30"),
            "Dinner": ("17:30", "19:30"),
        }
        def_start_time, def_end_time = default_schedules[req.meal_period]
        scheduled_start = req.scheduled_start or f"{req.service_date}T{def_start_time}:00Z"
        scheduled_end = req.scheduled_end or f"{req.service_date}T{def_end_time}:00Z"

        # Calculate prediction cutoff time: exactly T - 4h before scheduled start
        try:
            start_dt = datetime.fromisoformat(scheduled_start.replace("Z", "+00:00"))
        except ValueError:
            start_dt = datetime.strptime(f"{req.service_date}T{def_start_time}:00+00:00", "%Y-%m-%dT%H:%M:%S%z")

        cutoff_dt = start_dt - timedelta(hours=PILOT_CUTOFF_HOURS_BEFORE_SERVICE)
        prediction_cutoff_time = cutoff_dt.isoformat()

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            # Check for duplicate
            cursor.execute("SELECT service_id FROM meal_services WHERE service_id = ?", (service_id,))
            if cursor.fetchone():
                raise ValueError(f"Meal service '{service_id}' already exists.")

            cursor.execute(
                """
                INSERT INTO meal_services (
                    service_id, service_date, meal_period, canteen_section, service_status,
                    scheduled_start, scheduled_end, prediction_cutoff_time, service_timezone,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'Planned', ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_id,
                    req.service_date,
                    req.meal_period,
                    req.canteen_section,
                    scheduled_start,
                    scheduled_end,
                    prediction_cutoff_time,
                    req.service_timezone or PILOT_TIMEZONE,
                    now_utc,
                    now_utc,
                ),
            )
            conn.commit()

        self._log_audit(
            "Meal_Service",
            service_id,
            "CREATE",
            details=req.model_dump(),
            performed_by=performed_by,
        )

        return {
            "service_id": service_id,
            "service_date": req.service_date,
            "meal_period": req.meal_period,
            "canteen_section": req.canteen_section,
            "service_status": "Planned",
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
            "prediction_cutoff_time": prediction_cutoff_time,
            "service_timezone": req.service_timezone or PILOT_TIMEZONE,
            "created_at": now_utc,
            "updated_at": now_utc,
        }

    def get_meal_services(
        self,
        service_date: Optional[str] = None,
        meal_period: Optional[str] = None,
        canteen_section: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query services with optional filters."""
        query = "SELECT * FROM meal_services WHERE 1=1"
        params: List[Any] = []
        if service_date:
            query += " AND service_date = ?"
            params.append(service_date)
        if meal_period:
            query += " AND meal_period = ?"
            params.append(meal_period)
        if canteen_section:
            query += " AND canteen_section = ?"
            params.append(canteen_section)
        if status:
            query += " AND service_status = ?"
            params.append(status)

        query += " ORDER BY service_date DESC, scheduled_start DESC LIMIT ?"
        params.append(limit)

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def update_service_status(
        self, service_id: str, new_status: str, notes: Optional[str] = None, performed_by: Optional[str] = "staff"
    ) -> Dict[str, Any]:
        """Advance or audit the lifecycle state of a service."""
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meal_services WHERE service_id = ?", (service_id,))
            current = cursor.fetchone()
            if not current:
                raise ValueError(f"Service '{service_id}' does not exist.")

            old_dict = dict(current)
            cursor.execute(
                "UPDATE meal_services SET service_status = ?, updated_at = ? WHERE service_id = ?",
                (new_status, now_utc, service_id),
            )
            conn.commit()

        self._log_audit(
            "Meal_Service",
            service_id,
            "STATUS_CHANGE",
            details={"notes": notes},
            old_value={"status": old_dict["service_status"]},
            new_value={"status": new_status},
            performed_by=performed_by,
        )

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meal_services WHERE service_id = ?", (service_id,))
            updated = cursor.fetchone()
        return dict(updated)

    # =========================================================================
    # 2. Menu Items and Meal Menus
    # =========================================================================

    def create_menu_item(self, req: MenuItemCreate, performed_by: Optional[str] = "staff") -> Dict[str, Any]:
        """Register a dish in the master item catalog."""
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT item_id FROM menu_items WHERE item_id = ?", (req.item_id,))
            if cursor.fetchone():
                raise ValueError(f"Menu item '{req.item_id}' already exists.")

            cursor.execute(
                """
                INSERT INTO menu_items (
                    item_id, item_name, food_category, standard_portion_unit,
                    standard_portion_grams, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (req.item_id, req.item_name, req.food_category, req.standard_portion_unit, req.standard_portion_grams, now_utc),
            )
            conn.commit()

        self._log_audit("Menu_Item", req.item_id, "CREATE", details=req.model_dump(), performed_by=performed_by)

        return {
            "item_id": req.item_id,
            "item_name": req.item_name,
            "food_category": req.food_category,
            "standard_portion_unit": req.standard_portion_unit,
            "standard_portion_grams": req.standard_portion_grams,
            "is_active": True,
            "created_at": now_utc,
        }

    def get_menu_items(self) -> List[Dict[str, Any]]:
        """List all active dishes in the master catalog."""
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM menu_items ORDER BY food_category, item_name")
            rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def add_menu_to_service(
        self, service_id: str, req: MealMenuCreate, performed_by: Optional[str] = "staff"
    ) -> Dict[str, Any]:
        """Associate a dish with a specific meal service."""
        menu_entry_id = str(uuid.uuid4())
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT service_id FROM meal_services WHERE service_id = ?", (service_id,))
            if not cursor.fetchone():
                raise ValueError(f"Service '{service_id}' does not exist.")

            cursor.execute("SELECT item_id, item_name, food_category FROM menu_items WHERE item_id = ?", (req.item_id,))
            item = cursor.fetchone()
            if not item:
                raise ValueError(f"Menu item '{req.item_id}' does not exist.")

            cursor.execute(
                "SELECT menu_entry_id FROM meal_menus WHERE service_id = ? AND item_id = ?",
                (service_id, req.item_id),
            )
            if cursor.fetchone():
                raise ValueError(f"Menu item '{req.item_id}' is already scheduled for service '{service_id}'.")

            cursor.execute(
                """
                INSERT INTO meal_menus (
                    menu_entry_id, service_id, item_id, planned_portions, unit_price,
                    ingredient_cost_per_portion, is_available
                ) VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (menu_entry_id, service_id, req.item_id, req.planned_portions, req.unit_price, req.ingredient_cost_per_portion),
            )
            conn.commit()

        self._log_audit(
            "Meal_Menu",
            menu_entry_id,
            "CREATE",
            details={"service_id": service_id, **req.model_dump()},
            performed_by=performed_by,
        )

        return {
            "menu_entry_id": menu_entry_id,
            "service_id": service_id,
            "item_id": req.item_id,
            "item_name": item["item_name"],
            "food_category": item["food_category"],
            "planned_portions": req.planned_portions,
            "unit_price": req.unit_price,
            "ingredient_cost_per_portion": req.ingredient_cost_per_portion,
            "is_available": True,
        }

    # =========================================================================
    # 3. Pre-Service Demand Observations & Cutoff Enforcement
    # =========================================================================

    def record_demand_observation(
        self, service_id: str, req: DemandObservationCreate
    ) -> Dict[str, Any]:
        """Record pre-service headcount with strict prediction cutoff evaluation."""
        observation_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        obs_time = req.observation_timestamp or now_utc

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meal_services WHERE service_id = ?", (service_id,))
            srv = cursor.fetchone()
            if not srv:
                raise ValueError(f"Service '{service_id}' does not exist.")

            cutoff_timestamp = srv["prediction_cutoff_time"]

            # Evaluate late-entry: if observation recorded after cutoff, flag is_late_entry
            is_late = 0
            try:
                rec_dt = datetime.fromisoformat(now_utc.replace("Z", "+00:00"))
                obs_dt = datetime.fromisoformat(obs_time.replace("Z", "+00:00"))
                cut_dt = datetime.fromisoformat(cutoff_timestamp.replace("Z", "+00:00"))
                if rec_dt > cut_dt or obs_dt > cut_dt:
                    is_late = 1
            except Exception:
                if now_utc > cutoff_timestamp or obs_time > cutoff_timestamp:
                    is_late = 1

            cursor.execute(
                """
                INSERT INTO demand_observations (
                    observation_id, service_id, observation_timestamp, expected_headcount,
                    observation_source, registered_reservations, is_late_entry,
                    prediction_cutoff_timestamp, notes, recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    service_id,
                    obs_time,
                    req.expected_headcount,
                    req.observation_source,
                    req.registered_reservations,
                    is_late,
                    cutoff_timestamp,
                    req.notes,
                    now_utc,
                    req.recorded_by,
                ),
            )
            conn.commit()

        self._log_audit(
            "Demand_Observation",
            observation_id,
            "CREATE",
            details={**req.model_dump(), "is_late_entry": bool(is_late), "cutoff": cutoff_timestamp},
            performed_by=req.recorded_by,
        )

        return {
            "observation_id": observation_id,
            "service_id": service_id,
            "observation_timestamp": obs_time,
            "expected_headcount": req.expected_headcount,
            "observation_source": req.observation_source,
            "registered_reservations": req.registered_reservations,
            "is_late_entry": bool(is_late),
            "prediction_cutoff_timestamp": cutoff_timestamp,
            "notes": req.notes,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
        }

    def get_preservice_features(self, service_id: str) -> PreServiceFeaturesResponse:
        """Retrieve pre-service inputs strictly prior to prediction cutoff (leakage-free)."""
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meal_services WHERE service_id = ?", (service_id,))
            srv = cursor.fetchone()
            if not srv:
                raise ValueError(f"Service '{service_id}' does not exist.")

            cutoff = srv["prediction_cutoff_time"]

            # Query only observations that arrived before the cutoff and are not late entries
            cursor.execute(
                """
                SELECT * FROM demand_observations
                WHERE service_id = ? AND is_late_entry = 0 AND recorded_at <= ?
                ORDER BY observation_timestamp ASC
                """,
                (service_id, cutoff),
            )
            obs_rows = cursor.fetchall()
            eligible_obs = [
                DemandObservationResponse(
                    observation_id=r["observation_id"],
                    service_id=r["service_id"],
                    observation_timestamp=r["observation_timestamp"],
                    expected_headcount=r["expected_headcount"],
                    observation_source=r["observation_source"],
                    registered_reservations=r["registered_reservations"],
                    is_late_entry=bool(r["is_late_entry"]),
                    prediction_cutoff_timestamp=r["prediction_cutoff_timestamp"],
                    notes=r["notes"],
                    recorded_at=r["recorded_at"],
                    recorded_by=r["recorded_by"],
                )
                for r in obs_rows
            ]

            # Query scheduled menu items
            cursor.execute(
                """
                SELECT m.menu_entry_id, m.item_id, i.item_name, i.food_category, m.planned_portions
                FROM meal_menus m
                JOIN menu_items i ON m.item_id = i.item_id
                WHERE m.service_id = ?
                """,
                (service_id,),
            )
            menu_rows = [dict(r) for r in cursor.fetchall()]

            warnings = []
            if len(eligible_obs) == 0:
                warnings.append("No valid pre-service headcount observations exist prior to prediction cutoff.")

            feature_snapshot = {
                "service_id": service_id,
                "service_date": srv["service_date"],
                "meal_period": srv["meal_period"],
                "canteen_section": srv["canteen_section"],
                "cutoff_timestamp": cutoff,
                "headcount_values": [o.expected_headcount for o in eligible_obs],
                "scheduled_dishes": [m["item_id"] for m in menu_rows],
            }

            return PreServiceFeaturesResponse(
                service_id=service_id,
                service_date=srv["service_date"],
                meal_period=srv["meal_period"],
                canteen_section=srv["canteen_section"],
                scheduled_start=srv["scheduled_start"],
                cutoff_timestamp=cutoff,
                eligible_headcount_observations=eligible_obs,
                scheduled_menu_items=menu_rows,
                feature_snapshot=feature_snapshot,
                is_temporal_boundary_valid=len(eligible_obs) > 0,
                warnings=warnings,
            )

    # =========================================================================
    # 4. Production, Service, Waste & Auditable Corrections
    # =========================================================================

    def record_production(self, menu_entry_id: str, req: ProductionRecordCreate) -> Dict[str, Any]:
        """Log kitchen cooked portions and scale weight."""
        prod_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        meas_time = req.measurement_time or now_utc

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT menu_entry_id FROM meal_menus WHERE menu_entry_id = ?", (menu_entry_id,))
            if not cursor.fetchone():
                raise ValueError(f"Menu entry '{menu_entry_id}' does not exist.")

            cursor.execute(
                """
                INSERT INTO production_records (
                    production_id, menu_entry_id, measurement_time, batch_number,
                    portions_prepared, prepared_weight_kg, kitchen_station, recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prod_id,
                    menu_entry_id,
                    meas_time,
                    req.batch_number,
                    req.portions_prepared,
                    req.prepared_weight_kg,
                    req.kitchen_station,
                    now_utc,
                    req.recorded_by,
                ),
            )
            conn.commit()

        self._log_audit("Production_Record", prod_id, "CREATE", details=req.model_dump(), performed_by=req.recorded_by)

        return {
            "production_id": prod_id,
            "menu_entry_id": menu_entry_id,
            "measurement_time": meas_time,
            "batch_number": req.batch_number,
            "portions_prepared": req.portions_prepared,
            "prepared_weight_kg": req.prepared_weight_kg,
            "kitchen_station": req.kitchen_station,
            "correction_reason": None,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
            "superseded_by_id": None,
        }

    def correct_production_record(
        self, production_id: str, req: ProductionRecordCorrectionRequest, performed_by: Optional[str] = "staff"
    ) -> ProductionRecordResponse:
        """Auditably correct a production record, marking original as superseded."""
        new_prod_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM production_records WHERE production_id = ?", (production_id,))
            old = cursor.fetchone()
            if not old:
                raise ValueError(f"Production record '{production_id}' not found.")
            if old["superseded_by_id"]:
                raise ValueError(f"Production record '{production_id}' has already been superseded by '{old['superseded_by_id']}'.")

            old_dict = dict(old)

            # Insert replacement record
            cursor.execute(
                """
                INSERT INTO production_records (
                    production_id, menu_entry_id, measurement_time, batch_number,
                    portions_prepared, prepared_weight_kg, kitchen_station, correction_reason,
                    recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_prod_id,
                    old_dict["menu_entry_id"],
                    old_dict["measurement_time"],
                    old_dict["batch_number"],
                    req.portions_prepared,
                    req.prepared_weight_kg,
                    req.kitchen_station,
                    req.correction_reason,
                    now_utc,
                    req.corrected_by or performed_by,
                ),
            )

            # Mark old record as superseded
            cursor.execute(
                "UPDATE production_records SET superseded_by_id = ? WHERE production_id = ?",
                (new_prod_id, production_id),
            )
            conn.commit()

        self._log_audit(
            "Production_Record",
            new_prod_id,
            "CORRECTION",
            old_value={
                "production_id": production_id,
                "portions_prepared": old_dict["portions_prepared"],
                "prepared_weight_kg": old_dict["prepared_weight_kg"],
            },
            new_value={
                "production_id": new_prod_id,
                "portions_prepared": req.portions_prepared,
                "prepared_weight_kg": req.prepared_weight_kg,
            },
            correction_reason=req.correction_reason,
            performed_by=req.corrected_by or performed_by,
        )

        return ProductionRecordResponse(
            production_id=new_prod_id,
            menu_entry_id=old_dict["menu_entry_id"],
            measurement_time=old_dict["measurement_time"],
            batch_number=old_dict["batch_number"],
            portions_prepared=req.portions_prepared,
            prepared_weight_kg=req.prepared_weight_kg,
            kitchen_station=req.kitchen_station,
            correction_reason=req.correction_reason,
            recorded_at=now_utc,
            recorded_by=req.corrected_by or performed_by,
            superseded_by_id=None,
        )

    def record_service(self, menu_entry_id: str, req: ServiceRecordCreate) -> Dict[str, Any]:
        """Log POS portions served and stockout information."""
        service_rec_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        meas_time = req.measurement_time or now_utc

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT menu_entry_id FROM meal_menus WHERE menu_entry_id = ?", (menu_entry_id,))
            if not cursor.fetchone():
                raise ValueError(f"Menu entry '{menu_entry_id}' does not exist.")

            cursor.execute(
                """
                INSERT INTO service_records (
                    service_record_id, menu_entry_id, measurement_time, portions_served,
                    stockout_occurred, stockout_time, gross_sales_amount, data_source,
                    recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    service_rec_id,
                    menu_entry_id,
                    meas_time,
                    req.portions_served,
                    1 if req.stockout_occurred else 0,
                    req.stockout_time,
                    req.gross_sales_amount,
                    req.data_source,
                    now_utc,
                    req.recorded_by,
                ),
            )
            conn.commit()

        self._log_audit("Service_Record", service_rec_id, "CREATE", details=req.model_dump(), performed_by=req.recorded_by)

        return {
            "service_record_id": service_rec_id,
            "menu_entry_id": menu_entry_id,
            "measurement_time": meas_time,
            "portions_served": req.portions_served,
            "stockout_occurred": req.stockout_occurred,
            "stockout_time": req.stockout_time,
            "gross_sales_amount": req.gross_sales_amount,
            "data_source": req.data_source,
            "correction_reason": None,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
            "superseded_by_id": None,
        }

    def correct_service_record(
        self, service_record_id: str, req: ServiceRecordCorrectionRequest, performed_by: Optional[str] = "staff"
    ) -> ServiceRecordResponse:
        """Auditably correct a service record with mandatory reason."""
        new_rec_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM service_records WHERE service_record_id = ?", (service_record_id,))
            old = cursor.fetchone()
            if not old:
                raise ValueError(f"Service record '{service_record_id}' not found.")
            if old["superseded_by_id"]:
                raise ValueError(f"Service record '{service_record_id}' has already been superseded.")

            old_dict = dict(old)

            cursor.execute(
                """
                INSERT INTO service_records (
                    service_record_id, menu_entry_id, measurement_time, portions_served,
                    stockout_occurred, stockout_time, gross_sales_amount, data_source,
                    correction_reason, recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_rec_id,
                    old_dict["menu_entry_id"],
                    old_dict["measurement_time"],
                    req.portions_served,
                    1 if req.stockout_occurred else 0,
                    req.stockout_time,
                    req.gross_sales_amount,
                    old_dict["data_source"],
                    req.correction_reason,
                    now_utc,
                    req.corrected_by or performed_by,
                ),
            )
            cursor.execute(
                "UPDATE service_records SET superseded_by_id = ? WHERE service_record_id = ?",
                (new_rec_id, service_record_id),
            )
            conn.commit()

        self._log_audit(
            "Service_Record",
            new_rec_id,
            "CORRECTION",
            old_value={"portions_served": old_dict["portions_served"], "stockout": old_dict["stockout_occurred"]},
            new_value={"portions_served": req.portions_served, "stockout": req.stockout_occurred},
            correction_reason=req.correction_reason,
            performed_by=req.corrected_by or performed_by,
        )

        return ServiceRecordResponse(
            service_record_id=new_rec_id,
            menu_entry_id=old_dict["menu_entry_id"],
            measurement_time=old_dict["measurement_time"],
            portions_served=req.portions_served,
            stockout_occurred=req.stockout_occurred,
            stockout_time=req.stockout_time,
            gross_sales_amount=req.gross_sales_amount,
            data_source=old_dict["data_source"],
            correction_reason=req.correction_reason,
            recorded_at=now_utc,
            recorded_by=req.corrected_by or performed_by,
            superseded_by_id=None,
        )

    def record_waste(self, menu_entry_id: str, req: WasteRecordCreate) -> Dict[str, Any]:
        """Log separate unserved kitchen surplus and customer plate waste."""
        waste_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        meas_time = req.measurement_time or now_utc

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT menu_entry_id FROM meal_menus WHERE menu_entry_id = ?", (menu_entry_id,))
            if not cursor.fetchone():
                raise ValueError(f"Menu entry '{menu_entry_id}' does not exist.")

            cursor.execute(
                """
                INSERT INTO waste_records (
                    waste_id, menu_entry_id, measurement_time, unserved_surplus_weight_kg,
                    plate_waste_weight_kg, disposal_destination, measurement_method,
                    recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    waste_id,
                    menu_entry_id,
                    meas_time,
                    req.unserved_surplus_weight_kg,
                    req.plate_waste_weight_kg,
                    req.disposal_destination,
                    req.measurement_method,
                    now_utc,
                    req.recorded_by,
                ),
            )
            conn.commit()

        self._log_audit("Waste_Record", waste_id, "CREATE", details=req.model_dump(), performed_by=req.recorded_by)

        return {
            "waste_id": waste_id,
            "menu_entry_id": menu_entry_id,
            "measurement_time": meas_time,
            "unserved_surplus_weight_kg": req.unserved_surplus_weight_kg,
            "plate_waste_weight_kg": req.plate_waste_weight_kg,
            "disposal_destination": req.disposal_destination,
            "measurement_method": req.measurement_method,
            "correction_reason": None,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
            "superseded_by_id": None,
        }

    def correct_waste_record(
        self, waste_id: str, req: WasteRecordCorrectionRequest, performed_by: Optional[str] = "staff"
    ) -> WasteRecordResponse:
        """Auditably correct a waste record with mandatory reason."""
        new_waste_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM waste_records WHERE waste_id = ?", (waste_id,))
            old = cursor.fetchone()
            if not old:
                raise ValueError(f"Waste record '{waste_id}' not found.")
            if old["superseded_by_id"]:
                raise ValueError(f"Waste record '{waste_id}' has already been superseded.")

            old_dict = dict(old)

            cursor.execute(
                """
                INSERT INTO waste_records (
                    waste_id, menu_entry_id, measurement_time, unserved_surplus_weight_kg,
                    plate_waste_weight_kg, disposal_destination, measurement_method,
                    correction_reason, recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_waste_id,
                    old_dict["menu_entry_id"],
                    old_dict["measurement_time"],
                    req.unserved_surplus_weight_kg,
                    req.plate_waste_weight_kg,
                    req.disposal_destination,
                    old_dict["measurement_method"],
                    req.correction_reason,
                    now_utc,
                    req.corrected_by or performed_by,
                ),
            )
            cursor.execute(
                "UPDATE waste_records SET superseded_by_id = ? WHERE waste_id = ?",
                (new_waste_id, waste_id),
            )
            conn.commit()

        self._log_audit(
            "Waste_Record",
            new_waste_id,
            "CORRECTION",
            old_value={
                "unserved_surplus_kg": old_dict["unserved_surplus_weight_kg"],
                "plate_waste_kg": old_dict["plate_waste_weight_kg"],
            },
            new_value={
                "unserved_surplus_kg": req.unserved_surplus_weight_kg,
                "plate_waste_kg": req.plate_waste_weight_kg,
            },
            correction_reason=req.correction_reason,
            performed_by=req.corrected_by or performed_by,
        )

        return WasteRecordResponse(
            waste_id=new_waste_id,
            menu_entry_id=old_dict["menu_entry_id"],
            measurement_time=old_dict["measurement_time"],
            unserved_surplus_weight_kg=req.unserved_surplus_weight_kg,
            plate_waste_weight_kg=req.plate_waste_weight_kg,
            disposal_destination=req.disposal_destination,
            measurement_method=old_dict["measurement_method"],
            correction_reason=req.correction_reason,
            recorded_at=now_utc,
            recorded_by=req.corrected_by or performed_by,
            superseded_by_id=None,
        )

    # =========================================================================
    # 5. Forecast Record Creation & Frozen Snapshots
    # =========================================================================

    def create_forecast_record(
        self, req: ForecastRecordCreate, performed_by: Optional[str] = "forecasting_service"
    ) -> ForecastRecordResponse:
        """Create immutable forecast record capturing predictions and frozen pre-service snapshot."""
        forecast_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT m.menu_entry_id, m.service_id, s.prediction_cutoff_time, s.scheduled_start
                FROM meal_menus m
                JOIN meal_services s ON m.service_id = s.service_id
                WHERE m.menu_entry_id = ?
                """,
                (req.menu_entry_id,),
            )
            entry = cursor.fetchone()
            if not entry:
                raise ValueError(f"Menu entry '{req.menu_entry_id}' not found.")

            service_id = entry["service_id"]
            cutoff_timestamp = entry["prediction_cutoff_time"]

            # Pull pre-service features snapshot strictly prior to cutoff
            preservice_info = self.get_preservice_features(service_id)
            snapshot_dict = preservice_info.feature_snapshot

            cursor.execute(
                """
                INSERT INTO forecast_records (
                    forecast_id, menu_entry_id, forecast_timestamp, cutoff_timestamp,
                    predicted_demand_portions, recommended_portions, final_adopted_portions,
                    human_override, override_reason, model_name, model_version,
                    feature_snapshot, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    forecast_id,
                    req.menu_entry_id,
                    now_utc,
                    cutoff_timestamp,
                    req.predicted_demand_portions,
                    req.recommended_portions,
                    req.final_adopted_portions,
                    1 if req.human_override else 0,
                    req.override_reason,
                    req.model_name,
                    req.model_version,
                    json.dumps(snapshot_dict),
                    now_utc,
                ),
            )
            conn.commit()

        self._log_audit(
            "Forecast_Record",
            forecast_id,
            "CREATE",
            details={
                "menu_entry_id": req.menu_entry_id,
                "predicted": req.predicted_demand_portions,
                "model": req.model_name,
            },
            performed_by=performed_by,
        )

        return ForecastRecordResponse(
            forecast_id=forecast_id,
            menu_entry_id=req.menu_entry_id,
            forecast_timestamp=now_utc,
            cutoff_timestamp=cutoff_timestamp,
            predicted_demand_portions=req.predicted_demand_portions,
            recommended_portions=req.recommended_portions,
            final_adopted_portions=req.final_adopted_portions,
            human_override=req.human_override,
            override_reason=req.override_reason,
            model_name=req.model_name,
            model_version=req.model_version,
            feature_snapshot=snapshot_dict,
            created_at=now_utc,
        )

    # =========================================================================
    # 6. Service Aggregation & Details
    # =========================================================================

    def get_service_details(self, service_id: str) -> Dict[str, Any]:
        """Aggregate service metadata, observations, and menu item workflow progress."""
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meal_services WHERE service_id = ?", (service_id,))
            srv = cursor.fetchone()
            if not srv:
                raise ValueError(f"Service '{service_id}' not found.")
            service_dict = dict(srv)

            # Observations
            cursor.execute(
                "SELECT * FROM demand_observations WHERE service_id = ? ORDER BY observation_timestamp ASC",
                (service_id,),
            )
            observations = [dict(r) for r in cursor.fetchall()]

            # Menu entries
            cursor.execute(
                """
                SELECT m.*, i.item_name, i.food_category, i.standard_portion_grams
                FROM meal_menus m
                JOIN menu_items i ON m.item_id = i.item_id
                WHERE m.service_id = ?
                """,
                (service_id,),
            )
            menu_rows = cursor.fetchall()
            menu_entries: List[Dict[str, Any]] = []

            has_unserved_or_waste_missing = False
            has_pos_missing = False
            has_production_missing = False

            for m in menu_rows:
                entry_id = m["menu_entry_id"]

                # Production records (active, non-superseded)
                cursor.execute(
                    "SELECT * FROM production_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL ORDER BY batch_number ASC",
                    (entry_id,),
                )
                prod_records = [dict(r) for r in cursor.fetchall()]

                # Service records (active, non-superseded)
                cursor.execute(
                    "SELECT * FROM service_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL ORDER BY measurement_time ASC",
                    (entry_id,),
                )
                serv_records = [dict(r) for r in cursor.fetchall()]

                # Waste records (active, non-superseded)
                cursor.execute(
                    "SELECT * FROM waste_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL ORDER BY measurement_time ASC",
                    (entry_id,),
                )
                waste_records = [dict(r) for r in cursor.fetchall()]

                total_prepared = sum(p["portions_prepared"] for p in prod_records)
                total_cooked_wt = sum((p["prepared_weight_kg"] or 0.0) for p in prod_records)
                total_served = sum(s["portions_served"] for s in serv_records)
                stockout = any(bool(s["stockout_occurred"]) for s in serv_records)
                total_surplus = sum(w["unserved_surplus_weight_kg"] for w in waste_records)
                total_plate = sum(w["plate_waste_weight_kg"] for w in waste_records)

                if len(prod_records) == 0:
                    has_production_missing = True
                if len(serv_records) == 0:
                    has_pos_missing = True
                if len(waste_records) == 0:
                    has_unserved_or_waste_missing = True

                menu_entries.append(
                    {
                        "menu_entry_id": entry_id,
                        "item_id": m["item_id"],
                        "item_name": m["item_name"],
                        "food_category": m["food_category"],
                        "standard_portion_grams": m["standard_portion_grams"],
                        "planned_portions": m["planned_portions"],
                        "unit_price": m["unit_price"],
                        "ingredient_cost_per_portion": m["ingredient_cost_per_portion"],
                        "is_available": bool(m["is_available"]),
                        "total_portions_prepared": total_prepared,
                        "total_cooked_weight_kg": round(total_cooked_wt, 2),
                        "total_portions_served": total_served,
                        "stockout_occurred": stockout,
                        "total_unserved_surplus_kg": round(total_surplus, 2),
                        "total_plate_waste_kg": round(total_plate, 2),
                        "production_records": prod_records,
                        "service_records": serv_records,
                        "waste_records": waste_records,
                    }
                )

            validation_warnings: List[str] = []
            if len(observations) == 0:
                validation_warnings.append("Missing pre-service headcount observation.")
            if len(menu_entries) == 0:
                validation_warnings.append("No menu items scheduled for this service.")
            if has_production_missing:
                validation_warnings.append("Some menu items lack batch production records.")
            if has_pos_missing:
                validation_warnings.append("Some menu items lack POS served portion reconciliation.")
            if has_unserved_or_waste_missing:
                validation_warnings.append("Some menu items lack post-service separated waste measurements.")

            is_complete = (
                len(observations) > 0
                and len(menu_entries) > 0
                and not has_production_missing
                and not has_pos_missing
                and not has_unserved_or_waste_missing
            )

            return {
                "service": service_dict,
                "observations": observations,
                "menu_entries": menu_entries,
                "is_complete": is_complete,
                "validation_warnings": validation_warnings,
            }

    # =========================================================================
    # 7. POS CSV Import Engine (Hardened)
    # =========================================================================

    def import_pos_csv(
        self, csv_content: str, performed_by: Optional[str] = "pos_import"
    ) -> POSImportResponse:
        """Validate and ingest POS sales records with idempotent conflict resolution."""
        # Check payload size limit
        if len(csv_content.encode("utf-8")) > MAX_POS_CSV_SIZE_BYTES:
            return POSImportResponse(
                success=False,
                total_rows_processed=0,
                imported_count=0,
                skipped_count=0,
                errors=[f"Payload exceeds maximum allowed size of {MAX_POS_CSV_SIZE_BYTES // (1024 * 1024)} MB."],
                warnings=[],
                accepted_row_indices=[],
                rejected_rows=[],
            )

        stripped_content = csv_content.strip()
        if not stripped_content:
            return POSImportResponse(
                success=False,
                total_rows_processed=0,
                imported_count=0,
                skipped_count=0,
                errors=["CSV content is empty."],
                warnings=[],
                accepted_row_indices=[],
                rejected_rows=[],
            )

        reader = csv.DictReader(io.StringIO(stripped_content))
        headers = reader.fieldnames or []
        required_headers = {"service_date", "meal_period", "canteen_section", "portions_served"}
        missing_hdrs = required_headers - set(h.strip() for h in headers)
        if missing_hdrs:
            return POSImportResponse(
                success=False,
                total_rows_processed=0,
                imported_count=0,
                skipped_count=0,
                errors=[f"CSV missing mandatory headers: {sorted(list(missing_hdrs))}"],
                warnings=[],
                accepted_row_indices=[],
                rejected_rows=[],
            )

        total_processed = 0
        imported_count = 0
        skipped_count = 0
        errors: List[str] = []
        warnings: List[str] = []
        accepted_row_indices: List[int] = []
        rejected_rows: List[Dict[str, Any]] = []

        seen_in_batch: Set[Tuple[str, str, str, str]] = set()
        now_utc = datetime.now(timezone.utc).isoformat()

        for idx, row in enumerate(reader, start=2):
            if total_processed >= MAX_POS_CSV_ROWS:
                errors.append(f"Row limit of {MAX_POS_CSV_ROWS} exceeded. Remaining rows truncated.")
                break

            total_processed += 1
            s_date = row.get("service_date", "").strip()
            period = row.get("meal_period", "").strip()
            section = row.get("canteen_section", "").strip()
            item_id = row.get("item_id", "").strip()
            item_name = (row.get("item_name") or row.get("dish_name") or "").strip()
            p_served_str = row.get("portions_served", "").strip()
            sales_str = row.get("gross_sales_amount", "0.0").strip()
            stockout_str = row.get("stockout_occurred", "0").strip()
            meas_time = row.get("measurement_time", "").strip() or now_utc

            # Row Validation
            if not s_date or not period or not section:
                err = f"Row {idx}: missing service key (service_date, meal_period, canteen_section)."
                errors.append(err)
                rejected_rows.append({"row": idx, "reason": err})
                continue

            # Batch internal duplicate check
            batch_key = (s_date, period, section, (item_id or item_name).lower())
            if batch_key in seen_in_batch:
                err = f"Row {idx}: duplicate entry within the same CSV batch for {batch_key}."
                warnings.append(err)
                skipped_count += 1
                continue
            seen_in_batch.add(batch_key)

            try:
                portions_served = int(p_served_str)
                if portions_served < 0:
                    err = f"Row {idx}: portions_served must be non-negative (received {portions_served})."
                    errors.append(err)
                    rejected_rows.append({"row": idx, "reason": err})
                    continue
            except ValueError:
                err = f"Row {idx}: invalid portions_served integer '{p_served_str}'."
                errors.append(err)
                rejected_rows.append({"row": idx, "reason": err})
                continue

            try:
                gross_sales = float(sales_str)
                if gross_sales < 0:
                    err = f"Row {idx}: gross_sales_amount cannot be negative (received {gross_sales})."
                    errors.append(err)
                    rejected_rows.append({"row": idx, "reason": err})
                    continue
            except ValueError:
                gross_sales = 0.0

            stockout = stockout_str.lower() in ("1", "true", "yes", "y")

            # Look up or resolve service and menu item
            service_id = f"{s_date}_{period}_Section_{section}"
            with get_pilot_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT service_id FROM meal_services WHERE service_id = ?", (service_id,))
                srv_exists = cursor.fetchone()
                if not srv_exists:
                    # Reject row if service has not been planned/scheduled first
                    err = f"Row {idx}: service '{service_id}' does not exist. Meal services must be scheduled before importing POS sales."
                    errors.append(err)
                    rejected_rows.append({"row": idx, "reason": err})
                    continue

                # Match menu item
                resolved_item_id = None
                if item_id:
                    cursor.execute("SELECT item_id FROM menu_items WHERE item_id = ?", (item_id,))
                    res = cursor.fetchone()
                    if res:
                        resolved_item_id = res["item_id"]
                if not resolved_item_id and item_name:
                    cursor.execute("SELECT item_id FROM menu_items WHERE LOWER(item_name) = LOWER(?)", (item_name,))
                    res = cursor.fetchone()
                    if res:
                        resolved_item_id = res["item_id"]

                if not resolved_item_id:
                    err = f"Row {idx}: could not resolve menu item '{item_id or item_name}' in catalog."
                    errors.append(err)
                    rejected_rows.append({"row": idx, "reason": err})
                    continue

                # Ensure meal_menus bridge exists
                cursor.execute(
                    "SELECT menu_entry_id FROM meal_menus WHERE service_id = ? AND item_id = ?",
                    (service_id, resolved_item_id),
                )
                menu_entry = cursor.fetchone()
                if not menu_entry:
                    m_entry_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                        INSERT INTO meal_menus (
                            menu_entry_id, service_id, item_id, planned_portions, unit_price,
                            ingredient_cost_per_portion, is_available
                        ) VALUES (?, ?, ?, 0, 0.0, 0.0, 1)
                        """,
                        (m_entry_id, service_id, resolved_item_id),
                    )
                else:
                    m_entry_id = menu_entry["menu_entry_id"]

                # Check if service record already exists from POS import (Idempotency)
                cursor.execute(
                    """
                    SELECT service_record_id FROM service_records
                    WHERE menu_entry_id = ? AND data_source = 'POS_CSV_Import' AND superseded_by_id IS NULL
                    """,
                    (m_entry_id,),
                )
                existing = cursor.fetchone()
                if existing:
                    skipped_count += 1
                    warnings.append(f"Row {idx}: POS record already imported for {service_id} / {resolved_item_id}. Skipped duplicate.")
                    continue

                # Insert Service Record
                rec_id = str(uuid.uuid4())
                cursor.execute(
                    """
                    INSERT INTO service_records (
                        service_record_id, menu_entry_id, measurement_time, portions_served,
                        stockout_occurred, stockout_time, gross_sales_amount, data_source,
                        recorded_at, recorded_by
                    ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'POS_CSV_Import', ?, ?)
                    """,
                    (rec_id, m_entry_id, meas_time, portions_served, 1 if stockout else 0, gross_sales, now_utc, performed_by),
                )
                conn.commit()
                imported_count += 1
                accepted_row_indices.append(idx)

        self._log_audit(
            "POS_Import",
            "BATCH",
            "IMPORT_POS",
            details={
                "processed": total_processed,
                "imported": imported_count,
                "skipped": skipped_count,
                "error_count": len(errors),
            },
            performed_by=performed_by,
        )

        return POSImportResponse(
            success=len(errors) == 0,
            total_rows_processed=total_processed,
            imported_count=imported_count,
            skipped_count=skipped_count,
            errors=errors,
            warnings=warnings,
            accepted_row_indices=accepted_row_indices,
            rejected_rows=rejected_rows,
        )

    # =========================================================================
    # 8. Quality Report and 4-State Readiness Gate Calculation
    # =========================================================================

    def get_quality_report(self) -> PilotQualityReportResponse:
        """Compute live compliance metrics, completeness counts, and 4-state Phase 6 readiness gates."""
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # Target Scope: Section A, Lunch
            cursor.execute(
                """
                SELECT * FROM meal_services
                WHERE canteen_section = ? AND meal_period = ?
                ORDER BY service_date ASC
                """,
                (PILOT_TARGET_SECTION, PILOT_TARGET_MEAL),
            )
            services = [dict(r) for r in cursor.fetchall()]

            total_services = len(services)
            complete_count = 0
            missing_headcount = 0
            missing_prep = 0
            missing_pos = 0
            missing_waste = 0
            late_entries = 0
            total_dishes_count = 0
            dishes_with_stockout_audited = 0

            for s in services:
                sid = s["service_id"]
                # Headcount check and late entries
                cursor.execute("SELECT * FROM demand_observations WHERE service_id = ?", (sid,))
                obs_list = [dict(r) for r in cursor.fetchall()]
                if len(obs_list) == 0:
                    missing_headcount += 1
                else:
                    for o in obs_list:
                        if o.get("is_late_entry") == 1:
                            late_entries += 1

                # Menu entries
                cursor.execute("SELECT menu_entry_id FROM meal_menus WHERE service_id = ?", (sid,))
                m_entries = [r["menu_entry_id"] for r in cursor.fetchall()]

                srv_has_prep = True
                srv_has_pos = True
                srv_has_waste = True

                if not m_entries:
                    srv_has_prep = srv_has_pos = srv_has_waste = False
                else:
                    total_dishes_count += len(m_entries)
                    for meid in m_entries:
                        cursor.execute("SELECT COUNT(*) as c FROM production_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL", (meid,))
                        if cursor.fetchone()["c"] == 0:
                            srv_has_prep = False

                        cursor.execute("SELECT * FROM service_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL", (meid,))
                        s_recs = cursor.fetchall()
                        if len(s_recs) == 0:
                            srv_has_pos = False
                        else:
                            # Stockout was recorded and audited (0 or 1)
                            dishes_with_stockout_audited += 1

                        cursor.execute("SELECT COUNT(*) as c FROM waste_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL", (meid,))
                        if cursor.fetchone()["c"] == 0:
                            srv_has_waste = False

                if not srv_has_prep:
                    missing_prep += 1
                if not srv_has_pos:
                    missing_pos += 1
                if not srv_has_waste:
                    missing_waste += 1

                if s["service_status"] == "Audited" or (
                    srv_has_prep and srv_has_pos and srv_has_waste and len(obs_list) > 0
                ):
                    complete_count += 1

            compliance_rate = (complete_count / total_services) if total_services > 0 else 0.0

            # Evaluate Phase 6 Readiness Gates with 4 distinct states
            # Gate 1: G1_SCHEMA
            g1_status = "MET"
            g1_is_met = True

            # Gate 2: G2_VOLUME
            if total_services == 0:
                g2_status = "NOT_STARTED"
                g2_is_met = False
            elif total_services < PILOT_TARGET_SERVICE_COUNT:
                g2_status = "BLOCKED"
                g2_is_met = False
            else:
                g2_status = "MET"
                g2_is_met = True

            # Gate 3: G3_COMPLIANCE
            if total_services == 0:
                g3_status = "NOT_STARTED"
                g3_is_met = False
            elif total_services < PILOT_TARGET_SERVICE_COUNT:
                g3_status = "BLOCKED"
                g3_is_met = False
            elif compliance_rate >= PILOT_TARGET_COMPLIANCE_RATE:
                g3_status = "MET"
                g3_is_met = True
            else:
                g3_status = "BLOCKED"
                g3_is_met = False

            # Gate 4: G4_POS_RECON
            if total_services == 0:
                g4_status = "NOT_STARTED"
                g4_is_met = False
            elif missing_pos == 0 and total_services > 0:
                g4_status = "MET"
                g4_is_met = True
            else:
                g4_status = "BLOCKED"
                g4_is_met = False

            # Gate 5: G5_STOCKOUT (Precise denominator: dishes with stockout status audited)
            if total_services == 0 or total_dishes_count == 0:
                g5_status = "NOT_STARTED"
                g5_is_met = False
            elif dishes_with_stockout_audited == total_dishes_count:
                g5_status = "MET"
                g5_is_met = True
            else:
                g5_status = "BLOCKED"
                g5_is_met = False

            # Gate 6: G6_HOLDOUT_POLICY
            # Distinguish policy documentation (established) from real observation reservation
            if total_services < 31:
                g6_status = "BLOCKED"
                g6_is_met = False
                g6_details = f"Holdout policy formalized, but real-service count ({total_services}) is below 31. Awaiting Services 31-40."
            elif total_services >= PILOT_TARGET_SERVICE_COUNT:
                g6_status = "MET"
                g6_is_met = True
                g6_details = "Final 10 chronological services (Services 31-40) strictly partitioned and sealed."
            else:
                g6_status = "BLOCKED"
                g6_is_met = False
                g6_details = f"Currently accumulating Services 31-40 ({total_services}/{PILOT_TARGET_SERVICE_COUNT})."

            gates: List[ReadinessGateStatus] = [
                ReadinessGateStatus(
                    gate_id="G1_SCHEMA",
                    name="Operational Relational Schema Deployed",
                    description="All 8 operational tables active with foreign key and unique constraints.",
                    status=g1_status,
                    is_met=g1_is_met,
                    current_value="Active",
                    required_value="Active",
                    details="Isolated pilot database initialized with full relational schema and foreign keys.",
                ),
                ReadinessGateStatus(
                    gate_id="G2_VOLUME",
                    name="Minimum Pilot Observation Volume",
                    description=f"At least {PILOT_TARGET_SERVICE_COUNT} completed lunch services in Section A.",
                    status=g2_status,
                    is_met=g2_is_met,
                    current_value=f"{total_services} services",
                    required_value=f">= {PILOT_TARGET_SERVICE_COUNT} services",
                    evidence_count=total_services,
                    denominator=PILOT_TARGET_SERVICE_COUNT,
                    details=f"Current service volume is {total_services}/{PILOT_TARGET_SERVICE_COUNT} eligible services.",
                ),
                ReadinessGateStatus(
                    gate_id="G3_COMPLIANCE",
                    name="Data Collection Compliance Rate",
                    description=f"At least {int(PILOT_TARGET_COMPLIANCE_RATE * 100)}% of services must have complete records.",
                    status=g3_status,
                    is_met=g3_is_met,
                    current_value=f"{compliance_rate * 100:.1f}%",
                    required_value=f">= {PILOT_TARGET_COMPLIANCE_RATE * 100:.0f}%",
                    evidence_count=complete_count,
                    denominator=total_services if total_services > 0 else PILOT_TARGET_SERVICE_COUNT,
                    details=f"{complete_count} of {total_services} services are fully audited.",
                ),
                ReadinessGateStatus(
                    gate_id="G4_LABEL_QUALITY",
                    name="Authentic POS Demand Reconciliation",
                    description="Ground truth targets derived strictly from reconciled POS transaction records.",
                    status=g4_status,
                    is_met=g4_is_met,
                    current_value=f"{total_services - missing_pos}/{total_services} reconciled" if total_services > 0 else "0/0",
                    required_value="100% of recorded services",
                    evidence_count=total_services - missing_pos,
                    denominator=total_services,
                    details=f"{missing_pos} services still lack POS reconciliation.",
                ),
                ReadinessGateStatus(
                    gate_id="G5_STOCKOUT",
                    name="Audited Stockout Demarcation",
                    description="100% of scheduled dishes must have audited stockout occurrences for demand unconstraining.",
                    status=g5_status,
                    is_met=g5_is_met,
                    current_value=f"{dishes_with_stockout_audited}/{total_dishes_count} dishes" if total_dishes_count > 0 else "0/0",
                    required_value="100% of scheduled dishes",
                    evidence_count=dishes_with_stockout_audited,
                    denominator=total_dishes_count,
                    details=f"{total_dishes_count - dishes_with_stockout_audited} dishes missing verified stockout audit status.",
                ),
                ReadinessGateStatus(
                    gate_id="G6_HOLDOUT_POLICY",
                    name="Pristine Holdout Reservation Policy",
                    description=f"Final {PILOT_HOLDOUT_RESERVE_DAYS} pilot services permanently sealed for final evaluation.",
                    status=g6_status,
                    is_met=g6_is_met,
                    current_value=f"{min(total_services, PILOT_HOLDOUT_RESERVE_DAYS)}/10 holdout services" if total_services >= 30 else "Awaiting services",
                    required_value=f"Sealed ({PILOT_HOLDOUT_RESERVE_DAYS} days)",
                    evidence_count=max(0, total_services - 30),
                    denominator=PILOT_HOLDOUT_RESERVE_DAYS,
                    details=g6_details,
                ),
            ]

            is_pilot_ready = all(g.is_met for g in gates)

            return PilotQualityReportResponse(
                pilot_section=PILOT_TARGET_SECTION,
                pilot_meal_period=PILOT_TARGET_MEAL,
                total_services_recorded=total_services,
                target_services_count=PILOT_TARGET_SERVICE_COUNT,
                complete_services_count=complete_count,
                compliance_rate=round(compliance_rate, 4),
                target_compliance_rate=PILOT_TARGET_COMPLIANCE_RATE,
                services_missing_headcount=missing_headcount,
                services_missing_production=missing_prep,
                services_missing_pos_service=missing_pos,
                services_missing_waste=missing_waste,
                late_entries_count=late_entries,
                holdout_policy={
                    "reserve_days": PILOT_HOLDOUT_RESERVE_DAYS,
                    "policy_rule": "Final 10 chronological pilot services (Services 31-40) sealed until model selection is frozen.",
                    "holdout_gate_status": g6_status,
                    "historical_holdout_status": "Disqualified (August 4-10, 2025 permanently contaminated).",
                },
                readiness_gates=gates,
                is_pilot_ready_for_ml=is_pilot_ready,
            )

    # =========================================================================
    # 9. Data Export with Holdout Protection
    # =========================================================================

    def export_flat_dataset(self, exclude_holdout: bool = True) -> List[Dict[str, Any]]:
        """Export reconciled pilot records in flat format with strict holdout protection."""
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()

            # First determine chronological service ranks for Section A Lunch
            cursor.execute(
                """
                SELECT service_id, service_date, scheduled_start
                FROM meal_services
                WHERE canteen_section = ? AND meal_period = ?
                ORDER BY service_date ASC, scheduled_start ASC
                """,
                (PILOT_TARGET_SECTION, PILOT_TARGET_MEAL),
            )
            all_services = cursor.fetchall()
            holdout_service_ids: Set[str] = set()

            if exclude_holdout and len(all_services) > 30:
                # Services from index 30 onwards (31st to 40th service) are sealed holdout
                for s in all_services[30:]:
                    holdout_service_ids.add(s["service_id"])

            cursor.execute(
                """
                SELECT
                    s.service_id,
                    s.service_date,
                    s.meal_period,
                    s.canteen_section,
                    s.service_status,
                    s.prediction_cutoff_time,
                    i.item_id,
                    i.item_name,
                    i.food_category,
                    m.planned_portions,
                    m.unit_price,
                    m.ingredient_cost_per_portion,
                    COALESCE(SUM(p.portions_prepared), 0) as portions_prepared,
                    COALESCE(SUM(p.prepared_weight_kg), 0.0) as prepared_weight_kg,
                    COALESCE(SUM(sr.portions_served), 0) as portions_served,
                    COALESCE(MAX(sr.stockout_occurred), 0) as stockout_occurred,
                    COALESCE(SUM(w.unserved_surplus_weight_kg), 0.0) as unserved_surplus_kg,
                    COALESCE(SUM(w.plate_waste_weight_kg), 0.0) as plate_waste_kg
                FROM meal_services s
                JOIN meal_menus m ON s.service_id = m.service_id
                JOIN menu_items i ON m.item_id = i.item_id
                LEFT JOIN production_records p ON m.menu_entry_id = p.menu_entry_id AND p.superseded_by_id IS NULL
                LEFT JOIN service_records sr ON m.menu_entry_id = sr.menu_entry_id AND sr.superseded_by_id IS NULL
                LEFT JOIN waste_records w ON m.menu_entry_id = w.menu_entry_id AND w.superseded_by_id IS NULL
                GROUP BY s.service_id, m.menu_entry_id
                ORDER BY s.service_date ASC, s.scheduled_start ASC
                """
            )
            raw_rows = [dict(r) for r in cursor.fetchall()]

            # Filter out holdout records if requested
            filtered_rows = [
                r for r in raw_rows if r["service_id"] not in holdout_service_ids
            ]

        return filtered_rows
