# Phase 8: Pilot Security, Database Isolation & Deployment Guide

**Date**: 2026-10-20  
**Repository**: `SmartCanteen_AI`  
**Branch**: `ml/phase-8-pilot-hardening`  
**Target Environment**: Isolated Canteen Pilot (Section A, Lunch Service)  

---

## 1. Database Isolation & Safety Architecture

The SmartCanteen AI system maintains a strict architectural boundary between the existing production forecasting service and the Phase 7/8 operational pilot data capture system. Under no circumstances may pilot activities alter, lock, or corrupt production assets.

```
+-----------------------------------------------------------------------------------+
|                              SmartCanteen AI Application                          |
+----------------------------------------+------------------------------------------+
                                         |
     [PRODUCTION DOMAIN]                 |              [OPERATIONAL PILOT DOMAIN]
+------------------------------------+   |   +------------------------------------+
|  FastAPI Endpoints: /api/predict   |   |   |  FastAPI Endpoints: /api/pilot/*   |
|  Service: ProductionPredictor      |   |   |  Service: PilotDataService         |
|  Database: predictions.db          |   |   |  Database: data/pilot/pilot_*.db   |
|  Models: models/*.pkl              |   |   |  Models: NONE (Data Collection)    |
|  Validation: Strict Backward-Compat|   |   |  Validation: 4-State Gates & Audit |
+------------------------------------+   |   +------------------------------------+
                   |                     |                     |
        (PROD READ/WRITE ONLY)           |          (PILOT READ/WRITE ONLY)
                   v                     |                     v
         [ predictions.db ]              |          [ pilot_operational.db ]
                   ^                     |                     ^
                   |                     |                     |
                   +------ BLOCKED ------+---------------------+
                    (Path Collision Guard Prevents Any Overlap)
```

### 1.1 Path Collision Guard
To prevent accidental misconfiguration or deployment script errors from pointing the pilot database to `predictions.db`:
- Every connection opened by `get_pilot_connection()` executes `validate_pilot_db_path(db_path)`.
- The target database path is resolved to its canonical absolute filesystem path (`path.resolve()`).
- If the resolved path matches `backend.app.core.config.DATABASE_PATH.resolve()`, the application immediately raises `ValueError` and terminates execution before opening the connection.

### 1.2 Foreign Key Enforcement
SQLite disables foreign-key enforcement by default on new connections. To prevent orphaned records across parent-child tables (e.g. `meal_menus -> menu_items`, `production_records -> meal_menus`):
- `get_pilot_connection()` explicitly executes `PRAGMA foreign_keys = ON;` upon connection initialization.
- Every write transaction operates under verified referential integrity.

### 1.3 Concurrency & Lock Contention
Multiple physical stations (kitchen prep tablet, serving line POS register, disposal scale) may write to SQLite simultaneously.
- `PRAGMA busy_timeout = 5000;` is executed on all pilot connections.
- If a write lock is held, incoming transactions queue up to 5,000 milliseconds before raising a busy error, eliminating spurious write lock contention during peak lunch service rushes.
- Python context managers (`with conn:`) manage atomic transactions. In the event of unhandled exceptions or constraint violations, SQLite rolls back changes atomically, leaving the operational database clean.

### 1.4 Protection Against Destructive Resets
- The function `reset_pilot_db(confirm_destructive: bool = False)` requires an explicit Boolean flag.
- Default calls raise `PermissionError("Destructive database reset blocked. Must pass confirm_destructive=True.")`.
- No destructive reset route is exposed over HTTP.

### 1.5 Git and Filesystem Exclusion
The following paths are explicitly ignored in `.gitignore`:
```gitignore
# Pilot operational databases and test scratch
data/pilot/
*.db
*.sqlite3
*.sqlite
```
Operational records containing real employee badge IDs, financial register totals, and inventory weights will never be committed to source control.

---

## 2. Authentication & Authorization Status (Deployment Blocker)

> [!CAUTION]
> **GO-LIVE DEPLOYMENT BLOCKER**: The SmartCanteen AI pilot backend currently runs with token inspection but **without an integrated enterprise Identity Provider (IdP)**. The system must NOT be deployed to an open canteen intranet without implementing the authentication layer detailed below.

### 2.1 Current State & Unverified Staff Tagging
In Phase 7, staff entered arbitrary strings into the `recorded_by` field. In Phase 8:
- The backend inspects `Authorization` (Bearer token) and `X-Staff-Auth-Token` headers via `extract_actor()`.
- If no verified identity provider validates the token, the backend records the actor as `("staff", "unverified_client_claim")` in `pilot_audit_logs.auth_status`.
- This ensures audit trails do not falsely certify unauthenticated inputs as cryptographically verified human identities.

### 2.2 Pre-Deployment Identity Provider Requirements
Before physical staff tablets are handed to cooks and cashiers, the operational deployment must wire FastAPI dependencies to the organization's existing identity system:
1. **OAuth2 / OIDC Integration**:
   - Staff authenticate via canteen badge scanning or PIN login on shared tablets.
   - FastAPI validates JWT signatures using public keys provided by the enterprise identity server.
2. **Role-Based Access Control (RBAC)**:
   - `Role: Staff`: Permitted to record pre-service headcount observations and log initial kitchen production portions.
   - `Role: Supervisor / Head Chef`: Permitted to perform auditable record corrections (`/correct`) and upload POS CSV files.
   - `Role: Auditor`: Permitted to read audit logs and review readiness gates.
   - `Role: Admin`: Permitted to configure dish catalogs and schedule meal services.

---

## 3. Network & API Security

### 3.1 Request Payload Limits
To prevent memory exhaustion via malicious or accidental uploads of multi-gigabyte files:
- `MAX_POS_CSV_SIZE_BYTES` is strictly enforced at **2 MB** (approximately 50,000 transaction rows).
- In `POST /api/pilot/pos/import`, `Content-Length` is checked first. If $> 2\text{ MB}$, the server immediately responds with `HTTP 413 (Content Too Large)` before reading the request stream.
- If `Content-Length` is absent, the incoming byte stream is bounded at 2 MB during read.

### 3.2 Safe Error Handling & Input Validation
- All pilot endpoints validate input using Pydantic V2 models.
- Numeric constraints (`ge=0.0`, `ge=0`, `min_length=5` for correction reasons) reject nonsensical operational data at the HTTP boundary.
- Unhandled internal errors return sanitized JSON messages without dumping backend Python stack traces or database schema internals to client browsers.

### 3.3 CORS Configuration
In production:
- FastAPI `CORSMiddleware` must be restricted from wildcard origins (`"*"`) to the exact domain or IP of the canteen kiosk terminals (e.g. `https://canteen-tablet.internal.canteen.com`).
- Credentials flag `allow_credentials=True` must be paired with explicit origins.

---

## 4. Physical Station & Usability Architecture

During the pilot, data is captured across three distinct physical stations in Canteen Section A:

| Physical Station | Device Type | User Role | Data Captured | Timing |
|---|---|---|---|---|
| **Kitchen Office** | Desktop / Laptop | Head Chef / Manager | Schedule Meal Services, Register Menu Items | $T-24\text{h}$ to $T-12\text{h}$ |
| **Kitchen Hot Line** | Wall-Mounted Tablet (Touch) | Lead Cook | Log Cooked Portions, Log Cooked Weight, Headcount | $T-4\text{h}$ to $T-0.5\text{h}$ |
| **Cashier Counter** | POS Terminal | Cashier / Automated Script | Ingest End-of-Day POS Transactions CSV | $T+0.5\text{h}$ (Service Close) |
| **Scullery / Dishwash** | Floor Scale + Tablet | Steward / Auditor | Weigh Unserved Kitchen Surplus & Plate Waste | $T+1\text{h}$ (Post-Service) |

### 4.1 Touch-Optimized UI & High-Pace Usability
The frontend (`PilotDataCapturePage.tsx`) was audited for high-temperature kitchen environments:
- Large interactive buttons for single-tap status advancement (`In Prep`, `Serving`, `Closed`, `Audited`).
- Clear visual indicators for late observations (amber warning badge if entered after $T-4\text{h}$).
- Real-time client-side validation preventing accidental submission of negative portion counts.
- High-contrast 4-state readiness indicators (`MET`, `BLOCKED`, `NOT_STARTED`, `INVALID`) providing unambiguous status to canteen supervisors.

---

## 5. Deployment Checklist & Health Verification

1. Verify environment configuration:
   ```bash
   # Ensure pilot database is completely separate from predictions.db
   PILOT_DATABASE_PATH=data/pilot/pilot_operational.db
   ```
2. Verify production prediction endpoint remains completely unaffected:
   ```bash
   curl -X POST http://localhost:8000/api/predict \
     -H "Content-Type: application/json" \
     -d '{"dish_name": "Pan-Seared Pork Chop", "day_of_week": "Monday", "price": 5.5, "past_waste_mean": 2.1}'
   ```
3. Initialize the pilot schema:
   ```bash
   python -c "from backend.app.pilot.database import init_pilot_db; init_pilot_db()"
   ```
4. Verify pilot readiness gate endpoint:
   ```bash
   curl http://localhost:8000/api/pilot/quality-report
   # Expected response: G1_SCHEMA=MET, G2_VOLUME=NOT_STARTED, G3_COMPLIANCE=NOT_STARTED
   ```
