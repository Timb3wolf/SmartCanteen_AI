# SmartCanteen AI — Target Validity and Data Readiness Audit (Phase 5)

> **Document Status:** Comprehensive Diagnostic Audit & Data Readiness Assessment  
> **Target Branch:** `ml/phase-5-data-readiness-audit`  
> **Base Commit:** `1b38571` (Phase 4 ensemble feasibility)  
> **Verification Suite:** `backend/app/tests/test_data_readiness.py` (8 passing tests; 127 total backend tests passing)  

---

## 1. Executive Summary

Phases 0 through 4 established that neither machine learning regression models (Random Forest, regularized XGBoost) nor ensemble methods (linear blending, baseline shrinkage, chronological stacking) could reliably outperform a zero-information naive training-fold mean baseline ($1.2428\text{ kg}$) on out-of-time chronological evaluations.

In **Phase 5**, we executed a thorough audit of the evaluation pipeline, data lineage, target definitions, and model evidence. Rather than attempting another round of model building, this phase investigates **why** the models failed to learn and whether the dataset is capable of supporting pre-meal operational forecasting.

### Key Audit Findings:
1. **Target Derivation & Discretization Artifact:**
   - `Waste_Weight_kg` is the sole authentic target column in the raw dataset. `Waste_Quantity_kg` was an informal naming discrepancy in prompt instructions and temporary scripts; it does not exist in the dataset or production schemas.
   - `Cost_Loss` is an exact algebraic product: $\text{Cost\_Loss} = \text{Waste\_Weight\_kg} \times \text{Unit\_Price\_per_kg}$ ($\max|\Delta| \le 0.0051$ due strictly to 2-decimal currency rounding). It is a downstream financial metric, not an independent target.
   - `Waste_Risk` is **100% synthetically derived from the empirical tertiles of `Waste_Weight_kg`** ($\text{Low} \le 1.78\text{ kg}$, $\text{Medium } 1.79\text{--}3.42\text{ kg}$, $\text{High} \ge 3.43\text{ kg}$). The 35.4% classifier accuracy observed in production is mathematically consistent with random guessing across 3 balanced noise bins ($1/3 \approx 33.3\%$). There is zero independent risk labeling.
2. **Evaluation Pipeline Safeguards & Prediction Timelines:**
   - Data transformations and learned fallback parameters in `TemporalFeaturePipeline` are fitted strictly on training partitions. No `fit_transform` was ever executed across the full dataset prior to chronological splitting.
   - Same-day targets and future observations are strictly excluded from feature generation ($\text{Date} < \text{pred\_date}$ and `closed='left'`).
   - Test-window records were included in historical lookups (`history_pool`) during Phases 3 and 4. In a **daily next-day forecasting timeline**, this represents legitimate retrospective ground truth (yesterday's recorded waste is available before today's kitchen opens). In a **weekly block-horizon timeline**, it represents lookahead information. An empirical re-evaluation strictly excluding test records from history produced an aggregate MAE of $1.2445\text{ kg}$ for Random Forest and $1.2443\text{ kg}$ for XGBoost—both still underperforming the Dummy Mean ($1.2428\text{ kg}$). Thus, this timeline nuance does not alter the fundamental benchmark conclusions.
3. **Absence of Operational Forecasting Signals:**
   - The dataset contains static categorical descriptors (`Meal`, `Canteen_Section`, `Food_Category`), item price, and calendar timestamps across 61 consecutive days.
   - The dataset completely lacks **operational demand and volume covariates**: no headcount/attendance counts, no meal portions cooked, no portions served, and no leftover inventory carryovers.
   - Under these features, conditional target variance is essentially identical to marginal target variance. Models cannot learn predictive patterns that do not exist in the data.
4. **Final Decision:**
   - The current dataset is **NOT ready** for defensible pre-meal forecasting.
   - Production models, API contracts, SQLite databases, and frontend interfaces remain untouched.
   - Future ML work must be gated on instrumenting operational volume features as defined in `docs/data_collection_spec.md`.

---

## 2. Comprehensive Pipeline Audit

We audited the core modules implemented across Phases 1 through 4:
- `backend/app/ml/features.py` (Feature engineering pipeline)
- `backend/app/ml/evaluation.py` (Rolling origin chronological splitter & metrics)
- `backend/app/ml/benchmark.py` (Model benchmarking orchestration)
- `backend/app/ml/ensemble.py` (Ensemble feasibility runner)

### Investigation of Seven Specific Pipeline Questions:

#### Q1: Are feature encoders, imputers, scalers, and learned transformations fitted strictly on the appropriate training partition?
- **Finding:** **YES. Safely isolated.**
- **Evidence:** In `TemporalFeaturePipeline.fit(train_df)`:
  - Categorical encoders use fixed, deterministic vocabularies configured in `TemporalFeatureConfig` (`known_meals`, `known_sections`, `known_categories`). No data-dependent vocabulary learning or target encoding occurs.
  - The fallback imputation mean (`self._learned_fallback_mean`) is calculated strictly from `clean_train[self.config.target_column].mean()`.
  - The historical record lookup index (`self._history_records`) is populated strictly from `clean_train`.
  - No continuous feature scalers are fitted across splits.

#### Q2: Does any `fit_transform` operation process the complete dataset before chronological splitting?
- **Finding:** **NO. Strictly avoided.**
- **Evidence:** In `ModelBenchmarkRunner.run_development_benchmark()` and `EnsembleExperimentRunner.run_development_ensembles()`:
  - Splitting occurs first: `folds = self.splitter.split(df)`.
  - Inside each fold loop, `train_df = df.iloc[fold.train_indices].copy()` is isolated before `pipe.fit(train_df)` is instantiated.
  - The feature pipeline is never fitted on the full dataframe prior to splitting.

#### Q3: Do test-window records enter historical feature lookups?
- **Finding:** **YES, with clear timeline implications.**
- **Evidence & Operational Distinction:**
  In `benchmark.py` and `ensemble.py`:
  ```python
  history_pool = pd.concat([train_df, test_df], ignore_index=True)
  X_test = pipe.transform(test_df, is_training=False, historical_records=history_pool)
  ```
  - **Mechanics:** For an observation on date $D$ within the 7-day test window, lookups filter `prior_records = grp[grp["parsed_date"] < pred_date]`.
    - On Day 1 of the test window: Lookups access records where $\text{Date} < \text{Day 1}$, which resides 100% in `train_df`.
    - On Day 2: Lookups access records where $\text{Date} < \text{Day 2}$, which includes Day 1 of `test_df`.
    - On Day 7: Lookups access records from Days 1 through 6 of `test_df`.
  - **Timeline Context:**
    - *Daily Rolling Forecasting (Legitimate):* If the operational workflow runs daily at 06:00 AM to predict today's lunch, yesterday's realized dinner waste was weighed and logged yesterday evening. In this operational setting, Day 1 realized waste is genuine historical information when predicting Day 2.
    - *Block Weekly Forecasting (Leakage):* If the operational workflow runs on Sunday night to forecast the entire upcoming week (Monday through Sunday) in a single batch, Monday's realized waste has not occurred yet when predicting Tuesday through Sunday.
  - **Empirical Sensitivity Test:**
    We executed a controlled experiment on all 4 development folds comparing `history_pool` (test records included) against `train_only` (test records strictly excluded):
    - Candidate RF MAE: $1.2491\text{ kg}$ (pool) vs **$1.2445\text{ kg}$ (train_only)**.
    - XGBoost MAE: $1.2495\text{ kg}$ (pool) vs **$1.2443\text{ kg}$ (train_only)**.
    - Dummy Mean Baseline MAE: **$1.2428\text{ kg}$**.
    Even when test-window records are completely excluded from history, neither model beats the training-fold Dummy Mean. The finding that machine learning models fail to outperform the naive mean is completely invariant to this distinction.

#### Q4: Can same-day records or future target values influence a prediction?
- **Finding:** **NO. Strictly prevented.**
- **Evidence:**
  - In `transform_inference`: `prior_records = grp[grp["parsed_date"] < pred_date]`. The strict inequality `<` guarantees that same-day records ($\text{Date} = \text{pred\_date}$) and future records ($\text{Date} > \text{pred\_date}$) are excluded.
  - In `transform_training_batch`: Rolling window calculations use `closed="left"`, which defines the interval as $[\text{Date} - W, \text{Date})$, strictly excluding the current date. Verified by test `test_inference_transform_strictly_excludes_same_day_and_future_targets`.

#### Q5: Do lag and rolling features reflect only information available at intended prediction time?
- **Finding:** **YES, under a next-day operational schedule.**
- **Evidence:**
  - `waste_lag_7d` joins records exactly at $\text{pred\_date} - 7\text{ days}$.
  - `waste_rolling_mean_7d` aggregates $[\text{pred\_date} - 7\text{d}, \text{pred\_date} - 1\text{d}]$.
  - Both strictly reference past days.

#### Q6: Has the holdout influenced model selection, hyperparameter choices, feature selection, or repeated experimentation?
- **Finding:** **NO. Selection isolation was maintained.**
- **Evidence:**
  - In Phase 3, Candidate RF was chosen based on development folds, and holdout was evaluated once post-selection.
  - In Phase 4, the Model Selection Gate evaluated Gate 1 on development fold metrics. Because all ensemble candidates failed to beat the baseline on development folds, the **NO-GO** decision was locked prior to evaluating the holdout.
  - The holdout was never used for gradient descent, hyperparameter sweeps, or weight tuning.

#### Q7: Are development metrics and holdout metrics calculated with comparable target definitions and evaluation procedures?
- **Finding:** **YES. 100% comparable.**
- **Evidence:** Both evaluate `Waste_Weight_kg` using `evaluate_regression` to compute MAE, RMSE, and $R^2$ using `safe_r2_score`.

---

## 3. Target Validity and Data Quality Audit

### 3.1 Target Naming & Alias Resolution
- **Investigation:** In Phase 4 documentation and prompts, the string `Waste_Quantity_kg` appeared alongside `Waste_Weight_kg`.
- **Audit Result:** `Waste_Weight_kg` is the sole actual column in `data/raw/SmartCanteen_Final_Dataset.csv`. `Waste_Quantity_kg` does not exist anywhere in the raw data or production database schemas. Verified by test `test_target_column_naming_consistency`.

### 3.2 Analysis of `Cost_Loss`
- **Investigation:** Does `Cost_Loss` represent an independent measurement or a derived field?
- **Audit Result:**
  $$\text{Cost\_Loss} = \text{round}(\text{Waste\_Weight\_kg} \times \text{Unit\_Price\_per\_kg}, 2)$$
  Across all 2,600 rows:
  - Maximum absolute discrepancy: $0.0051$ (attributable entirely to 2-decimal rounding).
  - Mean absolute discrepancy: $0.0006$.
  - Exact matches within $10^{-4}$: $88.1\%$.
- **Severity & Impact:** `Cost_Loss` is a purely deterministic algebraic derivative. If `Cost_Loss` were ever provided as an input feature, it would cause 100% target leakage. We confirmed `Cost_Loss` is strictly excluded from `TemporalFeaturePipeline`.

### 3.3 Deconstruction of `Waste_Risk`
- **Investigation:** How was `Waste_Risk` generated, and what are its operational thresholds?
- **Audit Result:**
  `Waste_Risk` is an exact tertile binning of `Waste_Weight_kg`:
  - **Low Risk ($N=869$, $33.4\%$):** $\text{Waste\_Weight\_kg} \in [0.10, 1.78]\text{ kg}$
  - **Medium Risk ($N=872$, $33.5\%$):** $\text{Waste\_Weight\_kg} \in [1.79, 3.42]\text{ kg}$
  - **High Risk ($N=859$, $33.0\%$):** $\text{Waste\_Weight\_kg} \in [3.43, 5.00]\text{ kg}$
  The 33.33% and 66.67% quantiles of `Waste_Weight_kg` are exactly $1.78\text{ kg}$ and $3.42\text{ kg}$.
- **Implication:** `Waste_Risk` contains zero independent ground truth. It is simply a discretization of a noisy continuous target. Attempting to predict `Waste_Risk` directly using an independent classifier is mathematically redundant with predicting `Waste_Weight_kg` and thresholding the result. Furthermore, because `Waste_Weight_kg` has near-zero predictable signal from the features, the classifier's observed 35.4% accuracy is simply random guessing across three equal bins.

### 3.4 Unit of Observation & Dataset Structure
- **Granularity:** Each row represents a unique combination of `(Date, Meal, Canteen_Section, Food_Category)`:
  - 3 Meals: Breakfast ($N=869$), Lunch ($N=867$), Dinner ($N=864$)
  - 4 Canteen Sections: A ($N=652$), B ($N=654$), C ($N=646$), D ($N=648$)
  - 4 Food Categories: Meat ($N=653$), Rice ($N=659$), Soup ($N=637$), Vegetables ($N=651$)
  - Daily observations: 37 to 46 rows per day (mean 42.6).
  - Exact duplicates across `(Date, Meal, Canteen_Section, Food_Category)`: **0 duplicates** across all 2,600 rows.
- **Operational Reality:** This unit of prediction is a specific food category within a specific canteen section for a single meal. It is **not** total daily canteen waste, nor is it individual student plate waste.

---

## 4. Synthesis of Current Model Evidence

We summarize the verified empirical evidence across all phases.

### 4.1 Summary of Evaluated Candidates (Development Folds 1–4)

| Candidate Model / Baseline | Dev MAE (kg) | % Diff vs Mean | Dev RMSE (kg) | Dev $R^2$ | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean (Naive Baseline)** | **1.2428 ± 0.0595** | **baseline** | **1.4281 ± 0.0512** | **-0.0021 ± 0.0035** | **Optimal on current data** |
| **Dummy_Median (Naive Baseline)**| 1.2444 ± 0.0596 | +0.13% | 1.4297 ± 0.0510 | -0.0044 ± 0.0040 | Underperforms Mean |
| **Candidate_Temporal_RF** | 1.2491 ± 0.0590 | +0.51% | 1.4358 ± 0.0486 | -0.0132 ± 0.0196 | Fails to beat baseline |
| **XGBoost_Regularized** | 1.2495 ± 0.0595 | +0.54% | 1.4376 ± 0.0495 | -0.0157 ± 0.0258 | Fails to beat baseline |
| **Retrained_Legacy_RF** | 1.2862 ± 0.0638 | +3.49% | 1.4921 ± 0.0537 | -0.0938 ± 0.0264 | Severe calendar memorization |
| **Blend_50RF_50XGB** | 1.2489 ± 0.0595 | +0.49% | 1.4360 ± 0.0490 | -0.0136 ± 0.0228 | Fails to beat baseline |
| **Shrink_50Blend_50Mean** | 1.2448 ± 0.0589 | +0.16% | 1.4301 ± 0.0498 | -0.0050 ± 0.0125 | Monotonically approaches Mean |
| **Ridge_Stacking (Folds 2–4)** | 1.2579 ± 0.0651 | +0.34%* | 1.4380 ± 0.0601 | -0.0077 ± 0.0101 | Underperforms Mean ($1.2537\text{ kg}$) |

*\*Note: Comparison for Ridge Stacking is relative to the Dummy Mean on identical folds 2–4 ($1.2537\text{ kg}$).*

### 4.2 What the Evidence Supports vs What Remains Uncertain

- **What the Evidence Conclusively Supports:**
  1. No complex model (Random Forest, XGBoost, linear blend, shrinkage blend, or stacked meta-model) outperforms the constant training-fold mean baseline across 4 chronological development folds.
  2. The differences between model MAE and baseline MAE are tiny (within $0.006\text{ kg}$, or $+0.5\%$), and far smaller than fold-to-fold variability ($\sigma \approx 0.059\text{ kg}$).
  3. Shrinkage toward the mean improves accuracy because it dampens model variance; the training mean is the empirical minimum error state among tested configurations.
  4. Retraining the legacy Random Forest on raw dates causes severe overfitting ($R^2 = -0.0938$).
- **What Remains Uncertain (Correction of Theoretical Over-Claims):**
  1. We **cannot** mathematically assert that $1.2428\text{ kg}$ is an absolute "irreducible Bayes error floor." Proving a Bayes floor requires knowledge of the true underlying probability distribution $P(Y \mid X)$, which is unknown.
  2. We **cannot** claim that the mean is the "proven Bayes-optimal predictor" for all conceivable models. We can only state that **given the existing feature set**, all evaluated linear, tree-based, boosted, and stacked models fail to extract actionable signal beyond the sample mean.

---

## 5. Finding Severity Classification

| Finding ID | Description | Severity | Impact on Project |
| :---: | :--- | :---: | :--- |
| **F-01** | Dataset lacks operational volume features (headcount, portions cooked, portions served) | **Critical** | Prevents pre-meal forecasting; models cannot learn physical waste drivers. |
| **F-02** | `Waste_Risk` is a synthetic tertile binning of `Waste_Weight_kg` | **High** | Classification model is redundant with regression and behaves as random guessing. |
| **F-03** | History pooling in multi-day evaluation requires clear timeline definition | **Medium** | Valid for 1-day rolling inference; constitutes leakage if interpreted as 7-day batch forecast. |
| **F-04** | Discrepancy between `Waste_Quantity_kg` (prompt alias) and `Waste_Weight_kg` (actual) | **Low** | Resolved and tested; no code defect. |
| **F-05** | `Cost_Loss` is an algebraic derivative of target and price | **Low** | Excluded from features; no leakage present. |

---

## 6. Recommendations & Roadmap

1. **Stop Model Development on Current Data:** Cease algorithmic experimentation (no LightGBM, CatBoost, Neural Networks, or ensembling) until new operational data is collected.
2. **Implement Operational Data Collection Specification:** Adopt the schema defined in `docs/data_collection_spec.md` to collect mandatory operational variables (`Portions_Prepared`, `Portions_Served`, `Expected_Headcount`).
3. **Redefine the Pre-Meal Forecasting Target:** Transition the core prediction task from predicting retrospective category scrap to forecasting **Surplus Food / Overproduction**:
   $$\text{Surplus Portions} = \text{Portions Prepared} - \text{Portions Served}$$
4. **Preserve Production:** Keep the existing production service and models intact until genuine operational features are available.
