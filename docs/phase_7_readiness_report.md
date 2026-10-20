# Phase 7: Pilot Data Quality and Readiness Report

## 1. Executive Summary

This report establishes the criteria, metrics, and gate status for determining when the SmartCanteen AI pilot data capture collection has gathered sufficient, trustworthy operational data to warrant exploratory demand modeling.

**Current Verdict**:
The operational data capture prototype is fully implemented, verified, and ready for deployment. However, because real canteen pilot services have not yet commenced, **machine learning model training and evaluation remain strictly blocked**.

---

## 2. Pilot Scope Definition

As specified in Phase 6, the initial operational pilot is deliberately scoped to control variance and establish logging discipline:

- **Location**: Canteen Section A (primary student dining hall).
- **Service Period**: Lunch ($11{:}30\text{--}13{:}30$ on regular semester weekdays).
- **Duration**: 40 consecutive operational weekday services (approx. 8 calendar weeks).
- **Compliance Target**: At least $90\%$ complete services ($\ge 36$ fully logged services).
- **Holdout Boundary**: The final 10 days ($25\%$ chronological holdout) are strictly partitioned and locked prior to any exploratory model comparison.

---

## 3. Phase 6 Readiness Gates Evaluation

The system tracks six readiness gates through the `/api/pilot/quality-report` endpoint:

| Gate ID | Gate Name | Target Metric | Current Status | Blocker Rationale & Path to Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **G1_SCHEMA** | Operational Schema Deployed | 8 tables active with Foreign Keys | **MET** | Implemented in `data/pilot_operational.db` with `PRAGMA foreign_keys = ON;`. |
| **G2_VOLUME** | 40 Consecutive Services | $\ge 40$ services logged | **BLOCKED** | Currently 0 real services logged. Requires 8 weeks of live canteen operations. |
| **G3_COMPLIANCE** | $\ge 90\%$ Logging Compliance | $\ge 90.0\%$ complete services | **BLOCKED** | Calculated dynamically as $\frac{\text{Complete Services}}{\text{Total Services}} \times 100\%$. Blocked until operations begin. |
| **G4_POS_RECON** | Verified POS Reconciliation | 0 un-reconciled services | **BLOCKED** | Requires matching POS transaction register exports for all 40 services. |
| **G5_STOCKOUT** | Stockout Truncation Flagged | True for all stockouts | **BLOCKED** | Requires real-world service observation of early depletion events. |
| **G6_HOLDOUT_POLICY** | Chronological Holdout Locked | 10 days reserved | **MET** | Policy formalized: Services 31–40 are strictly held out. Model training on these days is forbidden. |

---

## 4. Completeness & Quality Metrics Formulae

### Service Completeness Definition
A `Meal_Service` is defined as complete if and only if all of the following conditions hold:
1. **Pre-Service Observation**: At least one `Demand_Observation` exists with a timestamp $\le T - 4\text{h}$.
2. **Menu Definition**: At least one scheduled dish entry exists in `meal_menus`.
3. **Production Logged**: Every scheduled dish has at least one valid `Production_Record` with `portions_prepared > 0`.
4. **Service Reconciled**: Every scheduled dish has at least one `Service_Record` with `portions_served` recorded from POS or manual counts.
5. **Separated Waste Weighed**: Every scheduled dish has a `Waste_Record` with non-negative entries for both `unserved_surplus_weight_kg` and `plate_waste_weight_kg`.

### Compliance Rate Formula
$$\text{Logging Compliance Rate (\%)} = \left( \frac{\sum_{i=1}^{N} \mathbb{I}(\text{Service}_i \text{ is Complete})}{N} \right) \times 100\%$$
where $N = \text{total eligible services recorded in Section A Lunch}$.

---

## 5. Chronological Holdout Policy (Services 31–40)

To prevent data snooping and ensure unbiased evaluation of future ML models:
1. **Partitioning**:
   - **Exploratory Development Set**: Services 1 through 30.
   - **Chronological Holdout Set**: Services 31 through 40 (the final 10 days).
2. **Access Policy**:
   - The holdout set must **never** be used for feature selection, hyperparameter tuning, model architecture selection, or threshold tuning.
   - The holdout set is evaluated **once** only after candidate models are fully frozen.
   - Any model that accesses holdout labels before freeze is disqualified from production deployment consideration.

---

## 6. Prohibition of Synthetic Pilot Records

**Explicit Constraint**:
Automated test fixtures use temporary in-memory or `tmp_path` databases and are marked clearly as synthetic test data. Under no circumstances may synthetic, simulated, or fabricated records be inserted into `data/pilot_operational.db` or used to claim that readiness gates G2–G5 are met.

The only acceptable basis for advancing to Phase 8 (Model Retraining on Authentic Data) is genuine canteen pilot data captured from real staff operations.
