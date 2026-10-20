# Phase 7: Staff Operational Data Entry Guide

## 1. Introduction & Objectives

This guide instructs canteen personnel on collecting trustworthy operational data during the Section A Lunch Pilot. 

Accurate, genuine data collection is necessary to build real-world demand forecasting models. Canteen staff must record what actually happens in the kitchen and dining hall without rounding, guessing, or forcing numbers to match an artificial equation.

---

## 2. Staff Roles & Responsibilities

| Role | Primary Responsibilities | Data Collection Step |
| :--- | :--- | :--- |
| **Kitchen Lead / Manager** | Schedules meal services, logs pre-service expected headcount at $T - 4\text{h}$, schedules menu dishes, advances service lifecycle status. | Steps 1 & 5 |
| **Head Cook / Line Cooks** | Logs cooked batch quantities, portion counts, and weighed cooked weights (kg) as pans leave the line. | Step 2 |
| **POS Cashier / Counter Lead** | Verifies POS register reconciliation, records dispensed portion counts, and flags early stockouts. | Step 3 |
| **Steward / Waste Operator** | Independently weighs unserved kitchen surplus pans and customer dining tray plate waste on calibrated kitchen scales. | Step 4 |

---

## 3. Service Timeline & Chronological Workflow

```
[ T - 24h to T - 4h ]  STEP 1: Pre-Service Setup
                        • Schedule meal service
                        • Confirm scheduled dishes
                        • Record expected headcount estimate

[ T - 2h to T - 0h ]   STEP 2: Kitchen Batch Production
                        • Cook line batches
                        • Record batch portions & cooked weight (kg)

[ T + 0h to T + 2h ]   STEP 3: Service Dispensing & POS Reconciliation
                        • Serve portions to diners
                        • Record early stockouts immediately if a dish runs out
                        • End-of-service POS sales counts logged

[ T + 2h to T + 3h ]   STEP 4: Separated Waste Measurement
                        • Weigh unserved surplus food left in kitchen pans (kg)
                        • Weigh plate waste scraped from customer trays (kg)
                        • Record disposal stream (Compost / Donation / Landfill)

[ T + 3h ]             STEP 5: Service Audit & Closure
                        • Review completeness checklist
                        • Resolve missing field warnings
                        • Advance status to 'Closed' and 'Audited'
```

---

## 4. Step-by-Step Instructions

### Step 1: Pre-Service Setup ($T - 4\text{h}$ Cutoff)
1. Navigate to the **Pilot Data Capture** page in the SmartCanteen AI portal (`/pilot`).
2. Click **+ New Service**, select the date (YYYY-MM-DD), meal period (`Lunch`), and section (`A`).
3. Add scheduled dishes from the catalog to the service menu. Set the planned portion target.
4. In the **1. Pre-Service (T-4h)** tab, enter the **Expected Headcount** and select the source:
   - `Timetable`: Class enrollment schedules.
   - `Wifi_Count`: Campus Wi-Fi footfall sensors.
   - `Preorder`: Mobile app pre-orders.
   - `Kitchen_Estimate`: Historical kitchen judgment.
5. Enter your staff ID / name and click **Save Headcount**.

### Step 2: Kitchen Batch Production (Before & During Service)
1. Select the **2. Kitchen Prep** tab.
2. For each menu dish, record every cooked batch:
   - **Batch #**: Incremental integer ($1, 2, 3\dots$).
   - **Portions Prepared**: Count of standard portions prepared in this batch.
   - **Cooked Weight (kg)**: Weighed pan weight minus tare weight on the kitchen prep scale.
   - **Cook**: Your staff identifier.
3. Click **Log Batch**. Repeat if second or third batches are cooked during high demand.

### Step 3: Portions Served & Stockout Reporting
1. Select the **3. Portions Served** tab.
2. Enter the total portions dispensed to diners (from POS cashier register or manual tally).
3. **Early Stockout Flag**:
   - If a dish ran out before the scheduled end of service ($13{:}30$), check **Dish Stocked Out**.
   - Note the approximate stockout time. This flags truncated demand for future demand unconstraining models.
4. Click **Save Served Count**.

### Step 4: Separated Waste Measurement (Post-Service)
1. Select the **4. Waste Log** tab.
2. **Important Rule**: Unserved kitchen surplus and customer plate waste are two distinct physical streams. **Never combine them.**
   - **Unserved Kitchen Surplus (kg)**: Food remaining in serving pans, warming trays, or cold hold that was never served to a diner.
   - **Plate Waste (kg)**: Food scraped from dining hall trays returned by students and staff.
3. Place container on scale, zero/tare the scale, and record weight to two decimal places (e.g. `2.45` kg).
4. Select the disposal stream (`Compost`, `Donation`, `Anaerobic_Digestion`, `Landfill`).
5. Click **Record Waste**.

---

## 5. Handling Operational Edge Cases

### Early Stockouts
When a popular dish is depleted at $12{:}45$, kitchen staff must **not** attempt to estimate how many diners "would have" bought the dish. Simply:
1. Log the exact portions actually served up to the moment of stockout.
2. Mark `Dish Stocked Out` as `True`.
3. The future forecasting model will treat this record as right-censored demand rather than total demand.

### Over-Production / Second Batches
If a cook prepares an emergency second batch of 40 portions:
1. Do not overwrite Batch 1.
2. Record Batch 2 with its own portions and cooked weight. The system aggregates total production automatically.

### POS CSV End-of-Day Batch Ingestion
If register data is exported in bulk from the canteen POS terminal:
1. Click **Import POS CSV** in the top navigation bar.
2. Paste the export CSV or upload the text file.
3. Verify that the dialog reports zero errors. Any row with negative quantities or unknown dishes will be highlighted for correction.

---

## 6. Audit Trail & Making Corrections

If a measurement was entered erroneously (e.g., entered `120` kg instead of `12.0` kg):
- Submit the corrected value using the data entry form.
- The system automatically creates a new revision in the database, preserving the previous entry and logging who made the change in `pilot_audit_logs`.
- Do not delete previous records directly from SQLite.
