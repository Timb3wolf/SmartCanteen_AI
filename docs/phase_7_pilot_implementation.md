# Phase 7: Operational Pilot Implementation

## 1. Executive Summary

Phase 7 implements a production-conscious, strictly isolated operational data capture prototype for SmartCanteen AI, executing the design specifications established in Phase 6.

**Critical Scope Boundary**:
This phase is exclusively concerned with collecting trustworthy, auditable, real-world operational data. **No machine learning models are trained, tuned, evaluated, or deployed in Phase 7.** Existing legacy prediction endpoints (`/api/predict`), model artifacts (`models/*.pkl`), SQLite prediction history (`predictions.db`), and forecasting behavior remain completely untouched.

---

## 2. System Architecture & Physical Isolation

The pilot infrastructure is physically and logically partitioned from existing application components:

```
SmartCanteen_AI/
├── backend/app/
│   ├── main.py                     # Registers /api/pilot router
│   ├── pilot/                      # Isolated Pilot Subsystem
│   │   ├── __init__.py
│   │   ├── config.py               # Pilot database path & operational parameters
│   │   ├── database.py             # Schema DDL, SQLite connection factory, PRAGMA foreign_keys
│   │   ├── schemas.py              # Pydantic v2 validation models
│   │   ├── service.py              # Pilot business logic, audit engine, POS CSV parser
│   │   └── router.py               # Versioned FastAPI endpoints under /api/pilot
│   └── tests/
│       └── test_pilot_data_capture.py # Comprehensive automated test suite
├── data/
│   ├── pilot_operational.db        # Physical SQLite pilot database (excluded from Git)
│   └── raw/                        # Historical legacy CSV (untouched)
├── frontend/src/
│   ├── pages/
│   │   └── PilotDataCapturePage.tsx # Staff data collection workflow interface
│   ├── services/
│   │   └── api.ts                  # Pilot API client methods
│   └── types/
│       └── pilot.ts                # Strict TypeScript data contracts
└── docs/                           # Phase 7 documentation deliverables
```

### Physical Data Store Isolation
- **Separate SQLite File**: Stored at `data/pilot_operational.db` by default (configurable via `PILOT_DATABASE_PATH`).
- **Git Safety**: The database path matches `*.db` in `.gitignore`, preventing accidental commits of local pilot operational state.
- **Foreign Key Invariant**: Every connection enforces `PRAGMA foreign_keys = ON;`.
- **Zero Impact on Production**: The legacy database `predictions.db` and the historical dataset `SmartCanteen_Final_Dataset.csv` are never referenced or modified by pilot code.

---

## 3. Relational Pilot Schema

The pilot data store implements the 8 relational entities specified in `docs/operational_data_model.md` plus an immutable audit log:

| Table | Primary Key | Description & Integrity Invariants |
| :--- | :--- | :--- |
| `meal_services` | `service_id` | Deterministic ID `{YYYY-MM-DD}_{Meal}_Section_{Sec}`. Unique constraint on `(service_date, meal_period, canteen_section)`. |
| `menu_items` | `item_id` | Master dish catalog. Non-negative `standard_portion_grams > 0`. |
| `meal_menus` | `menu_entry_id` | Junction associating dishes to meal services. Planned portions $\ge 0$. |
| `demand_observations` | `observation_id` | Pre-service headcount estimates recorded before the $T - 4\text{h}$ prediction cutoff. |
| `production_records` | `production_id` | Kitchen batch logs. Portions prepared $\ge 0$, cooked weight in kg $\ge 0.0$. |
| `service_records` | `service_record_id`| POS dispensed portions $\ge 0$, stockout occurrence flag, and stockout timestamp. |
| `waste_records` | `waste_id` | Unserved kitchen surplus (kg) $\ge 0.0$ and plate waste (kg) $\ge 0.0$ stored independently. |
| `forecast_records` | `forecast_id` | Prediction audit table preserving generated forecasts, model version, and cutoff timestamps. |
| `pilot_audit_logs` | `log_id` | Immutable append-only record of every create, update, and POS ingestion event. |

---

## 4. Configuration & Environment

The pilot data store is configured through `backend/app/pilot/config.py`:

```python
# Environment variable override:
# export PILOT_DATABASE_PATH="/custom/path/to/pilot.db"

PILOT_DATABASE_PATH = Path(os.getenv("PILOT_DATABASE_PATH", "data/pilot_operational.db"))
PILOT_CANTEEN_SECTION = "A"
PILOT_MEAL_PERIOD = "Lunch"
TARGET_SERVICES_COUNT = 40
TARGET_COMPLIANCE_RATE = 0.90
HOLDOUT_RESERVE_DAYS = 10
```

---

## 5. Setup & Safe Reset Instructions

### Automatic Initialization
When FastAPI starts, `backend.app.pilot.database.init_pilot_db()` runs automatically if the database does not exist, creating all tables and indexes.

### Manual Initialization via Python
```python
from backend.app.pilot.database import init_pilot_db
init_pilot_db()
print("Pilot database initialized.")
```

### Safe Reset Procedure
To completely reset the isolated pilot database without affecting production state:
```python
from backend.app.pilot.database import reset_pilot_db
# Drops only the 8 pilot tables and pilot_audit_logs in data/pilot_operational.db
reset_pilot_db()
```
Or delete the physical file `data/pilot_operational.db`—it will be automatically re-created clean on the next API call or service startup.

---

## 6. Pilot API Endpoints

All pilot routes are prefixed with `/api/pilot`:

### Meal Services
- `GET /api/pilot/services`: List services filtered by date, meal period, section, or status.
- `POST /api/pilot/services`: Schedule a new meal service event.
- `GET /api/pilot/services/{service_id}`: Retrieve detailed breakdown (menu, production, POS, waste, audit warnings).
- `PATCH /api/pilot/services/{service_id}/status`: Advance lifecycle status (`Planned` $\to$ `In_Prep` $\to$ `Serving` $\to$ `Closed` $\to$ `Audited`).

### Master Dish Catalog
- `GET /api/pilot/menu-items`: List all catalog dishes.
- `POST /api/pilot/menu-items`: Register a new dish recipe with portion size and category.
- `POST /api/pilot/services/{service_id}/menu`: Associate a catalog dish with a scheduled service.

### Kitchen & POS Logging
- `POST /api/pilot/services/{service_id}/observations`: Record pre-service headcount estimate ($T - 4\text{h}$ cutoff).
- `POST /api/pilot/menu/{menu_entry_id}/production`: Record batch cooking portion count and cooked weight (kg).
- `POST /api/pilot/menu/{menu_entry_id}/service`: Record POS portions dispensed and early stockouts.
- `POST /api/pilot/menu/{menu_entry_id}/waste`: Record unserved surplus weight (kg) and plate waste (kg) separately.

### Ingestion & Export
- `POST /api/pilot/pos/import`: Ingest end-of-day POS CSV export (supports JSON payload `POSImportPayload` or raw CSV body).
- `GET /api/pilot/quality-report`: Retrieve logging compliance, service completeness, and Phase 6 readiness gates.
- `GET /api/pilot/export`: Export validated, flat reconciled pilot records as JSON.

---

## 7. Model Isolation & Operational Limitations

1. **No ML Model Access to In-Flight Measurements**:
   Pre-service forecasts may only use observations timestamped $\le T - 4\text{h}$. Actual portions served, surplus weights, and plate waste weights are post-service variables and are strictly forbidden from pre-service feature tables.
2. **No Data Fabrication**:
   Test fixtures are isolated in `backend/app/tests/` and operate in `tmp_path`. No synthetic records are written into `data/pilot_operational.db`.
3. **Pilot Scope Enforcement**:
   The pilot is restricted to Section A, Lunch service. Other sections and meal periods can be configured but are tracked separately in data quality reporting.
