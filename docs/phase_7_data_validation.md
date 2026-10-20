# Phase 7: Data Validation, Error Handling, and Audit Rules

## 1. Overview

This document specifies the validation engine, data integrity invariants, POS file verification rules, and audit logging behavior implemented in the Phase 7 operational data capture prototype.

---

## 2. Quantitative Validation Invariants

All data-entry endpoints and import routines enforce strict mathematical and business invariants:

### Non-Negativity Rules
- **Quantities & Counts**: Headcount, planned portions, batch portions prepared, and portions served must satisfy:
  $$\text{Count} \in \mathbb{Z}_{\ge 0}$$
- **Weights**: Prepared weight, unserved surplus weight, and plate waste weight must satisfy:
  $$\text{Weight (kg)} \in \mathbb{R}_{\ge 0.0}$$
- **Financial Quantities**: Gross sales amounts must satisfy:
  $$\text{Sales} \in \mathbb{R}_{\ge 0.0}$$
- **Prices & Portion Sizes**: Recipe portion sizes must be strictly positive:
  $$\text{standard\_portion\_grams} \in \mathbb{R}_{> 0.0}$$

Negative values are rejected immediately with HTTP 422 Unprocessable Entity (API schemas) or row-level error reporting (POS CSV parser).

### Allowed Enumerations
- **Meal Periods**: `Breakfast`, `Lunch`, `Dinner`.
- **Canteen Sections**: `A`, `B`, `C`, `D`. (Pilot scope restricted to `A`).
- **Food Categories**: `Meat`, `Rice`, `Soup`, `Vegetables`.
- **Service Statuses**: `Planned`, `In_Prep`, `Serving`, `Closed`, `Audited`.
- **Observation Sources**: `Timetable`, `Wifi_Count`, `Preorder`, `Historical_Average`, `Kitchen_Estimate`.
- **Disposal Destinations**: `Compost`, `Donation`, `Anaerobic_Digestion`, `Landfill`.

---

## 3. Mass-Balance Invariant Policy

### Why Exact Mass Balance is NOT Artificially Enforced
In physical catering environments, the theoretical equation:
$$\text{Weight}_{\text{prepared}} = \text{Weight}_{\text{served}} + \text{Weight}_{\text{surplus}} + \text{Weight}_{\text{plate\_waste}}$$
rarely holds exactly due to:
1. **Evaporative Cooking Loss**: Moisture loss during hot-holding over a 2-hour lunch service ($5\text{--}15\%$).
2. **Serving Variance**: Diner self-service, ladle variance, or double scoops.
3. **Tray Scrape Incompleteness**: Liquid absorption by napkins or food retained on plates/cutlery.
4. **Bone & Inedible Discard**: Weight differences between raw ingredients, cooked servings, and customer discard.

**System Rule**: The validation engine **does not reject records** for minor deviations between prepared weight and the sum of served plus waste weights. Instead, severe discrepancies (e.g. surplus waste exceeding total prepared weight by $> 25\%$) generate a **soft audit warning** (`validation_warnings` in the service details payload) for supervisory review without discarding authentic measurements.

---

## 4. POS CSV Import Engine Specification

The end-of-day register import endpoint (`POST /api/pilot/pos/import`) processes transaction files from physical canteen POS registers.

### Mandatory File Headers
The CSV file must contain the following case-sensitive headers (accepting either `dish_name` or `item_name`):

```csv
service_date,meal_period,canteen_section,dish_name,portions_served,gross_sales_amount,stockout_occurred
```

### Validation Rules
1. **Header Validation**: Missing mandatory columns abort the entire import batch with an actionable error listing missing headers.
2. **Date Format**: Must parse to valid ISO format `YYYY-MM-DD`. Invalid dates (e.g., `2026-13-45`) fail the row.
3. **Non-Negativity**: Negative portion counts or sales figures produce row-specific errors identifying the line number.
4. **Recipe Verification**: The imported dish name must exist in `menu_items`. If uncataloged, the row is rejected with advice to register the recipe first.
5. **Idempotency & Duplicate Protection**:
   - Each valid row generates an SHA-256 fingerprint:
     $$\text{hash}(\text{service\_id} + \text{item\_id} + \text{portions\_served} + \text{sales})$$
   - Duplicate submissions within the same service and item are skipped safely without error, returning an explicit count of `skipped_count`.

### Error Response Format
When POS file processing encounters errors, it returns HTTP 200 with `success: false` and a structured report:

```json
{
  "success": false,
  "imported_count": 0,
  "skipped_count": 0,
  "errors": [
    "Row 3: portions_served must be non-negative (received -15)"
  ],
  "warnings": [],
  "batch_timestamp": "2026-10-20T11:15:30.123456Z"
}
```

---

## 5. Audit Logging & Revision Preservation

All state modifications are captured in `pilot_audit_logs`:

| Column | Type | Description |
| :--- | :--- | :--- |
| `log_id` | TEXT PK | UUID string |
| `entity_type` | TEXT | `Meal_Service`, `Production_Record`, `Service_Record`, `Waste_Record`, `POS_Import` |
| `entity_id` | TEXT | Primary key of the affected entity |
| `action` | TEXT | `CREATE`, `UPDATE`, `STATUS_CHANGE`, `POS_IMPORT` |
| `old_value_json` | TEXT | JSON snapshot of previous values before change |
| `new_value_json` | TEXT | JSON snapshot of new values after change |
| `performed_by` | TEXT | Staff ID or API client identifier |
| `timestamp` | TEXT | UTC timestamp of the modification event |

### Revision Preservation Policy
Previously recorded measurements are never silently overwritten or deleted:
1. When a revised measurement is submitted, the previous record's `is_superseded` column is set to `1`.
2. The new record is inserted with `is_superseded = 0` and points to the superseding timestamp.
3. Both the original measurement and the revision remain permanently queryable for audit integrity.
