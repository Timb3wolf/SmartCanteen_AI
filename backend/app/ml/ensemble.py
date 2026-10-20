"""Ensemble utilities and experimental feasibility benchmark for SmartCanteen AI.

Provides:
- WeightedAverageEnsemble: Validated weighted blending with optional baseline-aware shrinkage.
- ChronologicalStackingMetaLearner: Strictly chronological meta-learner trained on out-of-fold base predictions.
- EnsembleExperimentRunner: Orchestrator executing rolling-origin ensemble benchmarks and holdout verification.
"""

from dataclasses import dataclass, field
import datetime
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
import xgboost as xgb

from backend.app.ml.benchmark import (
    BenchmarkFoldRecord,
    BenchmarkModelSpec,
    ModelBenchmarkRunner,
    ModelFoldResult,
)
from backend.app.ml.evaluation import (
    RegressionMetrics,
    RollingOriginSplitter,
    SplitFold,
    evaluate_regression,
    safe_r2_score,
)
from backend.app.ml.features import (
    TemporalFeatureConfig,
    TemporalFeaturePipeline,
    parse_strict_date,
)


@dataclass
class EnsembleSpec:
    """Specification for an ensemble candidate."""

    name: str
    weights: Dict[str, float]
    shrinkage_to_mean: float = 0.0  # 0.0 = pure base ensemble, 1.0 = pure training mean


class WeightedAverageEnsemble:
    """Deterministic, validated linear blending with baseline-aware shrinkage.

    Attributes:
        weights: Mapping of model_name -> weight. Must be non-negative and sum to 1.0.
        shrinkage_to_mean: Fraction of prediction shrunk toward the training-fold mean (0.0 to 1.0).
    """

    def __init__(
        self,
        weights: Dict[str, float],
        shrinkage_to_mean: float = 0.0,
    ) -> None:
        self.weights = dict(weights)
        self.shrinkage_to_mean = float(shrinkage_to_mean)
        self._validate()

    def _validate(self) -> None:
        """Validate ensemble configuration invariants."""
        if not self.weights:
            raise ValueError("Ensemble weights dictionary cannot be empty.")

        for name, w in self.weights.items():
            if not isinstance(w, (int, float)) or math.isnan(w) or math.isinf(w):
                raise ValueError(f"Weight for model '{name}' must be a finite number, got {w}")
            if w < 0.0:
                raise ValueError(f"Weight for model '{name}' cannot be negative, got {w}")

        total_weight = sum(self.weights.values())
        if not math.isclose(total_weight, 1.0, rel_tol=1e-5, abs_tol=1e-5):
            raise ValueError(f"Ensemble weights must sum to 1.0, got sum = {total_weight}")

        if not (0.0 <= self.shrinkage_to_mean <= 1.0):
            raise ValueError(
                f"shrinkage_to_mean must be in [0.0, 1.0], got {self.shrinkage_to_mean}"
            )

    def predict(
        self,
        predictions: Dict[str, np.ndarray],
        training_mean: Optional[float] = None,
    ) -> np.ndarray:
        """Compute the ensemble prediction vector.

        Args:
            predictions: Mapping of model_name -> 1D numpy array of predictions.
            training_mean: Scalar mean of training fold targets (required if shrinkage_to_mean > 0).

        Returns:
            1D numpy array containing blended predictions.
        """
        # 1. Check all required models are present
        missing_models = [m for m in self.weights if m not in predictions]
        if missing_models:
            raise ValueError(f"Predictions missing required models: {missing_models}")

        # 2. Validate shapes
        sample_counts = {m: len(predictions[m]) for m in self.weights}
        unique_counts = set(sample_counts.values())
        if len(unique_counts) > 1:
            raise ValueError(f"Inconsistent prediction array lengths: {sample_counts}")

        n_samples = next(iter(unique_counts))
        if n_samples == 0:
            return np.array([], dtype=np.float64)

        # 3. Compute base weighted combination
        blended = np.zeros(n_samples, dtype=np.float64)
        for model_name, weight in self.weights.items():
            arr = np.asarray(predictions[model_name], dtype=np.float64).ravel()
            blended += weight * arr

        # 4. Apply baseline shrinkage if specified
        if self.shrinkage_to_mean > 0.0:
            if training_mean is None or math.isnan(training_mean) or math.isinf(training_mean):
                raise ValueError(
                    f"A finite scalar training_mean is required when shrinkage_to_mean > 0, got {training_mean}"
                )
            blended = (1.0 - self.shrinkage_to_mean) * blended + self.shrinkage_to_mean * float(training_mean)

        return blended


class ChronologicalStackingMetaLearner:
    """Meta-learner trained on chronological out-of-fold (OOF) base model predictions.

    Ensures strict time-ordering:
    A meta-learner for fold k can only be trained on OOF predictions from folds 1..(k-1).
    """

    def __init__(
        self,
        model_names: List[str],
        alpha: float = 10.0,
        positive: bool = True,
    ) -> None:
        self.model_names = list(model_names)
        self.alpha = float(alpha)
        self.positive = positive
        self.regressor_: Optional[Ridge] = None
        self.fitted_: bool = False

    def fit(
        self,
        oof_predictions: Dict[str, np.ndarray],
        targets: np.ndarray,
    ) -> "ChronologicalStackingMetaLearner":
        """Fit regularized linear meta-model on accumulated historical OOF predictions."""
        for name in self.model_names:
            if name not in oof_predictions:
                raise ValueError(f"OOF predictions missing required model: '{name}'")

        y = np.asarray(targets, dtype=np.float64).ravel()
        n_samples = len(y)
        if n_samples == 0:
            raise ValueError("Cannot fit meta-learner on empty targets.")

        X_cols = []
        for name in self.model_names:
            arr = np.asarray(oof_predictions[name], dtype=np.float64).ravel()
            if len(arr) != n_samples:
                raise ValueError(
                    f"OOF array for '{name}' length ({len(arr)}) does not match targets ({n_samples})"
                )
            X_cols.append(arr)

        X = np.column_stack(X_cols)

        # Regularized Ridge meta-learner (with optional non-negative weights constraint)
        self.regressor_ = Ridge(alpha=self.alpha, positive=self.positive)
        self.regressor_.fit(X, y)
        self.fitted_ = True
        return self

    def predict(self, predictions: Dict[str, np.ndarray]) -> np.ndarray:
        """Predict using the fitted meta-model."""
        if not self.fitted_ or self.regressor_ is None:
            raise RuntimeError("Meta-learner has not been fitted.")

        for name in self.model_names:
            if name not in predictions:
                raise ValueError(f"Predictions missing required model: '{name}'")

        X_cols = [np.asarray(predictions[name], dtype=np.float64).ravel() for name in self.model_names]
        X = np.column_stack(X_cols)
        return self.regressor_.predict(X)

    @property
    def coef_(self) -> np.ndarray:
        if not self.fitted_ or self.regressor_ is None:
            raise RuntimeError("Meta-learner has not been fitted.")
        return self.regressor_.coef_

    @property
    def intercept_(self) -> float:
        if not self.fitted_ or self.regressor_ is None:
            raise RuntimeError("Meta-learner has not been fitted.")
        return float(self.regressor_.intercept_)


class EnsembleExperimentRunner:
    """Executes leakage-free, chronological ensemble benchmarks and holdout verification."""

    def __init__(
        self,
        splitter: Optional[RollingOriginSplitter] = None,
        random_state: int = 42,
    ) -> None:
        self.splitter = splitter or RollingOriginSplitter(
            min_train_days=26,
            test_days=7,
            num_folds=4,
            holdout_days=7,
        )
        self.random_state = random_state

    def get_default_ensemble_specs(self) -> List[EnsembleSpec]:
        """Predefined set of weighted averaging and baseline shrinkage candidates."""
        return [
            # Experiment A: Fixed weight pairs
            EnsembleSpec(
                name="Blend_25RF_75XGB",
                weights={"Candidate_Temporal_RF": 0.25, "XGBoost_Regularized": 0.75},
            ),
            EnsembleSpec(
                name="Blend_50RF_50XGB",
                weights={"Candidate_Temporal_RF": 0.50, "XGBoost_Regularized": 0.50},
            ),
            EnsembleSpec(
                name="Blend_75RF_25XGB",
                weights={"Candidate_Temporal_RF": 0.75, "XGBoost_Regularized": 0.25},
            ),
            # Experiment A: Baseline-aware shrinkage applied to the 50/50 blend
            EnsembleSpec(
                name="Shrink_80Blend_20Mean",
                weights={"Candidate_Temporal_RF": 0.50, "XGBoost_Regularized": 0.50},
                shrinkage_to_mean=0.20,
            ),
            EnsembleSpec(
                name="Shrink_50Blend_50Mean",
                weights={"Candidate_Temporal_RF": 0.50, "XGBoost_Regularized": 0.50},
                shrinkage_to_mean=0.50,
            ),
            EnsembleSpec(
                name="Shrink_20Blend_80Mean",
                weights={"Candidate_Temporal_RF": 0.50, "XGBoost_Regularized": 0.50},
                shrinkage_to_mean=0.80,
            ),
        ]

    def run_development_ensembles(
        self,
        df: pd.DataFrame,
        ensemble_specs: Optional[List[EnsembleSpec]] = None,
        include_stacking: bool = True,
    ) -> Dict[str, Any]:
        """Run complete chronological development benchmark evaluating base models and ensembles."""
        specs = ensemble_specs or self.get_default_ensemble_specs()
        folds = self.splitter.split(df)
        if not folds:
            raise ValueError("Splitter generated 0 folds.")

        fold_records: List[Dict[str, Any]] = []
        all_model_metrics: Dict[str, List[RegressionMetrics]] = {}

        # Tracking for chronological stacking
        oof_rf_history: List[np.ndarray] = []
        oof_xgb_history: List[np.ndarray] = []
        oof_y_history: List[np.ndarray] = []

        for fold in folds:
            train_df = df.iloc[fold.train_indices].copy()
            test_df = df.iloc[fold.test_indices].copy()

            y_train = train_df["Waste_Weight_kg"].values
            y_test = test_df["Waste_Weight_kg"].values

            # Feature pipeline fitted strictly on training data
            pipe = TemporalFeaturePipeline()
            pipe.fit(train_df)
            X_train = pipe.transform(train_df, is_training=True)
            history_pool = pd.concat([train_df, test_df], ignore_index=True)
            X_test = pipe.transform(test_df, is_training=False, historical_records=history_pool)

            # 1. Base Model: Dummy Mean
            mean_baseline_val = float(np.mean(y_train))
            p_mean = np.full_like(y_test, mean_baseline_val)

            # 2. Base Model: Candidate Temporal RF
            rf = RandomForestRegressor(
                n_estimators=100,
                max_depth=5,
                min_samples_leaf=5,
                random_state=self.random_state,
            )
            rf.fit(X_train, y_train)
            p_rf = rf.predict(X_test)

            # 3. Base Model: Regularized XGBoost
            xg = xgb.XGBRegressor(
                max_depth=2,
                learning_rate=0.05,
                n_estimators=100,
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
                random_state=self.random_state,
            )
            xg.fit(X_train, y_train)
            p_xgb = xg.predict(X_test)

            base_predictions = {
                "Candidate_Temporal_RF": p_rf,
                "XGBoost_Regularized": p_xgb,
            }

            fold_predictions: Dict[str, np.ndarray] = {
                "Dummy_Mean": p_mean,
                "Candidate_Temporal_RF": p_rf,
                "XGBoost_Regularized": p_xgb,
            }

            # Evaluate predefined weighted average and shrinkage ensembles
            for spec in specs:
                ensemble = WeightedAverageEnsemble(
                    weights=spec.weights,
                    shrinkage_to_mean=spec.shrinkage_to_mean,
                )
                pred_ens = ensemble.predict(base_predictions, training_mean=mean_baseline_val)
                fold_predictions[spec.name] = pred_ens

            # Chronological Stacking (Folds 2-4 only, where historical OOF exists)
            stacking_coefs = None
            stacking_intercept = None
            if include_stacking:
                if len(oof_rf_history) > 0:
                    accum_rf = np.concatenate(oof_rf_history)
                    accum_xgb = np.concatenate(oof_xgb_history)
                    accum_y = np.concatenate(oof_y_history)

                    meta_learner = ChronologicalStackingMetaLearner(
                        model_names=["Candidate_Temporal_RF", "XGBoost_Regularized"],
                        alpha=10.0,
                        positive=True,
                    )
                    meta_learner.fit(
                        oof_predictions={"Candidate_Temporal_RF": accum_rf, "XGBoost_Regularized": accum_xgb},
                        targets=accum_y,
                    )
                    p_stacking = meta_learner.predict(base_predictions)
                    fold_predictions["Ridge_Stacking"] = p_stacking
                    stacking_coefs = meta_learner.coef_.tolist()
                    stacking_intercept = meta_learner.intercept_

                # Accumulate current fold out-of-fold predictions strictly AFTER evaluation
                oof_rf_history.append(p_rf)
                oof_xgb_history.append(p_xgb)
                oof_y_history.append(y_test)

            # Score all models on the current fold
            fold_results: Dict[str, Dict[str, float]] = {}
            for m_name, preds in fold_predictions.items():
                ev = evaluate_regression(y_test, preds)
                abs_diff = float(ev.mae - evaluate_regression(y_test, p_mean).mae)
                pct_diff = float((abs_diff / evaluate_regression(y_test, p_mean).mae) * 100.0)
                fold_results[m_name] = {
                    "mae": ev.mae,
                    "rmse": ev.rmse,
                    "r2": ev.r2,
                    "abs_diff_vs_mean": abs_diff,
                    "pct_diff_vs_mean": pct_diff,
                }
                if m_name not in all_model_metrics:
                    all_model_metrics[m_name] = []
                all_model_metrics[m_name].append(ev)

            test_dates_str = f"{fold.test_start_date} to {fold.test_end_date}"
            fold_records.append({
                "fold_idx": fold.fold_idx,
                "train_dates": f"{fold.train_start_date} to {fold.train_end_date}",
                "test_dates": test_dates_str,
                "train_samples": fold.train_count,
                "test_samples": fold.test_count,
                "models": fold_results,
                "stacking_coefs": stacking_coefs,
                "stacking_intercept": stacking_intercept,
            })

        # Compute aggregate summary across folds
        aggregate_summary: Dict[str, Dict[str, float]] = {}
        for m_name, ev_list in all_model_metrics.items():
            maes = [e.mae for e in ev_list]
            rmses = [e.rmse for e in ev_list]
            r2s = [e.r2 for e in ev_list]
            n_folds = len(maes)
            aggregate_summary[m_name] = {
                "num_folds": float(n_folds),
                "mean_mae": float(np.mean(maes)),
                "std_mae": float(np.std(maes, ddof=1)) if n_folds > 1 else 0.0,
                "mean_rmse": float(np.mean(rmses)),
                "std_rmse": float(np.std(rmses, ddof=1)) if n_folds > 1 else 0.0,
                "mean_r2": float(np.mean(r2s)),
                "std_r2": float(np.std(r2s, ddof=1)) if n_folds > 1 else 0.0,
            }

        return {
            "folds": fold_records,
            "aggregate_summary": aggregate_summary,
            "accumulated_oof": {
                "Candidate_Temporal_RF": np.concatenate(oof_rf_history) if oof_rf_history else np.array([]),
                "XGBoost_Regularized": np.concatenate(oof_xgb_history) if oof_xgb_history else np.array([]),
                "targets": np.concatenate(oof_y_history) if oof_y_history else np.array([]),
            },
        }

    def evaluate_holdout(
        self,
        df: pd.DataFrame,
        ensemble: Optional[WeightedAverageEnsemble] = None,
        accumulated_oof: Optional[Dict[str, np.ndarray]] = None,
    ) -> Dict[str, Any]:
        """Evaluate base models, candidate ensemble, and stacking on the untouched final holdout."""
        h_start, h_end, h_idx = self.splitter.get_holdout(df)
        clean_df = df.copy()
        clean_df["_parsed_date"] = clean_df[self.splitter.date_column].apply(parse_strict_date)

        h_start_ts = parse_strict_date(h_start)
        train_df = clean_df[clean_df["_parsed_date"] < h_start_ts].copy()
        holdout_df = clean_df.iloc[h_idx].copy()

        y_train = train_df["Waste_Weight_kg"].values
        y_holdout = holdout_df["Waste_Weight_kg"].values

        # Base mean
        mean_base = float(np.mean(y_train))
        p_mean = np.full_like(y_holdout, mean_base)

        # Feature pipeline fitted on full development period
        pipe = TemporalFeaturePipeline()
        pipe.fit(train_df)
        X_train = pipe.transform(train_df, is_training=True)
        pool = pd.concat([train_df, holdout_df], ignore_index=True)
        X_holdout = pipe.transform(holdout_df, is_training=False, historical_records=pool)

        # Fit RF on full development
        rf = RandomForestRegressor(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=5,
            random_state=self.random_state,
        )
        rf.fit(X_train, y_train)
        p_rf = rf.predict(X_holdout)

        # Fit XGB on full development
        xg = xgb.XGBRegressor(
            max_depth=2,
            learning_rate=0.05,
            n_estimators=100,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=1.0,
            random_state=self.random_state,
        )
        xg.fit(X_train, y_train)
        p_xgb = xg.predict(X_holdout)

        base_preds = {
            "Candidate_Temporal_RF": p_rf,
            "XGBoost_Regularized": p_xgb,
        }

        eval_models: Dict[str, np.ndarray] = {
            "Dummy_Mean": p_mean,
            "Candidate_Temporal_RF": p_rf,
            "XGBoost_Regularized": p_xgb,
            "Blend_50RF_50XGB": 0.50 * p_rf + 0.50 * p_xgb,
        }

        if ensemble is not None:
            eval_models["Candidate_Ensemble"] = ensemble.predict(base_preds, training_mean=mean_base)

        # Stacking on full dev OOF if provided
        if accumulated_oof is not None and len(accumulated_oof.get("targets", [])) > 0:
            meta = ChronologicalStackingMetaLearner(
                model_names=["Candidate_Temporal_RF", "XGBoost_Regularized"],
                alpha=10.0,
                positive=True,
            )
            meta.fit(
                oof_predictions=accumulated_oof,
                targets=accumulated_oof["targets"],
            )
            eval_models["Ridge_Stacking"] = meta.predict(base_preds)

        results: Dict[str, Dict[str, float]] = {}
        for name, preds in eval_models.items():
            ev = evaluate_regression(y_holdout, preds)
            results[name] = {
                "mae": ev.mae,
                "rmse": ev.rmse,
                "r2": ev.r2,
                "abs_diff_vs_mean": float(ev.mae - evaluate_regression(y_holdout, p_mean).mae),
                "pct_diff_vs_mean": float(((ev.mae - evaluate_regression(y_holdout, p_mean).mae) / evaluate_regression(y_holdout, p_mean).mae) * 100.0),
            }

        return {
            "holdout_dates": f"{h_start} to {h_end}",
            "holdout_samples": len(y_holdout),
            "results": results,
        }
