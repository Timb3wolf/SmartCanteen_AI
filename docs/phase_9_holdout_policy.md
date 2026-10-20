# Phase 9: Holdout Cohort Reservation & Immutability Policy

**Document ID**: `POL-ML-HOLDOUT-09`  
**Effective Date**: 2026-10-20  
**Pilot Domain**: SmartCanteen AI Operational Pilot (Section A, Lunch Service)  
**Status**: ACTIVE & FORMALIZED  

---

## 1. Executive Summary & Purpose

The SmartCanteen AI forecasting system requires ground-truth operational validation before any machine learning model may be deployed for automated prep guidance. Benchmark results from synthetic datasets (Phases 0–5) confirmed that premature model training on unverified or shifting targets produces misleading accuracy claims and risks severe food waste or stockouts.

To preserve the absolute statistical validity of the future evaluation, the operational pilot establishes an **immutable chronological holdout cohort**:
- **Target Observation Volume**: 40 genuine, eligible operational services.
- **Exploratory Analysis Cohort**: Services 1 through 30 (used for exploratory data analysis, feature engineering, and cross-validation benchmarking).
- **Frozen Holdout Cohort**: Services 31 through 40 (10 consecutive operational days) reserved exclusively for a single, locked out-of-sample evaluation.

This document formalizes the architectural safeguards, data model, lifecycle transitions, and audit mechanisms preventing data snooping and target leakage.

---

## 2. Evaluation Cohort Specification

```
+----------------------------------------------------------------------------------------------------+
|                                    40-Day Pilot Service Timeline                                   |
+--------------------------------------------------------------+-------------------------------------+
|                      Services 1 to 30                        |          Services 31 to 40          |
|                  (Exploratory Benchmarking)                  |      (SEALED Chronological Holdout) |
+--------------------------------------------------------------+-------------------------------------+
| - Eligible for exploratory statistics                        | - Strictly excluded from exports    |
| - Feature selection and lag tuning                           | - Frozen service IDs                |
| - Candidate model cross-validation                           | - Zero exploratory data snooping    |
| - Model architecture and hyperparameter freeze               | - Released only for locked eval     |
+--------------------------------------------------------------+-------------------------------------+
```

### 2.1 Eligible Service Criteria
A meal service qualifies for inclusion in the evaluation cohort if and only if it satisfies all of the following invariants:
1. `canteen_section = 'A'`: Physical serving line A in the main campus canteen.
2. `meal_period = 'Lunch'`: Standard lunch service (11:30 AM – 1:30 PM).
3. `service_status = 'Audited'`: Fully completed operational lifecycle with verified production, POS register reconciliation, and waste weighings.
4. `is_temporal_boundary_valid = True`: Contains verified pre-service headcount observations logged prior to the $T-4\text{h}$ prediction cutoff (07:30 AM).

---

## 3. Database Schema & Immutability Architecture

Holdout cohort membership is governed by the dedicated relational table `holdout_cohorts` in the isolated pilot database (`data/pilot/pilot_operational.db`), created during Phase 9 hardening:

```sql
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
```

### 3.1 Cohort Lifecycle State Machine

```
              [ DRAFT / DEFINED ]
                      |
                      v  (reserve_holdout_cohort)
                [ RESERVED ]
                      |  (Pre-sealing updates permitted with audit)
                      |
                      v  (seal_holdout_cohort - Admin Only)
                 [ SEALED ]  <--- STRICTLY IMMUTABLE (Modifications Prohibited)
                      |
                      v  (release_holdout_cohort - Post Model Freeze)
                [ RELEASED ]
```

1. **`RESERVED`**:
   - The cohort has been created and populated with exactly 10 eligible service IDs.
   - Pre-sealing adjustments (e.g. replacing a cancelled service) are permitted only by an administrator providing mandatory justification. Every change appends an immutable entry to `change_history_json`.
2. **`SEALED`**:
   - The holdout cohort is permanently locked prior to any exploratory model analysis.
   - **Absolute Immutability**: Any call to `update_holdout_cohort` on a `SEALED` cohort immediately raises `ValueError("Holdout cohort is SEALED and strictly immutable. Changes to reserved service IDs are prohibited.")`.
   - The set of service IDs is frozen and cannot be changed by inserting backdated records, reordering dates, or deleting other records.
3. **`RELEASED`**:
   - The holdout cohort is unlocked only after candidate ML models have been completely finalized, trained, and frozen.
   - Unlocks ground truth targets for the final, one-shot evaluation report.

---

## 4. Anti-Snooping Export Enforcement

### 4.1 Default Holdout Masking
- The core data export routine (`export_flat_dataset(exclude_holdout=True)`) and REST API (`GET /api/pilot/export?exclude_holdout=true`) strictly exclude all records associated with `SEALED` or `RESERVED` holdout service IDs.
- Data scientists, researchers, and automated pipelines running exploratory scripts cannot access holdout rows.

### 4.2 Audited Bypass Protection
- If an administrator explicitly requests an unprotected export (`exclude_holdout=False`):
  1. The caller must possess the `admin` or `auditor` role.
  2. The system immediately logs a security audit record to `pilot_audit_logs` with `action = 'HOLDOUT_ACCESS'`, recording the actor ID, timestamp, and row count.
  3. The bypass is flagged in the pilot quality report.

---

## 5. Mathematical Proof: Invariance to Backdating and Reordering

In Phase 8, holdout partitioning was dynamically calculated from `all_services[30:]`. This presented a vulnerability where:
$$\text{If } S_{\text{new}} < S_{\text{holdout\_start}} \implies \text{Index shift occurs: } S_{30} \to S_{31}$$
A backdated service insertion would shift earlier services into the holdout cohort and push intended holdout services out into exploratory training.

In Phase 9:
Let $\mathcal{H} = \{s_1, s_2, \dots, s_{10}\}$ be the explicit set of service UUIDs stored in `holdout_cohorts.reserved_service_ids_json`.
For any new meal service $s_{\text{new}}$ created at date $t_{\text{new}}$:
$$s_{\text{new}} \notin \mathcal{H} \implies \mathcal{H} \text{ remains identical.}$$
$$\forall s_i \in \mathcal{H}, \quad \text{Status}(s_i) = \text{SEALED} \implies s_i \in \mathcal{H}_{\text{export\_excluded}}.$$

Automated regression test `test_holdout_frozen_ids_immune_to_backdating_and_reordering` in `test_pilot_go_live_hardening.py` executes this exact scenario, asserting that inserting backdated services has zero effect on the reserved holdout set.

---

## 6. Audit & Compliance Checklist

| Invariant | Enforcement Mechanism | Verification Test |
|---|---|---|
| Minimum 10 Services | `len(reserved_service_ids) >= 10` enforced at sealing | `test_holdout_cohort_reservation_validation_and_sealing` |
| Referential Integrity | All service IDs verified against `meal_services` table | `test_holdout_cohort_reservation_validation_and_sealing` |
| Immutability | SEALED cohort rejects updates and duplicate reservations | `test_holdout_cohort_reservation_validation_and_sealing` |
| Export Exclusion | Export filters out `holdout_service_ids` | `test_holdout_export_protection_and_access_audit` |
| Access Logging | Unprotected export writes `HOLDOUT_ACCESS` audit event | `test_holdout_export_protection_and_access_audit` |
| Historical Contamination Quarantine | August 4–10, 2025 synthetic holdout permanently marked disqualified | Verified in `holdout_policy.historical_holdout_status` |
