"""SQLite database connection and schema manager for the isolated Pilot Data Store.

Enforces:
- Complete physical isolation from production database (path validation)
- Foreign key constraints (PRAGMA foreign_keys = ON)
- Concurrency timeout (PRAGMA busy_timeout = 5000)
- Strict unique constraints on meal services and menu allocations
- Temporal cutoff tracking and late-entry flagging
- Audit trail logging and revision tracking via superseded_by_id and correction_reason
- Safeguarded, non-accidental reset procedures
"""

from pathlib import Path
import sqlite3
from typing import Optional
from backend.app.pilot.config import PILOT_DATABASE_PATH, PILOT_TIMEZONE, validate_pilot_db_path


def get_pilot_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create and return an isolated SQLite connection with foreign keys and timeout enabled."""
    target_path = db_path or PILOT_DATABASE_PATH
    validate_pilot_db_path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_pilot_db(db_path: Optional[Path] = None) -> None:
    """Initialize all 8 Phase 6 relational tables and audit logging table."""
    target_path = db_path or PILOT_DATABASE_PATH
    validate_pilot_db_path(target_path)

    with get_pilot_connection(target_path) as conn:
        cursor = conn.cursor()

        # 1. Meal_Service
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS meal_services (
                service_id TEXT PRIMARY KEY,
                service_date TEXT NOT NULL,
                meal_period TEXT NOT NULL CHECK(meal_period IN ('Breakfast', 'Lunch', 'Dinner')),
                canteen_section TEXT NOT NULL CHECK(canteen_section IN ('A', 'B', 'C', 'D')),
                service_status TEXT NOT NULL DEFAULT 'Planned' CHECK(service_status IN ('Planned', 'In_Prep', 'Serving', 'Closed', 'Audited')),
                scheduled_start TEXT NOT NULL,
                scheduled_end TEXT NOT NULL,
                prediction_cutoff_time TEXT NOT NULL,
                service_timezone TEXT NOT NULL DEFAULT 'Asia/Colombo',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(service_date, meal_period, canteen_section)
            );
            """
        )

        # 2. Menu_Item
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_items (
                item_id TEXT PRIMARY KEY,
                item_name TEXT NOT NULL,
                food_category TEXT NOT NULL CHECK(food_category IN ('Meat', 'Rice', 'Soup', 'Vegetables')),
                standard_portion_unit TEXT NOT NULL DEFAULT 'portions',
                standard_portion_grams REAL NOT NULL DEFAULT 150.0 CHECK(standard_portion_grams > 0),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            """
        )

        # 3. Meal_Menu
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS meal_menus (
                menu_entry_id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                planned_portions INTEGER NOT NULL DEFAULT 0 CHECK(planned_portions >= 0),
                unit_price REAL NOT NULL CHECK(unit_price >= 0),
                ingredient_cost_per_portion REAL NOT NULL CHECK(ingredient_cost_per_portion >= 0),
                is_available INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (service_id) REFERENCES meal_services(service_id) ON DELETE CASCADE,
                FOREIGN KEY (item_id) REFERENCES menu_items(item_id) ON DELETE RESTRICT,
                UNIQUE(service_id, item_id)
            );
            """
        )

        # 4. Demand_Observation
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS demand_observations (
                observation_id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                observation_timestamp TEXT NOT NULL,
                expected_headcount INTEGER NOT NULL CHECK(expected_headcount >= 0),
                observation_source TEXT NOT NULL,
                registered_reservations INTEGER NOT NULL DEFAULT 0 CHECK(registered_reservations >= 0),
                is_late_entry INTEGER NOT NULL DEFAULT 0 CHECK(is_late_entry IN (0, 1)),
                prediction_cutoff_timestamp TEXT,
                notes TEXT,
                recorded_at TEXT NOT NULL,
                recorded_by TEXT,
                FOREIGN KEY (service_id) REFERENCES meal_services(service_id) ON DELETE CASCADE
            );
            """
        )

        # 5. Production_Record
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS production_records (
                production_id TEXT PRIMARY KEY,
                menu_entry_id TEXT NOT NULL,
                measurement_time TEXT NOT NULL,
                batch_number INTEGER NOT NULL DEFAULT 1 CHECK(batch_number >= 1),
                portions_prepared INTEGER NOT NULL CHECK(portions_prepared >= 0),
                prepared_weight_kg REAL CHECK(prepared_weight_kg IS NULL OR prepared_weight_kg >= 0),
                kitchen_station TEXT DEFAULT 'Main_Station',
                correction_reason TEXT,
                recorded_at TEXT NOT NULL,
                recorded_by TEXT,
                superseded_by_id TEXT,
                FOREIGN KEY (menu_entry_id) REFERENCES meal_menus(menu_entry_id) ON DELETE CASCADE,
                FOREIGN KEY (superseded_by_id) REFERENCES production_records(production_id) ON DELETE SET NULL
            );
            """
        )

        # 6. Service_Record
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS service_records (
                service_record_id TEXT PRIMARY KEY,
                menu_entry_id TEXT NOT NULL,
                measurement_time TEXT NOT NULL,
                portions_served INTEGER NOT NULL CHECK(portions_served >= 0),
                stockout_occurred INTEGER NOT NULL DEFAULT 0 CHECK(stockout_occurred IN (0, 1)),
                stockout_time TEXT,
                gross_sales_amount REAL NOT NULL DEFAULT 0.0 CHECK(gross_sales_amount >= 0),
                data_source TEXT NOT NULL DEFAULT 'POS_Register',
                correction_reason TEXT,
                recorded_at TEXT NOT NULL,
                recorded_by TEXT,
                superseded_by_id TEXT,
                FOREIGN KEY (menu_entry_id) REFERENCES meal_menus(menu_entry_id) ON DELETE CASCADE,
                FOREIGN KEY (superseded_by_id) REFERENCES service_records(service_record_id) ON DELETE SET NULL
            );
            """
        )

        # 7. Waste_Record
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS waste_records (
                waste_id TEXT PRIMARY KEY,
                menu_entry_id TEXT NOT NULL,
                measurement_time TEXT NOT NULL,
                unserved_surplus_weight_kg REAL NOT NULL CHECK(unserved_surplus_weight_kg >= 0),
                plate_waste_weight_kg REAL NOT NULL CHECK(plate_waste_weight_kg >= 0),
                disposal_destination TEXT NOT NULL DEFAULT 'Compost',
                measurement_method TEXT NOT NULL DEFAULT 'Digital_Scale',
                correction_reason TEXT,
                recorded_at TEXT NOT NULL,
                recorded_by TEXT,
                superseded_by_id TEXT,
                FOREIGN KEY (menu_entry_id) REFERENCES meal_menus(menu_entry_id) ON DELETE CASCADE,
                FOREIGN KEY (superseded_by_id) REFERENCES waste_records(waste_id) ON DELETE SET NULL
            );
            """
        )

        # 8. Forecast_Record
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS forecast_records (
                forecast_id TEXT PRIMARY KEY,
                menu_entry_id TEXT NOT NULL,
                forecast_timestamp TEXT NOT NULL,
                cutoff_timestamp TEXT NOT NULL,
                predicted_demand_portions REAL NOT NULL,
                recommended_portions INTEGER NOT NULL,
                final_adopted_portions INTEGER NOT NULL,
                human_override INTEGER NOT NULL DEFAULT 0 CHECK(human_override IN (0, 1)),
                override_reason TEXT,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                feature_snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (menu_entry_id) REFERENCES meal_menus(menu_entry_id) ON DELETE CASCADE
            );
            """
        )

        # 9. Pilot_Audit_Log (No CASCADE delete to guarantee immutable history)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_audit_logs (
                log_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                old_value_json TEXT,
                new_value_json TEXT,
                correction_reason TEXT,
                details TEXT,
                performed_by TEXT,
                auth_status TEXT DEFAULT 'unverified_client_claim',
                timestamp TEXT NOT NULL
            );
            """
        )

        # 10. Holdout_Cohorts (Explicit, immutable evaluation cohort freezing)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS holdout_cohorts (
                cohort_id TEXT PRIMARY KEY,
                pilot_id TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                eligible_service_definition TEXT NOT NULL,
                reserved_service_ids_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('RESERVED', 'SEALED', 'RELEASED')),
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                sealed_at TEXT,
                sealed_by TEXT,
                released_at TEXT,
                released_by TEXT,
                change_history_json TEXT NOT NULL
            );
            """
        )

        # Indexes for query performance and data integrity
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_services_lookup ON meal_services(service_date, meal_period, canteen_section);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meal_menus_lookup ON meal_menus(service_id, item_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_demand_obs_service ON demand_observations(service_id, observation_timestamp);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_entity ON pilot_audit_logs(entity_type, entity_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_holdout_cohorts_status ON holdout_cohorts(pilot_id, status);")

        conn.commit()


def reset_pilot_db(db_path: Optional[Path] = None, confirm_destructive: bool = False) -> None:
    """Drop and re-create pilot tables.
    
    Requires explicit confirm_destructive=True to prevent accidental resets.
    """
    if not confirm_destructive:
        raise PermissionError(
            "Destructive database reset aborted: confirm_destructive must be set to True."
        )

    target_path = db_path or PILOT_DATABASE_PATH
    validate_pilot_db_path(target_path)

    with get_pilot_connection(target_path) as conn:
        cursor = conn.cursor()
        tables = [
            "holdout_cohorts",
            "pilot_audit_logs",
            "forecast_records",
            "waste_records",
            "service_records",
            "production_records",
            "demand_observations",
            "meal_menus",
            "menu_items",
            "meal_services",
        ]
        for t in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {t};")
        conn.commit()

    init_pilot_db(target_path)


def backup_pilot_db(source_db_path: Optional[Path] = None, dest_backup_path: Optional[Path] = None) -> Path:
    """Safely back up the operational pilot database using SQLite's online backup API."""
    from datetime import datetime, timezone
    src = validate_pilot_db_path(source_db_path or PILOT_DATABASE_PATH)
    if dest_backup_path is None:
        from backend.app.pilot.config import PILOT_BACKUP_DIR
        PILOT_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        dest_backup_path = PILOT_BACKUP_DIR / f"pilot_backup_{ts}.db"
    dest_path = Path(dest_backup_path)
    validate_pilot_db_path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    with get_pilot_connection(src) as src_conn:
        with sqlite3.connect(str(dest_path)) as dst_conn:
            src_conn.backup(dst_conn)
    return dest_path


def restore_pilot_db(backup_source_path: Path, target_db_path: Optional[Path] = None) -> Path:
    """Restore the pilot database from a verified backup file."""
    src = Path(backup_source_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup file not found at '{src}'")
    tgt = validate_pilot_db_path(target_db_path or PILOT_DATABASE_PATH)
    tgt.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(src)) as src_conn:
        with get_pilot_connection(tgt) as dst_conn:
            src_conn.backup(dst_conn)
    return tgt
