# Phase 9: Operational Pilot Go/No-Go Decision Report

**Report ID**: `REP-GOLIVE-09`  
**Date**: 2026-10-20  
**Repository**: `SmartCanteen_AI`  
**Branch**: `ml/phase-9-pilot-go-live`  
**Target Environment**: Canteen Section A Lunch Service  
**Auditor**: Lead Systems & ML Infrastructure Engineer  
**Final Decision**: **NO-GO FOR UNRESTRICTED PRODUCTION STAFF ROLLOUT**  
**Authorized Status**: **APPROVED FOR SUPERVISED PILOT DRY-RUN ONLY**  

---

## 1. Executive Summary & Decision Justification

The SmartCanteen AI Phase 9 hardening has successfully delivered an isolated, auditable, and temporally robust operational data-capture engine. The software architecture strictly prevents pre-service temporal data leakage, enforces immutable holdout cohort partitioning, validates upload payload sizes, and guarantees zero contamination of the production forecasting database.

However, in accordance with disciplined engineering standards:
> **A successful software test run cannot mark an external operational requirement as met.**

Because physical scale calibration sheets remain unsigned on-site, the physical POS register export file has not yet been extracted from the canteen cashier hardware, and the enterprise Identity Provider (IdP/SSO) is not yet integrated with the canteen network, **the system is officially rated NO-GO for general staff deployment.**

A **SUPERVISED OPERATIONAL DRY-RUN** is authorized in an isolated staging environment using the verified dry-run protocol.

---

## 2. Go/No-Go Requirement Verification Matrix

| # | Operational Requirement | Verification Method | Empirical Evidence | Status | Responsible Party | Next Required Action |
|---|---|---|---|---|---|---|
| **R-1** | **Database Isolation & Safety** | Path comparison vs `predictions.db` in `validate_pilot_db_path()` | `test_pilot_db_path_cannot_collide_with_production` passed | **`MET`** | Systems Engineer | Maintain separate DB file paths across environments |
| **R-2** | **Disaster Recovery & Backup** | SQLite online backup API & full wipe/restoration test | `test_database_online_backup_and_disaster_recovery_restoration` passed | **`MET`** | DevOps Lead | Configure automated 3:00 PM cron backup |
| **R-3** | **Pre-Service Temporal Boundaries** | Cutoff $T-4\text{h}$ enforcement & late-entry detection | `test_preservice_features_temporal_integrity` passed | **`MET`** | ML Engineer | Monitor late-entry rates during service |
| **R-4** | **Audit Trail Immutability** | Structured before/after diffs & mandatory reason validation | `test_auditable_record_correction_and_non_destructibility` passed | **`MET`** | QA Engineer | Audit reason logs weekly |
| **R-5** | **Holdout Freezing & Anti-Snooping** | Dedicated `holdout_cohorts` table & export exclusion | `test_holdout_cohort_reservation_validation_and_sealing` passed | **`MET`** | ML Engineer | Seal Services 31–40 before exploratory modeling |
| **R-6** | **Software Automated Test Suite** | Full backend test suite execution across all modules | 158/158 tests passed in 45.03s | **`MET`** | CI/CD Pipeline | Maintain 100% test pass threshold |
| **R-7** | **Frontend Production Build** | TypeScript compiler check and Vite client bundle | `npm run build` completed in 3.34s with 0 errors | **`MET`** | Frontend Lead | Deploy bundle to staging kiosk tablets |
| **R-8** | **Enterprise Identity Provider (IdP)** | OAuth2/OIDC/SSO integration for staff badge authentication | Zero-dependency HS256 JWT module built; enterprise IdP not connected | **`BLOCKED`** | Campus IT / Security | Wire FastAPI backend to enterprise Active Directory / Okta |
| **R-9** | **Real POS Hardware Export** | Terminal register CSV dump extraction and schema mapping | Ingestion engine verified with synthetic fixtures; real hardware export pending | **`BLOCKED`** | POS Vendor / Canteen IT | Generate and validate authentic register export on Terminal A |
| **R-10** | **Physical Scale Calibration** | Class M1 test weight verification and physical tare sign-off | Protocol drafted; physical inspection sheets pending on-site execution | **`BLOCKED`** | Facilities Technician | Execute zero, tare, and repeatability checks with 5.00 kg weight |

---

## 3. Detailed Status of Deployment Blockers

### Blocker 1: Enterprise Identity Provider Integration (BLOCKED)
- **Current State**: The system implements an RFC 7519 compliant HS256 JWT security layer with granular RBAC (`staff`, `supervisor`, `auditor`, `admin`). Unauthenticated requests are rejected with HTTP 401, and unauthorized role escalations return HTTP 403.
- **Why Blocked**: In a live canteen environment, staff must authenticate via their physical employee RFID badges or single sign-on (SSO). The pilot host currently operates with local JWT secrets rather than an active corporate IdP connection.
- **Go-Live Prerequisite**: Connect `get_current_actor` in `backend/app/pilot/auth.py` to the campus OAuth2/OIDC discovery endpoint.

### Blocker 2: Real POS Terminal Export Verification (BLOCKED)
- **Current State**: The backend POS parser (`import_pos_csv`) handles batch duplicates, idempotent skips, payload limits (2 MB), and unscheduled services, verified against synthetic fixtures.
- **Why Blocked**: Real cash registers frequently exhibit undocumented formatting quirks (e.g. carriage return variations, non-standard column headers, localized decimal commas, split tender transaction lines).
- **Go-Live Prerequisite**: Canteen cashier lead must extract a live CSV dump from Terminal A and run a verification pass using `docs/phase_9_pos_verification.md`.

### Blocker 3: Physical Scale Calibration & Tare Sign-Off (BLOCKED)
- **Current State**: Data contracts enforce separation between cooked batch weight, unserved surplus, and customer plate waste.
- **Why Blocked**: Software cannot detect whether a physical scale has drifted or whether cooks have tared pans correctly.
- **Go-Live Prerequisite**: The facilities technician must physically test `SCALE-KIT-01` and `SCALE-WST-01` with certified 5.000 kg test weights and sign the physical log sheet.

---

## 4. Supervised Operational Dry-Run Clearance

While unrestricted staff deployment is on hold, the system is **CLEARED FOR A SUPERVISED PILOT DRY-RUN** under the following conditions:
1. **Isolated Sandbox Database**: The dry run must execute on a dedicated test database (`data/pilot/pilot_dryrun_sandbox.db`).
2. **Authorized Lead Operator**: A senior engineer or canteen supervisor must supervise all data entries.
3. **12-Step Protocol**: Follow the runbook in `docs/phase_9_deployment_runbook.md`.
4. **No Synthetic Contamination**: Dry run records must be wiped or kept strictly separate from the genuine 40-day operational dataset.

---

## 5. Next Actions for Pilot Launch

```
[ IMMEDIATE ACTIONS TIMELINE ]
├── T+0 Days: Execute Supervised Operational Dry-Run in Sandbox.
├── T+2 Days: Campus IT wires enterprise OAuth2/OIDC SSO credentials.
├── T+3 Days: Facilities technician executes physical scale calibration with Class M1 weights.
├── T+4 Days: POS lead extracts Terminal A sample export and verifies schema.
└── T+5 Days: Formal Go-Live Re-evaluation & Launch of Day 1 Operational Pilot.
```
