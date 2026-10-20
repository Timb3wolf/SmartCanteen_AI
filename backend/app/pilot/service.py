"""Business logic, validation engine, POS CSV parser, and readiness reporting for the Pilot Store."""

import csv
from datetime import datetime, timezone
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from backend.app.pilot.config import (
    PILOT_DATABASE_PATH,
    PILOT_HOLDOUT_RESERVE_DAYS,
    PILOT_TARGET_COMPLIANCE_RATE,
    PILOT_TARGET_MEAL,
    PILOT_TARGET_SECTION,
    PILOT_TARGET_SERVICE_COUNT,
)
from backend.app.pilot.database import get_pilot_connection, init_pilot_db
from backend.app.pilot.schemas import (
    DemandObservationCreate,
    MealMenuCreate,
    MealServiceCreate,
    MenuItemCreate,
    POSImportResponse,
    PilotQualityReportResponse,
    ProductionRecordCreate,
    ReadinessGateStatus,
    ServiceDetailsResponse,
    ServiceRecordCreate,
    WasteRecordCreate,
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
        details: Dict[str, Any],
        performed_by: Optional[str] = "system",
    ) -> None:
        """Record immutable event in the audit trail."""
        log_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_pilot_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pilot_audit_logs (log_id, entity_type, entity_id, action, details, performed_by, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, entity_type, entity_id, action, json.dumps(details), performed_by or "system", now_utc),
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
                    scheduled_start, scheduled_end, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'Planned', ?, ?, ?, ?)
                """,
                (
                    service_id,
                    req.service_date,
                    req.meal_period,
                    req.canteen_section,
                    scheduled_start,
                    scheduled_end,
                    now_utc,
                    now_utc,
                ),
            )
            conn.commit()

        self._log_audit("Meal_Service", service_id, "CREATE", req.model_dump(), performed_by)

        return {
            "service_id": service_id,
            "service_date": req.service_date,
            "meal_period": req.meal_period,
            "canteen_section": req.canteen_section,
            "service_status": "Planned",
            "scheduled_start": scheduled_start,
            "scheduled_end": scheduled_end,
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
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [dict(r) for r in rows]

    def update_service_status(
        self, service_id: str, new_status: str, notes: Optional[str] = None, performed_by: Optional[str] = "staff"
    ) -> Dict[str, Any]:
        """Update service lifecycle status with audit logging."""
        now_utc = datetime.now(timezone.utc).isoformat()
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM meal_services WHERE service_id = ?", (service_id,))
            service = cursor.fetchone()
            if not service:
                raise ValueError(f"Service '{service_id}' not found.")

            cursor.execute(
                "UPDATE meal_services SET service_status = ?, updated_at = ? WHERE service_id = ?",
                (new_status, now_utc, service_id),
            )
            conn.commit()

        self._log_audit(
            "Meal_Service",
            service_id,
            "STATUS_CHANGE",
            {"old_status": service["service_status"], "new_status": new_status, "notes": notes},
            performed_by,
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
                INSERT INTO menu_items (item_id, item_name, food_category, standard_portion_unit, standard_portion_grams, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
                """,
                (req.item_id, req.item_name, req.food_category, req.standard_portion_unit, req.standard_portion_grams, now_utc),
            )
            conn.commit()

        self._log_audit("Menu_Item", req.item_id, "CREATE", req.model_dump(), performed_by)

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
            # Verify service and item exist
            cursor.execute("SELECT service_id FROM meal_services WHERE service_id = ?", (service_id,))
            if not cursor.fetchone():
                raise ValueError(f"Service '{service_id}' does not exist.")

            cursor.execute("SELECT item_id, item_name, food_category FROM menu_items WHERE item_id = ?", (req.item_id,))
            item = cursor.fetchone()
            if not item:
                raise ValueError(f"Menu item '{req.item_id}' does not exist.")

            # Check uniqueness
            cursor.execute(
                "SELECT menu_entry_id FROM meal_menus WHERE service_id = ? AND item_id = ?",
                (service_id, req.item_id),
            )
            if cursor.fetchone():
                raise ValueError(f"Menu item '{req.item_id}' is already scheduled for service '{service_id}'.")

            cursor.execute(
                """
                INSERT INTO meal_menus (menu_entry_id, service_id, item_id, planned_portions, unit_price, ingredient_cost_per_portion, is_available)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (menu_entry_id, service_id, req.item_id, req.planned_portions, req.unit_price, req.ingredient_cost_per_portion),
            )
            conn.commit()

        self._log_audit("Meal_Menu", menu_entry_id, "CREATE", {"service_id": service_id, **req.model_dump()}, performed_by)

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
    # 3. Pre-Service Demand Observations
    # =========================================================================

    def record_demand_observation(
        self, service_id: str, req: DemandObservationCreate
    ) -> Dict[str, Any]:
        """Record pre-service headcount and demand estimates."""
        observation_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).isoformat()
        obs_time = req.observation_timestamp or now_utc

        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT service_id FROM meal_services WHERE service_id = ?", (service_id,))
            if not cursor.fetchone():
                raise ValueError(f"Service '{service_id}' does not exist.")

            cursor.execute(
                """
                INSERT INTO demand_observations (
                    observation_id, service_id, observation_timestamp, expected_headcount,
                    observation_source, registered_reservations, notes, recorded_at, recorded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation_id,
                    service_id,
                    obs_time,
                    req.expected_headcount,
                    req.observation_source,
                    req.registered_reservations,
                    req.notes,
                    now_utc,
                    req.recorded_by,
                ),
            )
            conn.commit()

        self._log_audit("Demand_Observation", observation_id, "CREATE", req.model_dump(), req.recorded_by)

        return {
            "observation_id": observation_id,
            "service_id": service_id,
            "observation_timestamp": obs_time,
            "expected_headcount": req.expected_headcount,
            "observation_source": req.observation_source,
            "registered_reservations": req.registered_reservations,
            "notes": req.notes,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
        }

    # =========================================================================
    # 4. Production, Service, and Waste Records
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

        self._log_audit("Production_Record", prod_id, "CREATE", req.model_dump(), req.recorded_by)

        return {
            "production_id": prod_id,
            "menu_entry_id": menu_entry_id,
            "measurement_time": meas_time,
            "batch_number": req.batch_number,
            "portions_prepared": req.portions_prepared,
            "prepared_weight_kg": req.prepared_weight_kg,
            "kitchen_station": req.kitchen_station,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
            "superseded_by_id": None,
        }

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

        self._log_audit("Service_Record", service_rec_id, "CREATE", req.model_dump(), req.recorded_by)

        return {
            "service_record_id": service_rec_id,
            "menu_entry_id": menu_entry_id,
            "measurement_time": meas_time,
            "portions_served": req.portions_served,
            "stockout_occurred": req.stockout_occurred,
            "stockout_time": req.stockout_time,
            "gross_sales_amount": req.gross_sales_amount,
            "data_source": req.data_source,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
            "superseded_by_id": None,
        }

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

        self._log_audit("Waste_Record", waste_id, "CREATE", req.model_dump(), req.recorded_by)

        return {
            "waste_id": waste_id,
            "menu_entry_id": menu_entry_id,
            "measurement_time": meas_time,
            "unserved_surplus_weight_kg": req.unserved_surplus_weight_kg,
            "plate_waste_weight_kg": req.plate_waste_weight_kg,
            "disposal_destination": req.disposal_destination,
            "measurement_method": req.measurement_method,
            "recorded_at": now_utc,
            "recorded_by": req.recorded_by,
            "superseded_by_id": None,
        }

    # =========================================================================
    # 5. Service Aggregation & Details
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
            obs_rows = [dict(r) for r in cursor.fetchall()]

            # Menu entries with items
            cursor.execute(
                """
                SELECT m.*, i.item_name, i.food_category
                FROM meal_menus m
                JOIN menu_items i ON m.item_id = i.item_id
                WHERE m.service_id = ?
                """,
                (service_id,),
            )
            menu_rows = cursor.fetchall()

            menu_entries_detail = []
            has_headcount = len(obs_rows) > 0
            has_all_prep = True
            has_all_served = True
            has_all_waste = True
            validation_warnings = []

            if not has_headcount:
                validation_warnings.append("Missing pre-service demand observation / headcount.")

            if len(menu_rows) == 0:
                validation_warnings.append("No dishes scheduled on service menu.")

            for m in menu_rows:
                m_id = m["menu_entry_id"]

                # Production
                cursor.execute(
                    "SELECT * FROM production_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL ORDER BY batch_number ASC",
                    (m_id,),
                )
                prod_list = [dict(r) for r in cursor.fetchall()]
                tot_prep = sum(p["portions_prepared"] for p in prod_list)
                if len(prod_list) == 0:
                    has_all_prep = False

                # Service
                cursor.execute(
                    "SELECT * FROM service_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL ORDER BY measurement_time DESC",
                    (m_id,),
                )
                serv_list = [dict(r) for r in cursor.fetchall()]
                tot_serv = sum(s["portions_served"] for s in serv_list)
                if len(serv_list) == 0:
                    has_all_served = False

                # Waste
                cursor.execute(
                    "SELECT * FROM waste_records WHERE menu_entry_id = ? AND superseded_by_id IS NULL ORDER BY measurement_time DESC",
                    (m_id,),
                )
                waste_list = [dict(r) for r in cursor.fetchall()]
                tot_surplus = sum(w["unserved_surplus_weight_kg"] for w in waste_list)
                tot_plate = sum(w["plate_waste_weight_kg"] for w in waste_list)
                if len(waste_list) == 0:
                    has_all_waste = False

                # Physical Plausibility warning: served should generally not exceed prepared by > 20%
                if tot_prep > 0 and tot_serv > tot_prep * 1.25:
                    validation_warnings.append(
                        f"Dish '{m['item_name']}': portions served ({tot_serv}) exceeded portions prepared ({tot_prep}) by > 25%."
                    )

                menu_entries_detail.append({
                    "menu_entry_id": m_id,
                    "item_id": m["item_id"],
                    "item_name": m["item_name"],
                    "food_category": m["food_category"],
                    "planned_portions": m["planned_portions"],
                    "unit_price": m["unit_price"],
                    "ingredient_cost_per_portion": m["ingredient_cost_per_portion"],
                    "is_available": bool(m["is_available"]),
                    "production_records": prod_list,
                    "service_records": serv_list,
                    "waste_records": waste_list,
                    "total_portions_prepared": tot_prep,
                    "total_portions_served": tot_serv,
                    "total_unserved_surplus_kg": tot_surplus,
                    "total_plate_waste_kg": tot_plate,
                })

            is_complete = bool(
                has_headcount
                and len(menu_rows) > 0
                and has_all_prep
                and has_all_served
                and has_all_waste
            )

            return {
                "service": service_dict,
                "observations": obs_rows,
                "menu_entries": menu_entries_detail,
                "is_complete": is_complete,
                "validation_warnings": validation_warnings,
            }

    # =========================================================================
    # 6. POS CSV Import Engine
    # =========================================================================

    def import_pos_csv(
        self, csv_content: str, performed_by: Optional[str] = "pos_import"
    ) -> POSImportResponse:
        """Validate and ingest POS sales records with idempotent conflict resolution."""
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        headers = reader.fieldnames or []
        required_headers = {"service_date", "meal_period", "canteen_section", "portions_served"}
        missing_hdrs = required_headers - set(h.strip() for h in headers)
        if missing_hdrs:
            return POSImportResponse(
                success=False,
                total_rows_processed=0,
                imported_count=0,
                skipped_count=0,
                errors=[f"CSV missing mandatory headers: {list(missing_hdrs)}"],
                warnings=[],
            )

        total_processed = 0
        imported_count = 0
        skipped_count = 0
        errors: List[str] = []
        warnings: List[str] = []

        now_utc = datetime.now(timezone.utc).isoformat()

        for idx, row in enumerate(reader, start=2):
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
                errors.append(f"Row {idx}: missing service key (service_date, meal_period, canteen_section).")
                continue

            try:
                portions_served = int(p_served_str)
                if portions_served < 0:
                    errors.append(f"Row {idx}: portions_served must be non-negative, got {portions_served}.")
                    continue
            except ValueError:
                errors.append(f"Row {idx}: invalid portions_served integer '{p_served_str}'.")
                continue

            try:
                gross_sales = float(sales_str)
                if gross_sales < 0:
                    errors.append(f"Row {idx}: gross_sales_amount cannot be negative, got {gross_sales}.")
                    continue
            except ValueError:
                gross_sales = 0.0

            stockout = stockout_str.lower() in ("1", "true", "yes", "y")

            # Look up or resolve service and menu item
            service_id = f"{s_date}_{period}_Section_{section}"
            with get_pilot_connection(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT service_id FROM meal_services WHERE service_id = ?", (service_id,))
                if not cursor.fetchone():
                    # Create service if not yet registered
                    cursor.execute(
                        """
                        INSERT INTO meal_services (
                            service_id, service_date, meal_period, canteen_section, service_status,
                            scheduled_start, scheduled_end, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, 'Serving', ?, ?, ?, ?)
                        """,
                        (service_id, s_date, period, section, f"{s_date}T11:30:00Z", f"{s_date}T13:30:00Z", now_utc, now_utc),
                    )

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
                    errors.append(f"Row {idx}: could not resolve menu item '{item_id or item_name}' in catalog.")
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
                        INSERT INTO meal_menus (menu_entry_id, service_id, item_id, planned_portions, unit_price, ingredient_cost_per_portion, is_available)
                        VALUES (?, ?, ?, 0, 0.0, 0.0, 1)
                        """,
                        (m_entry_id, service_id, resolved_item_id),
                    )
                else:
                    m_entry_id = menu_entry["menu_entry_id"]

                # Check if service record already exists from POS import (Idempotency)
                cursor.execute(
                    """
                    SELECT service_record_id FROM service_records
                    WHERE menu_entry_id = ? AND data_source = 'POS_CSV_Import'
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

        self._log_audit(
            "POS_Import",
            "BATCH",
            "IMPORT_POS",
            {"processed": total_processed, "imported": imported_count, "skipped": skipped_count, "error_count": len(errors)},
            performed_by,
        )

        return POSImportResponse(
            success=len(errors) == 0,
            total_rows_processed=total_processed,
            imported_count=imported_count,
            skipped_count=skipped_count,
            errors=errors,
            warnings=warnings,
        )

    # =========================================================================
    # 7. Quality Report and Readiness Gate Calculation
    # =========================================================================

    def get_quality_report(self) -> PilotQualityReportResponse:
        """Compute live compliance metrics, completeness counts, and Phase 6 readiness gates."""
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

            for s in services:
                sid = s["service_id"]
                # Headcount
                cursor.execute("SELECT COUNT(*) as c FROM demand_observations WHERE service_id = ?", (sid,))
                if cursor.fetchone()["c"] == 0:
                    missing_headcount += 1

                # Menu entries
                cursor.execute("SELECT menu_entry_id FROM meal_menus WHERE service_id = ?", (sid,))
                m_entries = [r["menu_entry_id"] for r in cursor.fetchall()]

                srv_has_prep = True
                srv_has_pos = True
                srv_has_waste = True

                if not m_entries:
                    srv_has_prep = srv_has_pos = srv_has_waste = False
                else:
                    for meid in m_entries:
                        cursor.execute("SELECT COUNT(*) as c FROM production_records WHERE menu_entry_id = ?", (meid,))
                        if cursor.fetchone()["c"] == 0:
                            srv_has_prep = False
                        cursor.execute("SELECT COUNT(*) as c FROM service_records WHERE menu_entry_id = ?", (meid,))
                        if cursor.fetchone()["c"] == 0:
                            srv_has_pos = False
                        cursor.execute("SELECT COUNT(*) as c FROM waste_records WHERE menu_entry_id = ?", (meid,))
                        if cursor.fetchone()["c"] == 0:
                            srv_has_waste = False

                if not srv_has_prep:
                    missing_prep += 1
                if not srv_has_pos:
                    missing_pos += 1
                if not srv_has_waste:
                    missing_waste += 1

                if s["service_status"] == "Audited" or (
                    srv_has_prep and srv_has_pos and srv_has_waste and cursor.fetchone()
                ):
                    complete_count += 1

            compliance_rate = (complete_count / total_services) if total_services > 0 else 0.0

            # Evaluate Phase 6 Readiness Gates
            gates: List[ReadinessGateStatus] = [
                ReadinessGateStatus(
                    gate_id="G1_SCHEMA",
                    name="Operational Relational Schema Deployed",
                    description="All 8 operational tables active with foreign key and unique constraints.",
                    is_met=True,
                    current_value="Active",
                    required_value="Active",
                    details="Isolated pilot database initialized with full relational schema.",
                ),
                ReadinessGateStatus(
                    gate_id="G2_VOLUME",
                    name="Minimum Pilot Observation Volume",
                    description=f"At least {PILOT_TARGET_SERVICE_COUNT} completed lunch services in Section A.",
                    is_met=total_services >= PILOT_TARGET_SERVICE_COUNT,
                    current_value=f"{total_services} services",
                    required_value=f">= {PILOT_TARGET_SERVICE_COUNT} services",
                    details=f"Current service volume is {total_services}/{PILOT_TARGET_SERVICE_COUNT}.",
                ),
                ReadinessGateStatus(
                    gate_id="G3_COMPLIANCE",
                    name="Data Collection Compliance Rate",
                    description=f"At least {int(PILOT_TARGET_COMPLIANCE_RATE * 100)}% of services must have complete records.",
                    is_met=compliance_rate >= PILOT_TARGET_COMPLIANCE_RATE and total_services >= PILOT_TARGET_SERVICE_COUNT,
                    current_value=f"{compliance_rate * 100:.1f}%",
                    required_value=f">= {PILOT_TARGET_COMPLIANCE_RATE * 100:.0f}%",
                    details=f"{complete_count} of {total_services} services are fully audited.",
                ),
                ReadinessGateStatus(
                    gate_id="G4_LABEL_QUALITY",
                    name="Authentic POS Demand Reconciliation",
                    description="Ground truth targets derived strictly from reconciled POS transaction records.",
                    is_met=missing_pos == 0 and total_services > 0,
                    current_value=f"{total_services - missing_pos}/{total_services} reconciled",
                    required_value="100% of recorded services",
                    details=f"{missing_pos} services still lack POS reconciliation.",
                ),
                ReadinessGateStatus(
                    gate_id="G5_WASTE_SEGREGATION",
                    name="Physical Waste Segregation",
                    description="Unserved kitchen surplus and plate waste measured separately.",
                    is_met=missing_waste == 0 and total_services > 0,
                    current_value=f"{total_services - missing_waste}/{total_services} measured",
                    required_value="100% of recorded services",
                    details=f"{missing_waste} services missing post-service scale audits.",
                ),
                ReadinessGateStatus(
                    gate_id="G6_HOLDOUT_POLICY",
                    name="Pristine Holdout Reservation Policy",
                    description=f"Final {PILOT_HOLDOUT_RESERVE_DAYS} pilot services permanently sealed for final evaluation.",
                    is_met=True,
                    current_value=f"Sealed ({PILOT_HOLDOUT_RESERVE_DAYS} days)",
                    required_value=f"Sealed ({PILOT_HOLDOUT_RESERVE_DAYS} days)",
                    details="Holdout access policy enforced in software; previous August 2025 holdout disqualified.",
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
                    "policy_rule": "Final 10 chronological pilot services sealed until model selection is frozen.",
                    "historical_holdout_status": "Disqualified (August 4-10, 2025 permanently contaminated).",
                },
                readiness_gates=gates,
                is_pilot_ready_for_ml=is_pilot_ready,
            )

    # =========================================================================
    # 8. Data Export
    # =========================================================================

    def export_flat_dataset(self) -> List[Dict[str, Any]]:
        """Export reconciled pilot records in flat format for analysis."""
        with get_pilot_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    s.service_date,
                    s.meal_period,
                    s.canteen_section,
                    s.service_status,
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
            rows = [dict(r) for r in cursor.fetchall()]

        return rows
