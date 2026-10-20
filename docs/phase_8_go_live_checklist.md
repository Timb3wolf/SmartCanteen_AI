# Phase 8: Operational Pilot Go-Live Protocol & Checklist

**Date**: 2026-10-20  
**Target Environment**: Canteen Section A (Lunch Service Pilot)  
**System Status**: Pipeline Hardened & Verified  
**Go-Live Decision**: **CONDITIONAL APPROVAL** (Software ready; live staff collection pending deployment blockers)  

---

## 1. Executive Go-Live Decision Summary

The SmartCanteen AI Phase 8 audit has successfully hardened the data collection engine:
- Full database isolation prevents any contamination of the production forecasting database.
- Backend enforcement of the $T-4\text{h}$ prediction cutoff guarantees temporal integrity.
- Auditable before/after state diffs with mandatory justification preserve complete operational traceability.
- POS CSV ingestion is protected against batch duplicates, payload exhaustion, and unscheduled services.
- 4-state readiness gates honestly reflect pilot progress without synthetic claims.
- The 10-service chronological holdout is cryptographically and logically isolated against exploratory data snooping.

**However, live staff data collection must NOT commence until the 3 operational blockers listed below are satisfied.**

---

## 2. Pre-Deployment Operational Blockers

Before staff members are issued tablets in the kitchen and dining hall, the following three blockers must be resolved by systems engineering and canteen management:

```
[ BLOCKER 1: Authentication / Identity Provider ]
  Status: OPEN (Tagged as unverified_client_claim in current audit logs)
  Requirement: Connect FastAPI backend to organization Identity Provider (OAuth2 / OIDC / Badge SSO).
  Owner: DevOps / Enterprise IT

[ BLOCKER 2: Scale Hardware Calibration & Tare Protocol ]
  Status: PENDING PHYSICAL VERIFICATION
  Requirement: Verify kitchen floor scale and digital counter scales with standard 5.00 kg test weight.
  Owner: Kitchen Facilities Supervisor

[ BLOCKER 3: POS Export Schema Alignment ]
  Status: PENDING TEST FILE
  Requirement: Perform test end-of-day export from register terminal; verify exact column match.
  Owner: POS Vendor / Canteen Cashier Lead
```

---

## 3. Daily Staff Operational Protocol (Step-by-Step)

The daily pilot data collection process follows six disciplined operational phases:

```
+----------------------------------------------------------------------------------------------------+
|                                    Daily Meal Service Lifecycle                                    |
+-------------------+--------------------+--------------------+--------------------+-----------------+
| Phase A           | Phase B            | Phase C            | Phase D            | Phase E & F     |
| Pre-Service Setup | Cooking & Prep     | Service & Counters | POS Ingestion      | Waste & Audit   |
| (T-24h to T-4h)   | (T-4h to T-0.5h)   | (T-0h to T+2h)     | (T+2h to T+2.5h)   | (T+2.5h to T+3h)|
+-------------------+--------------------+--------------------+--------------------+-----------------+
```

### Phase A: Pre-Service Setup ($T-24\text{h}$ to $T-4\text{h}$)
*Responsible: Head Chef / Kitchen Manager*
1. **Schedule Service**: Open Staff UI (`/pilot`), click **"Schedule New Service"**, select Date, Lunch period, and Section A.
2. **Assign Menu Items**: Add all scheduled dishes from the catalog. Enter planned portion targets and unit pricing.
3. **Capture Pre-Service Headcount**:
   - Query campus timetable / room booking registry for expected lunch crowd.
   - Enter headcount observation **prior to the $T-4\text{h}$ prediction cutoff** (e.g. before 07:30 AM for an 11:30 AM lunch).
   - *Verification*: Confirm no amber "Late Entry" badge appears on the observation card.

### Phase B: Cooking & Batch Portioning ($T-3\text{h}$ to $T-0.5\text{h}$)
*Responsible: Lead Station Cook*
1. **Prepare Batches**: Cook scheduled menu dishes according to standard recipe specifications.
2. **Weigh & Count**: Place completed hotel pan on digital scale, subtract empty pan tare, and count portions.
3. **Log Production Record**:
   - Open dish card in UI, enter `Portions Prepared` and `Cooked Weight (kg)`.
   - Submit record.
4. **Corrections (if needed)**:
   - If scale tare was incorrect, click **"Auditably Correct"**, input revised values and a mandatory explanation (e.g., *"Tare weight of double-deep GN pan was 1.45 kg, not 1.25 kg"*).

### Phase C: Serving & Stockout Monitoring ($T-0\text{h}$ to $T+2\text{h}$)
*Responsible: Serving Line Steward / Cashier*
1. **Advance Service Status**: Tap **"Advance to Serving"** at 11:30 AM.
2. **Monitor Stockouts**:
   - If any dish runs out before service closure (1:30 PM), immediately log stockout timestamp.
   - Note whether a substitute dish was offered.

### Phase D: Service Close & POS Reconciliation ($T+2\text{h}$ to $T+2.5\text{h}$)
*Responsible: POS Cashier Supervisor*
1. **Close Service**: Tap **"Close Service"** at 1:30 PM.
2. **Export Register Data**: Export the lunch register CSV file from the POS terminal.
3. **Import CSV**:
   - Go to POS Ingestion section in Staff UI, drag-and-drop the CSV file.
   - Click **"Validate & Ingest POS Data"**.
   - Verify summary: Check that imported row count matches register count and that duplicate transactions were skipped.

### Phase E: Waste & Scrap Measurement ($T+2.5\text{h}$ to $T+3\text{h}$)
*Responsible: Kitchen Steward / Dishwash Team*
1. **Physical Stream Separation**:
   - **Stream 1: Kitchen Leftovers (Surplus)** = Food prepared but never served to customers (clean, edible food remaining in warmers).
   - **Stream 2: Plate Waste (Customer Scraps)** = Food returned on customer trays scraped into disposal bins.
   - *CRITICAL RULE*: Never mix kitchen surplus with plate waste.
2. **Weigh Each Stream**:
   - Place green bin (Plate Waste) on floor scale, subtract tare, record weight in kg.
   - Place pan (Unserved Surplus) on scale, record weight in kg.
3. **Log Waste Record**:
   - In UI, record separate weights for Surplus and Plate Waste.
   - Select destination (`Donation`, `Biofuel`, `Compost`, or `Landfill`).

### Phase F: Supervisor Audit & Sign-off ($T+3\text{h}$)
*Responsible: Head Chef / Canteen General Manager*
1. **Review Completeness**:
   - Confirm all dishes have Cooked Portions, POS Portions, and Waste Weights logged.
   - Check that POS Portions + Surplus Portions approximately equals Cooked Portions.
2. **Sign Off**:
   - Click **"Mark as Audited"** to lock the service from further routine edits.

---

## 4. 4-State Readiness Gate Progression

The pilot will track progress toward machine learning validation across 40 operational days:

| Gate | Title | Day 0 (Today) | Day 1–30 (Exploratory Training) | Day 31–40 (Sealed Holdout) | Final ML Exit Criteria |
|---|---|---|---|---|---|
| **G1_SCHEMA** | Schema Integrity | **MET** | **MET** | **MET** | Schema verified on all connections. |
| **G2_VOLUME** | 40-Day Service Volume | **NOT_STARTED** | **BLOCKED** ($1 \le N \le 30$) | **BLOCKED** ($31 \le N \le 39$) | **MET** ($N \ge 40$ authentic services). |
| **G3_COMPLIANCE** | Staff Data Compliance | **NOT_STARTED** | **BLOCKED** or **MET** | **BLOCKED** or **MET** | $\ge 90\%$ fully logged services. |
| **G4_POS_RECON** | POS Reconciliation | **NOT_STARTED** | **BLOCKED** or **MET** | **BLOCKED** or **MET** | $100\%$ reconciled transactions. |
| **G5_STOCKOUT** | Stockout Logging | **NOT_STARTED** | **BLOCKED** or **MET** | **BLOCKED** or **MET** | All services have stockout records. |
| **G6_HOLDOUT** | Holdout Policy | **BLOCKED** | **BLOCKED** (Export protected) | **BLOCKED** (Holdout sealed) | **MET** (Sealed until evaluation). |

---

## 5. Supervisor Go-Live Sign-Off Sheet

| Role | Sign-Off Item | Verification Method | Status |
|---|---|---|---|
| **DevOps Lead** | Database path verified distinct from `predictions.db` | Ran `test_pilot_db_path_cannot_collide_with_production` | **VERIFIED PASS** |
| **Lead ML Engineer** | Temporal cutoff enforcement verified | Ran `test_preservice_features_temporal_integrity` | **VERIFIED PASS** |
| **QA Engineer** | POS CSV idempotency & size bounds verified | Ran `test_pos_csv_valid_import_and_idempotency` & 413 check | **VERIFIED PASS** |
| **Canteen Manager** | Kitchen staff protocol training completed | Staff briefing & trial dry-run on test service | PENDING DEPLOYMENT |
| **IT Systems** | OAuth2 / Enterprise Canteen SSO configured | Verified bearer token validation in production gateway | **DEPLOYMENT BLOCKER** |
