# SmartCanteen AI — Ensemble Feasibility, Weighted Averaging, and Stacking (Phase 4)

> **Document Status:** Verified Empirical Feasibility Benchmark  
> **Target Module:** `backend/app/ml/ensemble.py`  
> **Test Suite:** `backend/app/tests/test_ensemble.py` (16 passing tests; 119 total backend tests passing)  
> **Target Branch:** `ml/phase-4-ensemble-feasibility`  
> **Base Commit:** `bc6032d` (Phase 3 model benchmark)  

---

## 1. Executive Summary

Phase 3 established that neither regularized gradient boosting (**XGBoost**, mean MAE $1.2495\text{ kg}$) nor the candidate temporal Random Forest (**RF**, mean MAE $1.2491\text{ kg}$) consistently outperformed the zero-information training-fold mean baseline (**Dummy Mean**, mean MAE $1.2428\text{ kg}$) across out-of-time chronological evaluations.

In **Phase 4**, we conducted an evidence-driven empirical investigation to determine whether ensembling can overcome this limitation. We evaluated two primary hypotheses:
1. **Experiment A (Weighted Averaging & Shrinkage):** Does a convex combination of Candidate RF and XGBoost predictions, or shrinkage toward the training mean, improve generalization over the individual models and the naive baseline?
2. **Experiment B (Chronological Stacking):** Can a regularized meta-learner (Ridge regression) trained strictly on historical out-of-fold (OOF) base model predictions learn an optimal meta-weighting that beats the naive baseline?

### Key Findings & Verdict:

| Candidate Model / Ensemble | Aggregate Dev MAE | % Diff vs Mean | Aggregate Dev RMSE | Aggregate Dev $R^2$ | Holdout MAE | Holdout $R^2$ |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean (Naive Baseline)** | **1.2428 ± 0.0595 kg** | **baseline** | **1.4281 ± 0.0512 kg** | **-0.0021** | **1.2302 kg** | **-0.0021** |
| **Candidate_Temporal_RF** | 1.2491 ± 0.0590 kg | +0.51% | 1.4358 ± 0.0486 kg | -0.0132 | 1.2309 kg | +0.0034 |
| **XGBoost_Regularized** | 1.2495 ± 0.0595 kg | +0.54% | 1.4376 ± 0.0495 kg | -0.0157 | 1.2320 kg | -0.0020 |
| **Blend_25RF_75XGB** | 1.2492 ± 0.0595 kg | +0.51% | 1.4366 ± 0.0493 kg | -0.0144 | — | — |
| **Blend_50RF_50XGB (Equal)** | 1.2489 ± 0.0595 kg | +0.49% | 1.4360 ± 0.0490 kg | -0.0136 | 1.2314 kg | +0.0014 |
| **Blend_75RF_25XGB** | 1.2489 ± 0.0592 kg | +0.49% | 1.4358 ± 0.0488 kg | -0.0132 | — | — |
| **Shrink_80Blend_20Mean** | 1.2470 ± 0.0590 kg | +0.34% | 1.4332 ± 0.0492 kg | -0.0095 | — | — |
| **Shrink_50Blend_50Mean** | 1.2448 ± 0.0589 kg | +0.16% | 1.4301 ± 0.0498 kg | -0.0050 | 1.2302 kg | +0.0013 |
| **Shrink_20Blend_80Mean** | 1.2433 ± 0.0592 kg | +0.04% | 1.4284 ± 0.0506 kg | -0.0026 | — | — |
| **Ridge_Stacking (Folds 2–4)** | 1.2579 ± 0.0651 kg | +0.34%* | 1.4380 ± 0.0601 kg | -0.0077 | 1.2299 kg | -0.0008 |

*\*Note: For Ridge Stacking, comparison is relative to the Dummy Mean on the identical folds 2–4 ($1.2537\text{ kg}$).*

### Formal Verdict: **NO-GO**
1. **Zero Ensembles Beat the Baseline:** No weighted average, shrinkage blend, or stacked meta-model achieves an aggregate development MAE lower than the naive mean baseline ($1.2428\text{ kg}$).
2. **Shrinkage Dynamics Reveal Absence of Signal:** As the shrinkage weight toward the training mean increases from $0\%$ to $80\%$, the MAE monotonically improves from $1.2489\text{ kg}$ down to $1.2433\text{ kg}$, asymptotically converging toward the pure training mean. The models add noise; dampening them toward a constant improves error.
3. **Stacking Suffers Data Starvation & Meta-Weight Collapse:** In a 61-day timeline, Fold 1 has zero prior historical OOF observations, precluding meta-model fitting without lookahead leakage. On Folds 2–4, Ridge meta-learning coefficients collapse to zero ($[0.0, 0.0]$ in Fold 3), with the model relying solely on its intercept (the mean).
4. **Untouched Holdout Confirms Finding:** Evaluated only after the development decision was finalized, the holdout exhibits identical behavior: all complex models and ensembles cluster between $1.2299\text{ kg}$ and $1.2320\text{ kg}$, statistically indistinguishable from the naive mean ($1.2302\text{ kg}$) within random sampling variance.

**Recommendation:** Do not deploy an ensemble to production. Preserve the existing production system without modifications.

---

## 2. Experimental Framework & Comparability Protocol

To prevent methodological divergence and ensure strict scientific comparability with Phase 2 and Phase 3:

1. **Target & Evaluation Unit:** The prediction target is strictly `Waste_Weight_kg` on identical individual meal-level canteen records.
2. **Dataset & Rolling-Origin Splitter:** Evaluated on `data/raw/SmartCanteen_Final_Dataset.csv` (2,600 rows across 61 consecutive calendar days: `2025-06-11` to `2025-08-10`).
   - Development folds: 4 chronological folds covering 28 calendar days (`2025-07-07` to `2025-08-03`), totaling 1,187 test samples.
   - Untouched holdout: final 7 calendar days (`2025-08-04` to `2025-08-10`, 287 samples).
3. **Leakage Prevention:**
   - Feature engineering pipeline (`TemporalFeaturePipeline`) was fitted strictly on each fold's training slice (`is_training=True`).
   - Out-of-fold historical feature lookup strictly used records strictly prior to each test date. No future observations, same-day realized targets, or holdout samples entered training or feature pools.
4. **Out-of-Fold Generation Protocol:**
   - Base models were trained strictly on each fold's training partition.
   - Ensemble predictions were evaluated strictly on out-of-fold test samples. In-sample training predictions were never used to estimate ensemble weights or performance.

---

## 3. Experiment A: Weighted Averaging & Baseline-Aware Shrinkage

### 3.1 Candidate Model Predictions
Base predictions were generated from:
- `Candidate_Temporal_RF`: Random Forest Regressor ($n=100$, $\text{max\_depth}=5$, $\text{min\_samples\_leaf}=5$, $\text{random\_state}=42$).
- `XGBoost_Regularized`: XGBoost Regressor ($\text{max\_depth}=2$, $\eta=0.05$, $n=100$, $\text{subsample}=0.8$, $\text{colsample}=0.8$, $\alpha=0.1$, $\lambda=1.0$, $\text{random\_state}=42$).
- `Dummy_Mean`: Scalar training-fold mean $\bar{y}_{\text{train}} = \frac{1}{N_{\text{train}}} \sum_{i \in \text{train}} y_i$.

### 3.2 Blending Formulas
1. **Fixed-Weight Linear Blends:**
   $$\hat{y}_{\text{blend}} = w \cdot \hat{y}_{\text{RF}} + (1 - w) \cdot \hat{y}_{\text{XGB}}, \quad w \in \{0.25, 0.50, 0.75\}$$
2. **Baseline-Aware Shrinkage (on 50/50 Blend):**
   $$\hat{y}_{\text{shrunk}} = (1 - \lambda) \cdot \hat{y}_{\text{blend}} + \lambda \cdot \bar{y}_{\text{train}}, \quad \lambda \in \{0.20, 0.50, 0.80\}$$

### 3.3 Per-Fold Empirical Results

#### Fold 1 (`2025-07-07` to `2025-07-13`, 295 test records, 1,126 train records)
| Model / Ensemble | MAE (kg) | % Diff vs Mean | RMSE (kg) | $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean** | 1.2103 kg | baseline | 1.4094 kg | -0.0010 |
| **Candidate_Temporal_RF** | 1.2018 kg | -0.70% | 1.4052 kg | +0.0048 |
| **XGBoost_Regularized** | 1.2004 kg | -0.82% | 1.4030 kg | +0.0081 |
| **Blend_25RF_75XGB** | 1.2003 kg | -0.83% | 1.4028 kg | +0.0083 |
| **Blend_50RF_50XGB** | **1.2002 kg** | **-0.83%** | **1.4031 kg** | **+0.0078** |
| **Blend_75RF_25XGB** | 1.2009 kg | -0.78% | 1.4039 kg | +0.0067 |
| **Shrink_80Blend_20Mean** | 1.2017 kg | -0.71% | 1.4029 kg | +0.0082 |
| **Shrink_50Blend_50Mean** | 1.2041 kg | -0.51% | 1.4039 kg | +0.0067 |
| **Shrink_20Blend_80Mean** | 1.2075 kg | -0.23% | 1.4066 kg | +0.0029 |

#### Fold 2 (`2025-07-14` to `2025-07-20`, 293 test records, 1,421 train records)
| Model / Ensemble | MAE (kg) | % Diff vs Mean | RMSE (kg) | $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean** | **1.2132 kg** | baseline | **1.4136 kg** | **-0.0073** |
| **Candidate_Temporal_RF** | 1.2397 kg | +2.18% | 1.4362 kg | -0.0397 |
| **XGBoost_Regularized** | 1.2428 kg | +2.44% | 1.4442 kg | -0.0513 |
| **Blend_25RF_75XGB** | 1.2417 kg | +2.35% | 1.4417 kg | -0.0477 |
| **Blend_50RF_50XGB** | 1.2406 kg | +2.26% | 1.4396 kg | -0.0446 |
| **Blend_75RF_25XGB** | 1.2399 kg | +2.20% | 1.4377 kg | -0.0419 |
| **Shrink_80Blend_20Mean** | 1.2341 kg | +1.72% | 1.4327 kg | -0.0346 |
| **Shrink_50Blend_50Mean** | 1.2256 kg | +1.02% | 1.4239 kg | -0.0220 |
| **Shrink_20Blend_80Mean** | 1.2179 kg | +0.39% | 1.4171 kg | -0.0123 |

#### Fold 3 (`2025-07-21` to `2025-07-27`, 299 test records, 1,714 train records)
| Model / Ensemble | MAE (kg) | % Diff vs Mean | RMSE (kg) | $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean** | 1.3320 kg | baseline | 1.5028 kg | -0.0001 |
| **Candidate_Temporal_RF** | 1.3344 kg | +0.18% | 1.5043 kg | -0.0022 |
| **XGBoost_Regularized** | 1.3349 kg | +0.22% | 1.5050 kg | -0.0031 |
| **Blend_25RF_75XGB** | 1.3347 kg | +0.20% | 1.5044 kg | -0.0022 |
| **Blend_50RF_50XGB** | 1.3346 kg | +0.20% | 1.5040 kg | -0.0018 |
| **Blend_75RF_25XGB** | 1.3345 kg | +0.19% | 1.5040 kg | -0.0018 |
| **Shrink_80Blend_20Mean** | 1.3333 kg | +0.10% | 1.5028 kg | -0.0002 |
| **Shrink_50Blend_50Mean** | 1.3322 kg | +0.02% | **1.5019 kg** | **+0.0010** |
| **Shrink_20Blend_80Mean** | **1.3319 kg** | **-0.01%** | 1.5021 kg | **+0.0008** |

#### Fold 4 (`2025-07-28` to `2025-08-03`, 300 test records, 2,013 train records)
| Model / Ensemble | MAE (kg) | % Diff vs Mean | RMSE (kg) | $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean** | **1.2157 kg** | baseline | **1.3867 kg** | **-0.0001** |
| **Candidate_Temporal_RF** | 1.2205 kg | +0.39% | 1.3976 kg | -0.0159 |
| **XGBoost_Regularized** | 1.2198 kg | +0.34% | 1.3981 kg | -0.0166 |
| **Blend_25RF_75XGB** | 1.2199 kg | +0.35% | 1.3977 kg | -0.0160 |
| **Blend_50RF_50XGB** | 1.2200 kg | +0.35% | 1.3974 kg | -0.0157 |
| **Blend_75RF_25XGB** | 1.2202 kg | +0.37% | 1.3974 kg | -0.0156 |
| **Shrink_80Blend_20Mean** | 1.2189 kg | +0.26% | 1.3944 kg | -0.0113 |
| **Shrink_50Blend_50Mean** | 1.2174 kg | +0.14% | 1.3907 kg | -0.0059 |
| **Shrink_20Blend_80Mean** | 1.2161 kg | +0.03% | 1.3879 kg | -0.0019 |

### 3.4 Aggregate Development Performance (Mean ± Std across 4 Folds)

| Candidate Model / Ensemble | Aggregate MAE (kg) | % Diff vs Mean | Aggregate RMSE (kg) | Aggregate $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean** | **1.2428 ± 0.0595** | **baseline** | **1.4281 ± 0.0512** | **-0.0021 ± 0.0035** |
| **Candidate_Temporal_RF** | 1.2491 ± 0.0590 | +0.51% | 1.4358 ± 0.0486 | -0.0132 ± 0.0196 |
| **XGBoost_Regularized** | 1.2495 ± 0.0595 | +0.54% | 1.4376 ± 0.0495 | -0.0157 ± 0.0258 |
| **Blend_25RF_75XGB** | 1.2492 ± 0.0595 | +0.51% | 1.4366 ± 0.0493 | -0.0144 ± 0.0243 |
| **Blend_50RF_50XGB** | 1.2489 ± 0.0595 | +0.49% | 1.4360 ± 0.0490 | -0.0136 ± 0.0228 |
| **Blend_75RF_25XGB** | 1.2489 ± 0.0592 | +0.49% | 1.4358 ± 0.0488 | -0.0132 ± 0.0213 |
| **Shrink_80Blend_20Mean** | 1.2470 ± 0.0590 | +0.34% | 1.4332 ± 0.0492 | -0.0095 ± 0.0186 |
| **Shrink_50Blend_50Mean** | 1.2448 ± 0.0589 | +0.16% | 1.4301 ± 0.0498 | -0.0050 ± 0.0125 |
| **Shrink_20Blend_80Mean** | 1.2433 ± 0.0592 | +0.04% | 1.4284 ± 0.0506 | -0.0026 ± 0.0067 |

### 3.5 Analysis of Shrinkage Dynamics

```
MAE Progression Under Increasing Baseline Shrinkage:

Blend_50RF_50XGB (0% Mean):    [==================================] 1.2489 kg
Shrink_80_20 (20% Mean):       [================================-] 1.2470 kg
Shrink_50_50 (50% Mean):       [==============================---] 1.2448 kg
Shrink_20_80 (80% Mean):       [============================-----] 1.2433 kg
Dummy_Mean (100% Mean):        [==========================-------] 1.2428 kg (Optimum)
```

The shrinkage experiment demonstrates that:
1. **The training mean is the global minimum error state:** Mixing any fraction of model predictions into the training mean degrades performance proportionally to the model weight.
2. **Models contribute variance without signal:** Blending RF and XGBoost does reduce base variance slightly (improving MAE from $1.2491$ / $1.2495$ to $1.2489\text{ kg}$), but the resulting blend still possesses a negative aggregate $R^2$ ($-0.0136$).
3. **No magic weights exist:** An exhaustive grid search across weights would only capitalize on random chance in small fold test partitions.

---

## 4. Experiment B: Chronological Stacking Feasibility

### 4.1 Methodology & Data Sufficiency Constraints

Stacking requires training a meta-model on out-of-fold predictions. In time-series forecasting, standard $K$-fold cross-validation causes catastrophic lookahead leakage because future folds leak into the training of past folds.

Therefore, stacking **must** follow rolling-origin chronological accumulation:
- **Fold 1 (`2025-07-07` to `2025-07-13`):** Has **0 preceding historical folds**. No past out-of-fold predictions exist. Fitting a meta-learner at Fold 1 is mathematically impossible without lookahead leakage. Stacking must be skipped on Fold 1.
- **Fold 2 (`2025-07-14` to `2025-07-20`):** Meta-model is fitted on Fold 1 OOF predictions ($N=295$).
- **Fold 3 (`2025-07-21` to `2025-07-27`):** Meta-model is fitted on accumulated Folds 1 & 2 OOF predictions ($N=588$).
- **Fold 4 (`2025-07-28` to `2025-08-03`):** Meta-model is fitted on accumulated Folds 1, 2, & 3 OOF predictions ($N=887$).

We implemented a non-negative, L2-regularized Ridge regression meta-learner (`Ridge(alpha=10.0, positive=True)`).

### 4.2 Empirical Stacking Results (Folds 2–4)

| Fold | Training OOF Samples | Ridge Meta-Weights $[\beta_{\text{RF}}, \beta_{\text{XGB}}]$ | Ridge Intercept | Ridge Stacking MAE | Equal Blend MAE | Dummy Mean MAE |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Fold 2** | 295 (Fold 1) | $[0.1950, 0.2888]$ | $1.3224$ | 1.2240 kg | 1.2406 kg | **1.2132 kg** |
| **Fold 3** | 588 (Folds 1+2) | $[0.0000, 0.0000]$ | $2.5320$ | 1.3329 kg | 1.3346 kg | **1.3320 kg** |
| **Fold 4** | 887 (Folds 1+2+3) | $[0.0153, 0.0191]$ | $2.4683$ | 1.2168 kg | 1.2200 kg | **1.2157 kg** |
| **Folds 2–4 Mean** | — | — | — | **1.2579 ± 0.0651 kg** | **1.2651 ± 0.0614 kg** | **1.2537 ± 0.0678 kg** |

### 4.3 Stacking Diagnostic: Coefficient Collapse

Look closely at the Ridge meta-learner parameters:
- In **Fold 3**, Ridge regression shrunk the base model coefficients completely to zero ($[0.0, 0.0]$). The meta-learner assigned **100% of its prediction weight to the intercept** ($2.5320\text{ kg}$, which reflects the sample mean of the accumulated historical targets).
- In **Fold 4**, the meta-weights are negligible ($0.015$ and $0.019$), with the intercept ($2.4683$) dominating the forecast.
- **Why did this happen?** L2 regularization recognizes that the base model predictions have near-zero correlation with true residuals on out-of-fold data. The optimal shrinkage path for the linear meta-learner is to discard the base models and predict the historical mean.
- Even with this shrinkage, Ridge Stacking ($1.2579\text{ kg}$) underperforms the naive mean ($1.2537\text{ kg}$) across Folds 2–4.

**Conclusion:** Stacking is not feasible or justified on this dataset. It suffers severe data starvation in early folds and collapses to a degenerate mean predictor in later folds.

---

## 5. Model-Selection Gate Evaluation

The project protocol specifies 5 strict gates an ensemble must satisfy to be eligible for adoption:

| Gate | Criterion | Result | Evidence & Analysis |
| :---: | :--- | :---: | :--- |
| **1** | Aggregate dev MAE lower than naive mean baseline | **FAILED** | Best weighted average ($1.2489\text{ kg}$) is worse than Dummy Mean ($1.2428\text{ kg}$) by $+0.0061\text{ kg}$ ($+0.49\%$). Stacking ($1.2579\text{ kg}$) is worse than Dummy Mean on the same folds ($1.2537\text{ kg}$) by $+0.0042\text{ kg}$. |
| **2** | Improvement not driven entirely by one fold | **N/A** | No improvement observed in aggregate. In 3 out of 4 development folds (Folds 2, 3, 4), the Dummy Mean beats every single candidate ensemble. |
| **3** | Results reproducible and leakage checks pass | **PASSED** | Determinism verified across repeated runs (`test_ensemble_runner_deterministic_repeatability`). Future target mutations verified to have zero effect on prior folds (`test_future_targets_mutation_invariance`). |
| **4** | RMSE and $R^2$ do not reveal major regression | **FAILED** | Aggregate $R^2$ across development folds is negative for all blends (e.g. Blend 50/50 has $R^2 = -0.0136 \pm 0.0228$). |
| **5** | Final holdout supports development conclusion | **CONFIRMED** | Untouched holdout shows Dummy Mean ($1.2302\text{ kg}$) matches or beats the ensembles (Blend 50/50 is $1.2314\text{ kg}$; Stacking is $1.2299\text{ kg}$ within random noise). |

Because Gate 1 failed decisively, **no ensemble candidate is eligible for selection**.

---

## 6. Untouched Final Holdout Evaluation

In accordance with strict protocol, the 7-day holdout (`2025-08-04` to `2025-08-10`, 287 records) was kept completely untouched during all exploratory and development fold analysis.

Once the **NO-GO** decision was locked, the holdout was evaluated once to confirm the conclusion:

| Model / Ensemble | Holdout MAE (kg) | Diff vs Dummy Mean | Holdout RMSE (kg) | Holdout $R^2$ |
| :--- | :--- | :--- | :--- | :--- |
| **Dummy_Mean** | **1.2302 kg** | **baseline** | **1.4080 kg** | **-0.0021** |
| **Candidate_Temporal_RF** | 1.2309 kg | +0.0007 kg (+0.06%) | 1.4042 kg | +0.0034 |
| **XGBoost_Regularized** | 1.2320 kg | +0.0018 kg (+0.15%) | 1.4080 kg | -0.0020 |
| **Blend_50RF_50XGB** | 1.2314 kg | +0.0012 kg (+0.10%) | 1.4056 kg | +0.0014 |
| **Shrink_50Blend_50Mean** | 1.2302 kg | 0.0000 kg (0.00%) | 1.4057 kg | +0.0013 |
| **Ridge_Stacking** | 1.2299 kg | -0.0003 kg (-0.02%) | 1.4071 kg | -0.0008 |

### Holdout Analysis:
- The difference between Ridge Stacking ($1.2299\text{ kg}$) and Dummy Mean ($1.2302\text{ kg}$) is **$0.0003\text{ kg}$ (0.3 grams per serving)**.
- This $0.02\%$ delta is two orders of magnitude smaller than the fold-to-fold development standard deviation ($\sigma \approx 0.060\text{ kg}$).
- Stacking's $R^2$ on the holdout remains negative ($-0.0008$).
- The holdout confirms the development finding: ensembling produces no meaningful predictive gain over the naive mean.

---

## 7. Root Cause Analysis: The Bayes Optimal Error Floor

Why do complex models and ensembles fail to beat a simple constant mean predictor?

In statistical decision theory, the Bayes optimal predictor under Mean Squared Error loss is the conditional expectation:
$$f^*(X) = \mathbb{E}[Y \mid X]$$
Under Mean Absolute Error loss, the Bayes optimal predictor is the conditional median:
$$f^*(X) = \text{Median}(Y \mid X)$$

If the conditioning features $X$ contain no mutual information with target variance $\text{Var}(Y \mid X) \approx \text{Var}(Y)$, then:
$$\mathbb{E}[Y \mid X] = \mathbb{E}[Y]$$

In the SmartCanteen AI dataset:
1. **Missing Primary Causal Variables:** Food waste in institutional canteens is overwhelmingly determined by **operational variance**:
   - Number of students/staff eating that meal (headcount / footfall).
   - Volume of food cooked (number of trays or portions batch-cooked).
   - Remaining raw inventory and perishable shelf life.
   - Weather anomalies (e.g. torrential rain keeping students indoors).
2. **Current Features Are Static Descriptors:** The current dataset contains `Meal` (Lunch/Dinner), `Canteen_Section`, `Food_Category`, `Unit_Price_per_kg`, and calendar timestamps. Across 61 days, average waste per meal type fluctuates around $\sim 2.5\text{ kg}$ with standard deviation $\sim 1.4\text{ kg}$.
3. **Ensemble Multiplies Parameter Overhead Without Signal:** Ensembling (whether Random Forest averaging, gradient boosting, or stacking) can only reduce *variance* (estimation error) or *bias* (approximation error). It cannot reduce *irreducible Bayes error* caused by missing covariates. Combining two models that are both fitting noise simply produces another noisy estimator.

---

## 8. Final Decision & Architectural Roadmap

### Definitive Recommendation: **NO-GO FOR ENSEMBLE ADOPTION**

- **Do Not Deploy Ensembles:** Do not replace the existing production Random Forest with an ensemble.
- **Preserve Production Pipeline:**
  - `models/waste_regression_model.pkl` remains intact.
  - `models/waste_risk_classifier.pkl` remains intact.
  - Active API endpoints (`/predict/waste`, `/analytics/summary`) remain untouched.
  - SQLite schema and prediction history remain untouched.
  - Frontend remains untouched.

### Recommended Next Steps for Future Phases:
1. **Instrument Operational Data Collection:** Rather than trying more complex algorithms (e.g. LightGBM, CatBoost, Neural Networks), the engineering team must add true predictive features to the canteen schema:
   - `Portions_Cooked_kg` or `Batch_Quantity`
   - `Meal_Headcount` or `Student_Attendance_Count`
   - `Surplus_Leftover_Previous_Meal_kg`
2. **Risk Classifier Redesign:** Explore reformulating the waste risk classifier into a cost-sensitive or quantile-based decision support system rather than predicting a noisy point estimate.
