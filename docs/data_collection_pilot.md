# SmartCanteen AI — Data Collection Pilot Design (Phase 6)

> **Document Status:** Operational Pilot Specification & Field Execution Plan  
> **Target Branch:** `ml/phase-6-operational-data-pipeline`  
> **Pilot Scope:** Single Canteen Section, Single Meal Period (Recommended: **Canteen Section A, Lunch Service**)  
> **Operational Status:** Proposed execution guidelines. All timelines, roles, and hardware requirements are recommendations for engineering and kitchen leadership, not existing operational facts.

---

## 1. Pilot Scope & Strategic Rationale

Attempting to instrument an entire campus dining complex (multiple canteens, all meals) simultaneously introduces unmanageable workflow friction, staff training resistance, and erratic data quality.

We recommend a focused **single-service operational pilot**:
- **Target Location:** **Canteen Section A** (Hot Entrée / Main Dining Line).
- **Target Meal Period:** **Lunch Service** (11:30 AM – 13:30 PM).
- **Strategic Rationale:**
  - Lunch exhibits the highest traffic volume and greatest financial variance.
  - Section A handles core batch-cooked dishes (Rice, Chicken, Beef, Steamed Vegetables) where overproduction represents the largest cost loss.
  - Staff shifts are fully staffed during lunch, ensuring dedicated personnel for logging.

---

## 2. Minimal Required Fields per Service

For each lunch service in Section A, the pilot must collect these mandatory fields:

```
+-----------------------------------------------------------------------------------------+
| PRE-SERVICE (07:30 - 10:30)                                                            |
| 1. Date (YYYY-MM-DD)                                                                    |
| 2. Meal Period ("Lunch")                                                                |
| 3. Section ("Section_A")                                                                |
| 4. Dish_Name (e.g. "Braised Chicken with Potatoes")                                     |
| 5. Expected_Headcount (Campus Wi-Fi / timetable estimate)                               |
| 6. Portions_Prepared (Batch 1 portion count logged by kitchen)                          |
| 7. Prepared_Weight_kg (Scale reading of cooked food dispatched to service line)          |
+-----------------------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------------------+
| DURING & POST-SERVICE (11:30 - 14:00)                                                   |
| 8. Portions_Served (POS cash register sales count per dish)                             |
| 9. Stockout_Occurred (Boolean: Did dish run out before 13:30?)                          |
| 10. Unserved_Surplus_kg (Scale reading of remaining unserved food in steam pans)        |
| 11. Plate_Waste_kg (Scale reading of uneaten food scraped into dish return hopper)      |
+-----------------------------------------------------------------------------------------+
```

---

## 3. Staff Workflow, Roles & Timing

To ensure compliance, logging is embedded directly into natural kitchen transition points:

| Role | Step / Timing | Action & Tool | Data Field Captured |
| :--- | :--- | :--- | :--- |
| **Kitchen Lead / Shift Manager** | **07:30 AM (T - 4h)** | Review morning campus headcount estimate and rotating menu schedule via kitchen tablet. | `Expected_Headcount`, `Dish_Name`, `Planned_Portions`. |
| **Hot Line Cook** | **10:45 AM (T - 45m)** | Weigh batch 1 steam pans on kitchen floor scale before wheeling to front service counter. | `Portions_Prepared`, `Prepared_Weight_kg`. |
| **Hot Line Cook** | **12:30 PM (Mid-Service)** | *If replenishment cooked:* Log Batch 2 count. | Additional `Portions_Prepared`. |
| **Cashier / POS System** | **13:30 PM (Service Close)** | Automated POS report export of total items dispensed. | `Portions_Served`, `Gross_Revenue`. |
| **Kitchen Steward** | **13:45 PM (Post-Service)** | Bring unserved hot pans to kitchen digital bench scale; log tare-subtracted weight. | `Unserved_Surplus_kg`. |
| **Dishwashing Attendant** | **14:00 PM (Clean-up)** | Weigh dedicated organic food waste bin from tray-return station. | `Plate_Waste_kg`. |
| **Kitchen Supervisor** | **14:15 PM (Sign-off)** | Review daily tablet dashboard, confirm all values entered, click **"Finalize Service"**. | Status set to `Audited`. |

---

## 4. Hardware & Tool Requirements

The pilot relies on simple, durable, low-cost equipment:

1. **Rugged Kitchen Tablet (1 unit):** Mounted in kitchen prep area with a simple web form (large touch-friendly numeric buttons) connected to the backend API.
2. **Heavy-Duty Digital Platform Scale (1 unit, $0.05\text{ kg}$ resolution):** Placed at the kitchen dispatch door for weighing full gastronorm pans.
3. **Dish Return Bench Scale (1 unit):** Located at the dishwashing station under the scrap hopper.
4. **POS Daily Automated Export:** Configured to push itemized sales counts for Section A to the operational database at 13:35 PM daily.

---

## 5. Handling Missing Data, Delays & Corrections

1. **Missing Pre-Service Log:** If a cook forgets to weigh pans before service, the supervisor marks `Prepared_Weight_kg = NULL` and records `Measurement_Status = 'Missed_Prep_Weight'`. **Never fabricate or back-calculate missing values.**
2. **Delayed POS Sync:** If POS connectivity drops, the transaction total is queued locally and ingested upon network reconnection, carrying the true POS closure timestamp.
3. **Measurement Corrections:** If a staff member enters $45\text{ kg}$ instead of $4.5\text{ kg}$, the supervisor submits an adjustment via the tablet. The system creates a new revision record linked by `supersedes_id` and records the editor's staff ID and timestamp.
4. **Distinguishing Zeros from Missing:** Zero surplus (clean pans) is entered as `0.00 kg`. Unmeasured surplus is recorded as `NULL` with reason `"Scale Unavailable"`.

---

## 6. Proposed Pilot Duration & Statistical Rationale

### Recommended Duration: **8 Weeks (40 Consecutive Weekday Lunch Services)**

#### Statistical & Operational Rationale:
1. **Weekday Cycle Coverage:** 8 weeks provides exactly 8 repeated observations for each weekday (8 Mondays, 8 Tuesdays, 8 Wednesdays, 8 Thursdays, 8 Fridays). This is the minimum necessary to estimate weekday seasonal effects ($N \ge 8$ per day-of-week bin).
2. **Rotating Menu Cycles:** Campus canteens typically operate on 2-week or 4-week rotating menu cycles. An 8-week pilot guarantees each specific dish recipe is prepared at least 2 to 4 times, providing repeated trials across distinct menu items.
3. **Weather Variation:** Spanning 2 calendar months ensures natural exposure to variable weather (rainy days vs fair days), allowing verification of weather forecast features.
4. **Staff Habituation:** Weeks 1–2 typically suffer from missing entries and calibration errors. Weeks 3–8 provide clean, stabilized operational data.

---

## 7. Pilot Success Metrics

The pilot is deemed operational and ready for Phase 7 ML modeling only when:
- **Logging Compliance Rate $\ge 92\%$:** At least 37 of 40 lunch services have complete, non-null records for headcount, prep, served, and surplus.
- **POS Reconciliation Rate $\ge 98\%$:** Sales records match kitchen dish offerings on all active days.
- **Physical Plausibility Violations $\le 2\%$:** Instances where $\text{Surplus} > \text{Prepared}$ or mass balance anomalies occur must be investigated and resolved under $2\%$.
- **Staff Overhead $\le 10\text{ minutes/day}$:** Total daily time spent logging across all staff must average under 10 minutes.
