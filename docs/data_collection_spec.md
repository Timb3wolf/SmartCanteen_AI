# SmartCanteen AI — Operational Data Collection Specification (Phase 5)

> **Document Status:** Operational Data Architecture & Ingestion Specification  
> **Target Branch:** `ml/phase-5-data-readiness-audit`  
> **Prerequisite For:** Next-generation ML model development & deployment  

---

## 1. Objective & Operational Context

The Phase 5 audit proved that existing machine learning models failed to outperform a constant naive mean baseline because the repository's dataset lacks operational volume features. To predict food waste before a meal is cooked, the forecasting pipeline requires variables that govern the **conservation of food mass** in institutional kitchens:

$$\text{Total Waste} = \text{Unserved Overproduction Surplus} + \text{Customer Plate Waste}$$

This document specifies the operational data architecture, data dictionary, ingestion frequency, prediction timelines, and target redefinition required before any future machine learning modeling phase can begin.

---

## 2. Target Redefinition: Pre-Meal Forecast vs Retrospective Audit

### 2.1 The Flaw in the Retrospective Target
The current dataset's target, `Waste_Weight_kg`, represents total discarded food recorded **after** a meal has ended. It bundles two fundamentally different physical phenomena:
1. **Unserved Kitchen Overproduction (Surplus):** Food prepared in bulk that was never served to customers. This is directly controllable by kitchen batch sizing.
2. **Customer Plate Waste (Scrap):** Food served onto student plates but uneaten. This is driven by portion sizes, food palatability, and student eating behavior.

Predicting `Waste_Weight_kg` before a meal without knowing how much food is being cooked or how many people will eat is mathematically ill-posed.

### 2.2 Recommended Pre-Meal Operational Targets

For future operational systems, we define two distinct targets based on use-case:

| Target Name | Formula / Definition | Unit | Prediction Horizon | Operational Decision Enabled |
| :--- | :--- | :---: | :--- | :--- |
| **`Expected_Demand_Portions`** *(Primary Pre-Meal Target)* | Count of student meals requested/served: $N_{\text{served}}$ | Portions (Integer) | **$T - 4\text{ hours}$** (Before cooking commences) | Tells the chef exactly how many portions to cook to prevent overproduction. |
| **`Expected_Surplus_kg`** *(Secondary Risk Target)* | Food prepared minus food served: $W_{\text{prep}} - W_{\text{served}}$ | Kilograms (Float) | **$T - 1\text{ hour}$** (After final prep count) | Flags excess food for donation, flash discount, or rapid chilling before spoilage. |
| **`Retrospective_Waste_Risk`** *(Audit Categorization Only)* | Post-meal operational audit: $\text{Low} / \text{Medium} / \text{High}$ | Category (Enum) | **$T + 1\text{ hour}$** (Post-service audit) | Internal reporting on compliance; **not** an input or goal for pre-meal forecasting. |

---

## 3. Data Dictionary & Field Specifications

Fields are divided into **Mandatory (Phase 6 Prerequisite)** and **Optional (Enhancement Features)**.

### 3.1 Mandatory Operational Fields (Required Before Next Model Phase)

| Field Name | Data Type & Unit | Collection Source | Frequency | Availability at Prediction Time | Operational Definition & Intended ML Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Date`** | `DATE` (ISO YYYY-MM-DD) | System Clock | Daily | Available at all times | Primary chronological indexing key. |
| **`Meal`** | `ENUM` (`Breakfast`, `Lunch`, `Dinner`) | Production Schedule | Per Meal | Available at all times | Service period grouping. |
| **`Canteen_Section`** | `ENUM` (`A`, `B`, `C`, `D`) | Facility Registry | Static | Available at all times | Spatial kitchen/station partition. |
| **`Food_Category`** | `ENUM` (`Meat`, `Rice`, `Soup`, `Vegetables`) | Menu Master | Static | Available at all times | Coarse food taxonomy. |
| **`Dish_Name`** | `VARCHAR(64)` | Kitchen Menu Plan | Daily ($T-24\text{h}$) | Available at $T-4\text{h}$ | Specific recipe/item (e.g. "Braised Chicken", "Steamed Jasmine Rice"). |
| **`Expected_Headcount`** | `INTEGER` (Number of persons) | Campus Card / Class Registry | Daily ($T-4\text{h}$) | **Available at $T-4\text{h}$** | Estimated student footfall based on timetables, dorm occupancy, and reservations. |
| **`Portions_Prepared`** | `INTEGER` (Portion count) | Kitchen Display / Batch Log | Per Batch | **Available at $T-1\text{h}$** | Total meal portions or trays batch-cooked by the kitchen staff. |
| **`Weight_Prepared_kg`** | `DECIMAL(6,2)` (kg) | Kitchen Floor Scale | Per Batch | **Available at $T-1\text{h}$** | Total gross weight of cooked food dispatched to the serving line. |
| **`Portions_Served`** | `INTEGER` (Portion count) | POS Checkout Register | Real-time | Post-meal only | Realized meal consumption count (ground truth demand). |
| **`Surplus_Unserved_kg`** | `DECIMAL(6,2)` (kg) | Service Line Scale | Post-Meal | Post-meal only | Unserved food remaining in pans at service close (overproduction ground truth). |
| **`Customer_Plate_Waste_kg`** | `DECIMAL(6,2)` (kg) | Tray Return Smart Scale | Post-Meal | Post-meal only | Food scraped into disposal bins by diners (plate waste ground truth). |

### 3.2 Optional Operational & Contextual Fields

| Field Name | Data Type & Unit | Collection Source | Frequency | Availability at Prediction Time | Operational Definition & Intended ML Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Academic_Event_Type`** | `ENUM` (`Normal`, `Exam_Period`, `Orientation`, `Holiday`, `Recess`) | University Academic Calendar | Termly | Available at all times | Explains dramatic shifts in campus footfall and dining schedules. |
| **`Day_Of_Week`** | `INTEGER` (0=Monday, 6=Sunday) | Derived from `Date` | Per Record | Available at all times | Weekly seasonal cycle. |
| **`Is_Weekend`** | `BOOLEAN` (0 or 1) | Derived from `Date` | Per Record | Available at all times | Weekend dining pattern flag. |
| **`Carried_Over_Leftover_kg`** | `DECIMAL(6,2)` (kg) | Cold Storage Inventory Log | Per Meal ($T-4\text{h}$) | Available at $T-4\text{h}$ | Reusable pre-cooked components safely stored from prior meal. |
| **`Unit_Price_per_kg`** | `DECIMAL(6,2)` ($/kg) | Catering ERP | Weekly | Available at all times | Retail selling price per unit weight. |
| **`Ingredient_Cost_per_kg`** | `DECIMAL(6,2)` ($/kg) | Purchasing Invoice | Monthly | Available at all times | Raw ingredient procurement cost (used for true financial loss audit). |
| **`Weather_Condition`** | `ENUM` (`Sunny`, `Rainy`, `Snow`, `Extreme_Cold`, `Extreme_Heat`) | Local Weather API | Hourly | Available at $T-4\text{h}$ (Forecast) | Weather directly alters willingness of students to walk to distant canteens. |
| **`Forecast_Rain_mm`** | `DECIMAL(4,1)` (mm) | Local Weather API | Hourly | Available at $T-4\text{h}$ (Forecast) | Precipitation volume index. |

---

## 4. Evaluation of Specific Candidate Variables

### 4.1 Attendance & Expected Headcount
- **Usefulness:** **Very High (Primary Driver).** Food waste is fundamentally driven by unexpected drops in dining attendance.
- **Feasibility:** High. Can be estimated via campus Wi-Fi density logs, class timetables, library swipe gates, or meal plan pre-orders.
- **Operational Timeline:** Available at $T-4\text{ hours}$ (morning report).

### 4.2 Portions Prepared & Portions Served
- **Usefulness:** **Critical (Physical Mass Conservation).** The difference between prepared and served portions defines unserved surplus waste.
- **Feasibility:** Moderate. Requires kitchen staff to record the number of standard pans/trays dispatched, and POS cash registers to tally sales per item.
- **Operational Timeline:** `Portions_Prepared` is set at cooking time ($T-2\text{h}$); `Portions_Served` is tallied at POS close.

### 4.3 Previous-Meal and Previous-Day Leftovers
- **Usefulness:** **High.** Canteen managers adjust batch preparation downwards when substantial chilled stock remains from lunch.
- **Feasibility:** Moderate. Requires standardizing cold storage tagging.
- **Operational Timeline:** Available at $T-4\text{ hours}$ before dinner or the next day's lunch.

### 4.4 Granular Dish Name / Menu Specificity
- **Usefulness:** **High.** "Meat" is too coarse. High-cost items (e.g. roast beef) exhibit different waste dynamics than stew or sausages.
- **Feasibility:** High. Canteens operate on rotating weekly menus that are planned days in advance.
- **Operational Timeline:** Available at $T-24\text{ hours}$.

### 4.5 Weather (Rain & Temperature)
- **Usefulness:** **Moderate.** On university campuses, heavy rain significantly reduces footfall at standalone peripheral canteens while surging demand at canteens connected to student dormitories or central lecture halls.
- **Feasibility:** High. Standard free weather APIs (e.g. Open-Meteo, NOAA) provide reliable hourly precipitation and temperature forecasts.
- **Operational Timeline:** Available at $T-4\text{ hours}$ via weather forecast lookup.

---

## 5. Ingestion Pipeline & Validation Invariants

Any future operational data ingestion pipeline must enforce the following physical constraints:

1. **Mass Conservation Invariant:**
   $$\text{Weight\_Prepared\_kg} \ge \text{Surplus\_Unserved\_kg}$$
   Total unserved surplus cannot physically exceed the total food weight cooked.
2. **Portion Count Invariant:**
   $$\text{Portions\_Prepared} + \text{Carried\_Over\_Leftover\_Portions} \ge \text{Portions\_Served}$$
   Total served portions cannot exceed the sum of cooked and carried portions.
3. **Strict Time Ordering:**
   All features used for pre-meal prediction must carry a timestamp verification:
   $$\text{Timestamp}_{\text{feature}} \le \text{Scheduled\_Service\_Start} - 2\text{ hours}$$
4. **Independent Ground Truth Verification:**
   `Customer_Plate_Waste_kg` must be weighed separately from `Surplus_Unserved_kg`. They must never be aggregated into an un-differentiated total before storage.

---

## 6. Implementation Roadmap & Milestones

```
+---------------------------------------------------------------------------------+
| Phase 5 (Current): Data Readiness Audit & Specification Completed              |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| Milestone 1: Kitchen Hardware & POS Instrumentation (Weeks 1-4)                 |
| - Connect POS meal counts to daily database.                                    |
| - Deploy digital floor scales in kitchen prep and tray-return areas.            |
| - Integrate University class calendar and weather API feeds.                    |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| Milestone 2: 60-Day Pilot Ingestion & Data Quality Auditing (Weeks 5-12)        |
| - Collect minimum 60 consecutive days of operational records.                   |
| - Run automated mass-balance integrity assertions daily.                        |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| Milestone 3: Machine Learning Model Development (Phase 6)                      |
| - Train Demand-Forecasting Gradient Boosted Models (predicting Portions Needed).|
| - Chronological rolling-origin evaluation against headcount-proportional baseline.|
+---------------------------------------------------------------------------------+
```
