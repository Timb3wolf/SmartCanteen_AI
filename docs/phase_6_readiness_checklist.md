# SmartCanteen AI — Phase 6 Data Readiness & Pilot Gating Checklist

> **Document Status:** Operational Readiness Gating Protocol  
> **Target Branch:** `ml/phase-6-operational-data-pipeline`  
> **Purpose:** Formal criteria required before transitioning from data collection to machine learning model development  

---

## 1. Executive Summary

This checklist serves as the objective quality gate between **Phase 6 (Data Infrastructure & Pilot Design)** and any future **Phase 7 (Empirical Demand Forecasting)**.

Under this gating policy, **no ML model development, training, or tuning may begin** until all mandatory verification gates in this document are confirmed with empirical data.

---

## 2. Readiness Verification Gates

### Gate 1: Operational Schema & Pipeline Infrastructure
- [ ] **1.1 Relational Schema Deployed:** The proposed operational schema (`Meal_Service`, `Menu_Item`, `Meal_Menu`, `Demand_Observation`, `Production_Record`, `Service_Record`, `Waste_Record`, `Forecast_Record`) is deployed in an isolated staging/pilot database.
- [ ] **1.2 Immutable Audit Timestamps:** All tables record strict database-generated UTC timestamps (`created_at`, `measurement_time`, `observation_timestamp`).
- [ ] **1.3 Automated POS Ingestion:** Point-of-Sale portion counts and gross sales are ingested automatically within 30 minutes of service closure.
- [ ] **1.4 Daily Campus Headcount Feed:** Morning timetable and headcount estimates are automatically pulled at $T - 4\text{ hours}$ (07:30 AM).

### Gate 2: Data Collection Pilot Completion
- [ ] **2.1 Minimum Observation Volume:** At least **40 consecutive weekday lunch services** collected for Canteen Section A.
- [ ] **2.2 Logging Compliance Rate:** Complete, audited records exist for at least **$90\%$ of scheduled services** ($\ge 36$ of 40 services).
- [ ] **2.3 Weekday Distribution:** At least **7 distinct observation days per weekday** (7 Mondays, 7 Tuesdays, 7 Wednesdays, 7 Thursdays, 7 Fridays) to support weekly seasonal indexing.
- [ ] **2.4 Menu Item Repetition:** Each primary hot entrée dish has been served and recorded a minimum of **3 times** under normal operational conditions.

### Gate 3: Ground Truth Target Quality & Independence
- [ ] **3.1 Demand Target Authenticity:** Ground truth target is strictly `Expected_Demand_Portions` derived from reconciled POS sales counts, **not** retrospective scrap estimations.
- [ ] **3.2 Waste Segregation:** Unserved kitchen surplus (`Surplus_Unserved_kg`) and student plate waste (`Plate_Waste_kg`) are measured and recorded on separate scales with distinct tare deductions.
- [ ] **3.3 Stockout Logging:** Services where dishes ran out before service close carry an explicit `stockout_occurred = TRUE` flag and recorded time of depletion.
- [ ] **3.4 Physical Plausibility:** Physical plausibility audits pass with zero un-investigated violations (e.g. unserved surplus cannot exceed gross prepared food weight).

### Gate 4: Feature Isolation & Leakage Prevention
- [ ] **4.1 Strict Prediction Horizon ($T - 4\text{ hours}$):** Feature generation pipeline enforces that every feature input carries a timestamp strictly prior to $T - 4\text{ hours}$.
- [ ] **4.2 Prohibited Features Gate:** Automated regression tests confirm that `Portions_Prepared`, `Portions_Served`, `Surplus_Unserved_kg`, and `Plate_Waste_kg` are inaccessible to the pre-service prediction pipeline.
- [ ] **4.3 Rolling Window Realism:** Rolling demand features access only finalized historical services from previous days ($\text{Date} < \text{pred\_date}$).

### Gate 5: Holdout Integrity & Baseline Setup
- [ ] **5.1 Pristine Final Holdout:** The final **10 consecutive days of the pilot** are reserved strictly as an untouched holdout and sealed from all early exploratory analysis and hyperparameter tuning.
- [ ] **5.2 Disqualification of Historical Holdout:** The historical August 4–10, 2025 holdout is permanently marked as contaminated and excluded from pilot evaluation.
- [ ] **5.3 Non-Trainable Baselines Established:**
  - Same-weekday median demand baseline implemented.
  - 3-week rolling average demand baseline implemented.
  - Kitchen head-chef heuristic baseline implemented.
- [ ] **5.4 Model Adoption Criterion:** Candidate ML models are eligible for consideration only if they demonstrate statistically and operationally significant reduction in overproduction and stockout costs over the same-weekday median baseline on development folds.

### Gate 6: Production & Application Safety
- [ ] **6.1 Live Production Untouched:** Active production SQLite database (`database.db`), models (`waste_regression_model.pkl`), API contracts, and React frontend remain completely unchanged.
- [ ] **6.2 Isolated Pilot Environment:** Pilot data ingestion operates on dedicated endpoints and staging tables with zero runtime dependency on the legacy production prediction path.

---

## 3. Go / No-Go Decision Framework

| Checklist Status | Operational Decision | Next Action |
| :--- | :---: | :--- |
| **All Gates 1.1 through 6.2 Checked** | **GO** | Formally approve Phase 7: Train and validate demand forecasting models on clean pilot records. |
| **Any Gate 1–4 Failed** | **NO-GO** | Continue pilot data collection and resolve instrumentation/compliance blockers. |
| **Gate 5.1 or 5.2 Compromised** | **NO-GO** | Discard compromised test partition; collect an additional 2 weeks of fresh chronological holdout data. |
