# SmartCanteen AI — Candidate Temporal Feature Engineering Specification (Phase 1)

> **Document Status:** Candidate Feature Specification (Pre-Model Integration)  
> **Target Branch:** `ml/phase-1-temporal-features`  
> **Module Implementation:** `backend/app/ml/features.py`  
> **Re-export Module:** `src/features.py`  
> **Verification Test Suite:** `backend/app/tests/test_temporal_features.py` (19 passing tests)  

---

## 1. Executive Summary

Phase 0 identified severe structural limitations in the initial SmartCanteen AI baseline:
- The Random Forest regressor ($R^2 = -0.128$) was worse than a zero-information mean baseline due to unconstrained tree leaves memorizing arbitrary calendar days (`Day` accounted for $25.8\%$ of regression importance and $39.5\%$ of classifier importance).
- The classifier operated at chance level ($35.38\%$ accuracy vs $33.33\%$ random guessing).
- Random 80/20 train/test splitting shuffled past and future observations, causing temporal leakage.

Phase 1 addresses the root cause of these failures by implementing a **leakage-safe, deterministic temporal feature engineering pipeline** (`backend.app.ml.features.TemporalFeaturePipeline`).

### Key Architectural Decisions:
1. **Elimination of Spurious Calendar Coordinates:** Raw linear `Day` (1–31) and constant `Year` (2025) are completely removed from the candidate schema.
2. **Periodic Weekly Dynamics:** Replaced by cyclical trigonometric encodings ($\sin/\cos$ of `DayOfWeek`) and an explicit `is_weekend` flag.
3. **True Calendar-Date Lags:** Historical waste features look backward across strictly calendar-based intervals ($t - 7\text{ days}$, rolling 7 days, rolling 14 days), excluding the current observation and all future dates.
4. **Explicit Missing Indicators:** Records with missing historical coverage (e.g. initial launch days or unserved combinations) are accompanied by boolean missing flags (`is_missing_*`), enabling decision trees to split on data availability.
5. **Strict Production Isolation:** The active production prediction service and model files in `models/` remain 100% untouched and operational, preserving all API contracts.

---

## 2. Candidate Feature Inventory

The pipeline transforms raw input records into a deterministic 26-dimensional feature vector ($X \in \mathbb{R}^{26}$):

| Index | Feature Name | Source Column(s) | Data Type | Physical Meaning & Transformation |
| :--- | :--- | :--- | :--- | :--- |
| 0 | `unit_price_per_kg` | `Unit_Price_per_kg` | `float64` | Raw unit price per kg of the food item |
| 1 | `day_of_week` | `Date` | `float64` | Day of week integer: 0 = Monday, ..., 6 = Sunday |
| 2 | `dow_sin` | `Date` | `float64` | $\sin\left(\frac{2\pi \cdot \text{DayOfWeek}}{7}\right)$ periodic day-of-week encoding |
| 3 | `dow_cos` | `Date` | `float64` | $\cos\left(\frac{2\pi \cdot \text{DayOfWeek}}{7}\right)$ periodic day-of-week encoding |
| 4 | `is_weekend` | `Date` | `float64` | Binary flag: $1.0$ if Saturday or Sunday, else $0.0$ |
| 5 | `meal_Breakfast` | `Meal` | `float64` | One-hot binary indicator for Breakfast |
| 6 | `meal_Dinner` | `Meal` | `float64` | One-hot binary indicator for Dinner |
| 7 | `meal_Lunch` | `Meal` | `float64` | One-hot binary indicator for Lunch |
| 8 | `section_A` | `Canteen_Section` | `float64` | One-hot binary indicator for Section A |
| 9 | `section_B` | `Canteen_Section` | `float64` | One-hot binary indicator for Section B |
| 10 | `section_C` | `Canteen_Section` | `float64` | One-hot binary indicator for Section C |
| 11 | `section_D` | `Canteen_Section` | `float64` | One-hot binary indicator for Section D |
| 12 | `category_Meat` | `Food_Category` | `float64` | One-hot binary indicator for Meat |
| 13 | `category_Rice` | `Food_Category` | `float64` | One-hot binary indicator for Rice |
| 14 | `category_Soup` | `Food_Category` | `float64` | One-hot binary indicator for Soup |
| 15 | `category_Vegetables` | `Food_Category` | `float64` | One-hot binary indicator for Vegetables |
| 16 | `waste_lag_7d` | `Waste_Weight_kg` | `float64` | Same grouping key waste exactly 7 calendar days prior ($D - 7\text{d}$) |
| 17 | `is_missing_lag_7d` | `Date`, `keys` | `float64` | Binary flag: $1.0$ if no service record existed on $D - 7\text{d}$, else $0.0$ |
| 18 | `waste_rolling_mean_7d` | `Waste_Weight_kg` | `float64` | Mean historical waste in preceding calendar interval $[D - 7\text{d}, D - 1\text{d}]$ |
| 19 | `waste_rolling_std_7d` | `Waste_Weight_kg` | `float64` | Sample standard deviation in preceding interval $[D - 7\text{d}, D - 1\text{d}]$ ($0.0$ if $< 2$ records) |
| 20 | `waste_rolling_count_7d` | `Date`, `keys` | `float64` | Number of observed service records in preceding interval $[D - 7\text{d}, D - 1\text{d}]$ |
| 21 | `is_missing_rolling_7d` | `Date`, `keys` | `float64` | Binary flag: $1.0$ if zero records existed in $[D - 7\text{d}, D - 1\text{d}]$, else $0.0$ |
| 22 | `waste_rolling_mean_14d` | `Waste_Weight_kg` | `float64` | Mean historical waste in preceding calendar interval $[D - 14\text{d}, D - 1\text{d}]$ |
| 23 | `waste_rolling_std_14d` | `Waste_Weight_kg` | `float64` | Sample standard deviation in preceding interval $[D - 14\text{d}, D - 1\text{d}]$ ($0.0$ if $< 2$ records) |
| 24 | `waste_rolling_count_14d` | `Date`, `keys` | `float64` | Number of observed service records in preceding interval $[D - 14\text{d}, D - 1\text{d}]$ |
| 25 | `is_missing_rolling_14d` | `Date`, `keys` | `float64` | Binary flag: $1.0$ if zero records existed in $[D - 14\text{d}, D - 1\text{d}]$, else $0.0$ |

---

## 3. Grouping Keys & Calendar Window Semantics

### Grouping Key Definition
Historical aggregations are computed on the multi-dimensional service event key:
$$\text{Group Key} = (\text{Canteen\_Section}, \text{Meal}, \text{Food\_Category})$$

- In `SmartCanteen_Final_Dataset.csv`, there are 4 sections $\times$ 3 meals $\times$ 4 categories = **48 unique combinations**.
- Each combination appears on average $54.2$ times across the 61 calendar days.
- **Uniqueness Guarantee:** Any single combination appears at most **once** per calendar date ($Date, Section, Meal, Category$ is an exact unique key).

### Explicit Calendar vs Row-Based Rolling Windows
A common data science error is calling `rolling(7)` a 7-day rolling window on row-sorted data. In university canteens where certain items are not served every day:
- Seven rows could span 10, 14, or 21 calendar days.
- `TemporalFeaturePipeline` enforces **explicit calendar-time semantics** using pandas `rolling('7D', closed='left')` and `rolling('14D', closed='left')`.

```
Timeline:
[ D - 14d ........... D - 7d ........... D - 1d ]  |  [ Date D (Current Observation) ]  |  [ D + 1d (Future) ]
|<--- rolling_14d --->|                            |                                    |
                      |<--- rolling_7d --------->| |                                    |
                      ^                            |                                    |
                      |-- lag_7d (Exact Point)     |                                    |
                                                   |-- STRICT EXCLUSION ZONE ---------->|
```

- **`closed='left'` Guarantee:** The rolling window evaluation strictly includes timestamps in $[t - \text{window}, t)$. The current observation at timestamp $t$ is strictly excluded.

---

## 4. Missing History and Imputation Handling

### Fallback Policy
When an observation has insufficient or missing preceding history:
1. **Lag 7d Missing:** If key $K$ was not served on date $D - 7\text{ days}$ (e.g., during the first week of data collection, or after a menu hiatus):
   - `waste_lag_7d` is imputed using the training partition prior mean ($\bar{y}_{\text{train}} \approx 2.585\text{ kg}$).
   - `is_missing_lag_7d` is set to $1.0$.
2. **Rolling Window Missing:** If zero historical records exist for key $K$ in $[D - 7\text{d}, D - 1\text{d}]$:
   - `waste_rolling_mean_7d` is imputed with $\bar{y}_{\text{train}}$.
   - `waste_rolling_std_7d` is set to $0.0$.
   - `waste_rolling_count_7d` is set to $0.0$.
   - `is_missing_rolling_7d` is set to $1.0$.

### Non-Leakage Rule for Imputation
- Under no circumstances is a missing historical feature filled using the current observation's target or any future observation's target.
- Imputation parameters are learned strictly during `pipeline.fit(train_df)` on training data only. Test set targets never influence fallback values.

---

## 5. Future-Date Inference Mechanism

In production, predictions are requested for tomorrow or next week ($D_{\text{pred}} > D_{\text{latest}}$).

### Inference Workflow
1. The client sends a prediction request for a future date (e.g. `2025-08-11`, `Dinner`, `Section B`, `Rice`, `Unit Price: $4.50`).
2. The pipeline queries the stored historical ledger:
   $$\text{History}_{\text{valid}} = \{ r \in \text{Ledger} \mid r.\text{Date} < D_{\text{pred}} \land r.\text{Key} = (B, \text{Dinner}, \text{Rice}) \}$$
3. **Lag 7d:** Searches for $r \in \text{History}_{\text{valid}}$ where $r.\text{Date} = 2025-08-04$. If found, uses its actual waste.
4. **Rolling 7d:** Filters to $r.\text{Date} \in [2025-08-04, 2025-08-10]$. Computes mean, std, and count over those historical days.
5. **Rolling 14d:** Filters to $r.\text{Date} \in [2025-07-28, 2025-08-10]$. Computes 14-day rolling statistics.
6. **Calendar & Categoricals:** Evaluates $\sin/\cos(\text{dow})$ and binary flags for `2025-08-11`.

---

## 6. Leakage Prevention Architecture & Formal Tests

The test suite in [test_temporal_features.py](file:///c:/Users/laksh/Downloads/SmartCanteen_AI_Project/SmartCanteen_AI/backend/app/tests/test_temporal_features.py) provides programmatic verification of non-leakage:

```
Test Matrix:
├── Date Parsing:
│   ├── Valid ISO string, datetime.date, pd.Timestamp parse to midnight Timestamp
│   └── Invalid calendar dates ('2025-02-30', 'invalid-date', None, NaN) raise ValueError
├── Trigonometric Periodic Encoding:
│   ├── Monday (0) -> sin=0.0, cos=1.0, is_weekend=0.0
│   ├── Friday (4) -> is_weekend=0.0; Saturday (5), Sunday (6) -> is_weekend=1.0
│   └── sin^2 + cos^2 == 1.0 identity holds for all days
├── Hand-Checkable Toy Fixture:
│   ├── Day 1: count=0, is_missing=1.0, mean=fallback
│   ├── Day 2: count=1, is_missing=0.0, mean=Day 1 value exactly (Day 2 excluded)
│   ├── Day 8: count=7, mean=mean(Days 1..7) (Day 8 excluded)
│   └── Day 8: lag_7d == Day 1 value exactly
├── Invariance Proofs:
│   ├── test_no_own_target_leakage: Mutating current row's waste does not change its features
│   └── test_no_future_target_leakage: Mutating future row's waste does not change earlier features
└── Robustness:
    ├── Unseen categories (e.g. 'MidnightBuffet') zero out gracefully without IndexError
    ├── Duplicate keys on same date are aggregated to prevent cartesian merge expansion
    └── Training batch and single inference schemas are 100% column-name and dtype identical
```

---

## 7. Missing Operational Variables & Data Collection Opportunities

The SmartCanteen dataset records waste after service has concluded, but lacks the primary physical drivers of catering food waste:

1. **Student / Staff Footfall (Swipes / Attendance):**
   - *Impact:* The dominant driver of canteen demand.
   - *Action:* Install card-swipe counter logs at turnstiles.
2. **Prepared Quantity (kg / portions cooked):**
   - *Impact:* Waste cannot be normalized without knowing total production volume. A waste of 4 kg represents 40% waste on a 10 kg batch, but only 2% waste on a 200 kg batch.
   - *Action:* Log kitchen production batch weights.
3. **Consumer Sales / Portions Served:**
   - *Impact:* $\text{Waste} = \text{Prepared} - \text{Consumed}$.
   - *Action:* Integrate POS register receipt item counts.
4. **Academic Calendar Events:**
   - *Impact:* Exam weeks, campus festivals, reading days, and semester breaks drastically alter dining patterns.
   - *Action:* Integrate campus academic registrar calendar.
5. **Weather & Ambient Temperature:**
   - *Impact:* Heavy rain or high heat causes students to patronize closer kiosks or order delivery.
   - *Action:* Integrate local NOAA/OpenWeather historical and forecast API.

> [!IMPORTANT]
> The Phase 1 pipeline **strictly refrains from fabricating synthetic operational columns** (e.g. mock attendance numbers). Metrics will reflect genuine data constraints rather than simulated performance.

---

## 8. Limitations of the 61-Day Observation Window

1. **Short Observation Duration:** Spans only June 11, 2025 to August 10, 2025.
2. **No Annual Seasonality:** 61 days cannot represent seasonal climate or annual semester shifts.
3. **Summer Session Context:** June–August is frequently a summer term in university environments, meaning student volumes may differ from standard fall/spring semesters.
4. **Initial Warm-up Window:** The first 7 to 14 days of the dataset naturally rely on fallback means until sufficient rolling history is accumulated.

---

## 9. Separation from Production Feature Schema

To maintain complete backward compatibility and system safety, candidate features are completely isolated from the active production model:

| Dimension | Active Production Pipeline (Phase 0) | Candidate Temporal Pipeline (Phase 1) |
| :--- | :--- | :--- |
| **Model Files** | `models/waste_regression_model.pkl`<br/>`models/waste_risk_classifier.pkl` | *None (models will be trained in Phase 2)* |
| **Feature Schema File** | `models/regression_features.pkl` (13 features) | Code-defined in `TemporalFeaturePipeline` (26 features) |
| **Calendar Representation** | Raw `Day` (1-31), `Month` (6-8), constant `Year` (2025) | Cyclic `dow_sin`, `dow_cos`, `day_of_week`, `is_weekend` |
| **Historical Lags** | None | Calendar `waste_lag_7d`, rolling 7d & 14d mean/std/count |
| **Missing History Flags** | None | Explicit boolean flags: `is_missing_*` |
| **Active In API** | **YES** (`POST /api/predict`) | **NO** (Candidate module for Phase 2 training) |

---

## 10. Proposed Next Steps for Phase 2

1. **Instituting Rolling-Origin Cross-Validation:**
   - Evaluate models using 4-fold expanding window cross-validation across the 61 days (never random train/test splits).
2. **Regularized Gradient Boosted Decision Trees:**
   - Train XGBoost (`XGBRegressor`) and LightGBM with depth constraints ($3 \le \text{max\_depth} \le 5$) and L1/L2 penalties (`reg_alpha`, `reg_lambda`) on the 26 candidate features.
3. **Ablation Studies:**
   - Measure feature importance and compute performance delta with vs. without historical rolling features.
4. **Unified Risk Mapping:**
   - Map calibrated regression waste predictions directly to audited risk categories ($\le 1.78\text{ kg}$ = Low, $\le 3.42\text{ kg}$ = Medium, $> 3.42\text{ kg}$ = High).
5. **Candidate Model Promotion Gate:**
   - A candidate model may only replace production artifacts if it demonstrably beats the naive historical baseline out-of-time ($\text{MAE} < 1.25\text{ kg}, R^2 > 0.00$).
