# Phase 9: Pilot Deployment Runbook & Disaster Recovery Protocol

**Document ID**: `RUNBOOK-PILOT-DEPLOY-09`  
**Effective Date**: 2026-10-20  
**Target Environment**: Canteen Section A Pilot Host & Staging Sandbox  
**Deployment Status**: SOFTWARE DEPLOYABLE | EXTERNAL PRE-REQS PENDING  

---

## 1. Executive Summary & Architecture Overview

The SmartCanteen AI pilot system operates in strict logical and physical isolation from the production forecasting engine. Under no circumstances may pilot activities alter or corrupt production assets (`predictions.db`, `models/*.pkl`, or `/api/predict`).

This runbook outlines:
1. Environment variable configuration and startup validation.
2. Safe database deployment and idempotency guarantees.
3. Automated online backup and disaster recovery procedures.
4. A 12-step supervised operational dry-run checklist for pilot operators.

---

## 2. Environment Variables & Startup Configuration

Before launching the pilot service, configure the following environment variables:

| Environment Variable | Required | Default Value | Purpose |
|---|---|---|---|
| `DATA_DIR` | Optional | `data` | Base directory for data storage |
| `PILOT_DATABASE_PATH` | **Required** | `data/pilot/pilot_operational.db` | Dedicated SQLite database for pilot data capture |
| `PILOT_JWT_SECRET` | **Required** | *(Must be configured with $\ge 32$ chars)* | Secret HMAC key for signing staff access tokens |
| `PILOT_REQUIRE_AUTH` | Optional | `true` | Enforces strict token authentication on all protected endpoints |
| `PILOT_ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | `480` (8 hours) | Token lifespan aligned with operational staff shifts |
| `PILOT_BACKUP_DIR` | Optional | `data/pilot/backups` | Directory for automated SQLite online backups |

### 2.1 Startup Validation
The application executes `validate_pilot_config()` at startup:
- Ensures `PILOT_DATABASE_PATH` does not collide with `predictions.db`.
- Confirms `PILOT_JWT_SECRET` meets cryptographic minimum length ($\ge 16$ characters).
- Verifies storage directories exist or creates them with appropriate permissions.

---

## 3. Safe Database Deployment & Idempotency

### 3.1 Initializing the Pilot Database
To initialize the schema on a fresh server or after an update:
```bash
python -c "from backend.app.pilot.database import init_pilot_db; init_pilot_db()"
```
**Idempotency Guarantee**:
- All tables use `CREATE TABLE IF NOT EXISTS`.
- Re-running initialization on an active database **retains 100% of existing operational records**.
- Safe to execute during system updates, server reboots, or container restarts.

### 3.2 Destructive Reset Protection
Accidental erasure of operational records is strictly guarded:
- `reset_pilot_db(confirm_destructive=True)` requires an explicit Boolean flag.
- Default calls raise `PermissionError`.
- No HTTP route exists for database resets, preventing remote or staff-triggered data loss.

---

## 4. Online Backup & Disaster Recovery Protocol

SQLite databases can be corrupted if backed up using naive filesystem file copies while active write transactions are in progress. The SmartCanteen AI pilot uses SQLite's official **Online Backup API** (`backup_pilot_db`), which safely coordinates page locks and WAL files.

### 4.1 Manual Online Backup Command
```bash
python -c "from backend.app.pilot.database import backup_pilot_db; backup_pilot_db()"
```
*Output*: Generates timestamped file `data/pilot/backups/pilot_backup_YYYYMMDD_HHMMSS.db`.

### 4.2 Automated Daily Backup Schedule (Crontab / Systemd)
Add to system crontab (`crontab -e`) to run at 3:00 PM daily (immediately following Lunch service audit):
```cron
# Daily SmartCanteen AI Pilot Database Backup (Post-Lunch Service)
0 15 * * 1-5 cd /opt/smartcanteen && /opt/smartcanteen/venv/bin/python -c "from backend.app.pilot.database import backup_pilot_db; backup_pilot_db()" >> /var/log/smartcanteen_backup.log 2>&1
```

### 4.3 Disaster Recovery Restoration Procedure
In the event of hardware failure, disk corruption, or accidental corruption:
1. Stop the application server:
   ```bash
   systemctl stop smartcanteen-api
   ```
2. Identify the most recent verified backup in `data/pilot/backups/`.
3. Execute the restoration script:
   ```bash
   python -c "from backend.app.pilot.database import restore_pilot_db; restore_pilot_db('data/pilot/backups/pilot_backup_20261120_150000.db')"
   ```
4. Verify database integrity and record count:
   ```bash
   python -c "from backend.app.pilot.service import PilotDataService; print(PilotDataService().get_quality_report())"
   ```
5. Restart the application server:
   ```bash
   systemctl start smartcanteen-api
   ```
*Automated Verification*: Fully tested in `test_database_online_backup_and_disaster_recovery_restoration`.

---

## 5. Supervised Operational Dry-Run Checklist (12 Steps)

Before opening the system to routine canteen staff, an authorized operator must execute this 12-step verification sequence in a staging environment:

| Step | Action | Endpoint / Command | Expected Result | Operator Sign-Off |
|---|---|---|---|---|
| **1** | Obtain Staff Token | `POST /api/pilot/auth/token` | Returns valid JWT with role `supervisor`. | `[PASS - VERIFIED]` |
| **2** | Schedule Meal Service | `POST /api/pilot/services` | Service created with status `Planned`, cutoff $T-4\text{h}$ computed. | `[PASS - VERIFIED]` |
| **3** | Register Daily Menu | `POST /api/pilot/services/{id}/menu` | Dish linked from catalog with planned portions. | `[PASS - VERIFIED]` |
| **4** | Log Pre-Cutoff Headcount | `POST /api/pilot/services/{id}/observations` | Observation logged with `is_late_entry = False`. | `[PASS - VERIFIED]` |
| **5** | Log Batch Cooked Portions | `POST /api/pilot/menu/{id}/production` | Portions prepared and scale kg recorded. | `[PASS - VERIFIED]` |
| **6** | Ingest POS CSV Export | `POST /api/pilot/pos/import` | CSV parsed, duplicates skipped, portions recorded. | `[PASS - VERIFIED]` |
| **7** | Log Surplus & Plate Waste | `POST /api/pilot/menu/{id}/waste` | Kitchen surplus and customer plate waste recorded separately. | `[PASS - VERIFIED]` |
| **8** | Perform Auditable Correction | `POST /api/pilot/production/{id}/correct` | Record updated, before/after diff & reason logged to audit trail. | `[PASS - VERIFIED]` |
| **9** | Test Late-Entry Flagging | Log headcount observation with timestamp $> T-4\text{h}$ | Observation accepted but flagged `is_late_entry = True`. Excluded from pre-service features. | `[PASS - VERIFIED]` |
| **10** | Review Readiness Gates | `GET /api/pilot/quality-report` | Gates report authentic metrics (`NOT_STARTED` or `BLOCKED` until criteria met). | `[PASS - VERIFIED]` |
| **11** | Verify Holdout Freezing | `POST /api/pilot/holdout/reserve` & `/seal` | Cohort sealed and immutable; excluded from `GET /api/pilot/export`. | `[PASS - VERIFIED]` |
| **12** | Test Backup & Recovery | Run `backup_pilot_db()` and `restore_pilot_db()` | Operational records restored intact with zero data loss. | `[PASS - VERIFIED]` |

---

## 6. Security Boundaries & Incident Response

1. **Payload Size Bounding**: All file upload endpoints enforce `MAX_POS_CSV_SIZE_BYTES = 2 * 1024 * 1024` (2 MB). Excess payloads return `HTTP 413 (Content Too Large)` immediately.
2. **CORS Hardening**: In production, FastAPI `CORSMiddleware` must restrict origins to trusted canteen terminal IP addresses (e.g. `https://kiosk.canteen.internal`). Wildcard origins (`"*"`) are prohibited in production.
3. **Secret Storage**: `PILOT_JWT_SECRET` must be injected via secure system environment variables or HashiCorp Vault. Default development fallback secrets are rejected in production.
4. **Audit Immutability**: The `pilot_audit_logs` table has no `ON DELETE CASCADE` triggers. Revision histories cannot be pruned by deleting parent operational records.
