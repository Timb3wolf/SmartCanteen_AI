"""SQLite database connection and schema manager for the isolated Pilot Data Store.

Enforces:
- Foreign key constraints (PRAGMA foreign_keys = ON)
- Strict unique constraints on meal services and menu allocations
- Audit trail logging and revision tracking via superseded_by_id
- Complete physical separation from production database
"""

from pathlib import Path
import sqlite3
from typing import Optional
from backend.app.pilot.config import PILOT_DATABASE_PATH


def get_pilot_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create and return an isolated SQLite connection with foreign keys enabled."""
    target_path = db_path or PILOT_DATABASE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_pilot_db(db_path: Optional[Path] = None) -> None:
    """Initialize all 8 Phase 6 relational tables and audit logging table."""
    with get_pilot_connection(db_path) as conn:
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

        # 9. Pilot_Audit_Log
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pilot_audit_logs (
                log_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT,
                performed_by TEXT,
                timestamp TEXT NOT NULL
            );
            """
        )

        conn.commit()


def reset_pilot_db(db_path: Optional[Path] = None) -> None:
    """Drop and re-create pilot tables (used in isolated unit tests)."""
    with get_pilot_connection(db_path) as conn:
        cursor = conn.cursor()
        tables = [
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
    init_pilot_db(db_path)
