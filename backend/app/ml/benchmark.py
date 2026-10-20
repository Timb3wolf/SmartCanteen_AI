"""Benchmark orchestration and comparison framework for SmartCanteen AI.

Evaluates naive baselines, legacy Random Forest, candidate temporal Random Forest,
and regularized XGBoost models across chronological rolling-origin folds and final holdout.
"""

from dataclasses import dataclass, field
import datetime
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

import xgboost as xgb

from backend.app.ml.evaluation import (
    DummyMeanPredictor,
    DummyMedianPredictor,
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
class BenchmarkModelSpec:
    """Specification of a candidate model to benchmark."""

    name: str
    model_type: str  # "dummy_mean", "dummy_median", "random_forest", "xgboost", "legacy_rf"
    params: Dict[str, Any] = field(default_factory=dict)
    use_temporal_features: bool = True


@dataclass
class ModelFoldResult:
    """Evaluation result of a single model on a single fold."""

    mae: float
    rmse: float
    r2: float
    fit_time_sec: float
    abs_diff_vs_mean: float
    pct_diff_vs_mean: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "r2": self.r2,
            "fit_time_sec": self.fit_time_sec,
            "abs_diff_vs_mean": self.abs_diff_vs_mean,
            "pct_diff_vs_mean": self.pct_diff_vs_mean,
        }


@dataclass
class BenchmarkFoldRecord:
    """Container for all model results on a single chronological fold."""

    fold_idx: int
    train_dates: str
    test_dates: str
    train_samples: int
    test_samples: int
    results: Dict[str, ModelFoldResult]


class ModelBenchmarkRunner:
    """Executes leakage-free, chronological model benchmarks."""

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
        self.legacy_feature_columns = [
            "Unit_Price_per_kg",
            "Year",
            "Month",
            "Day",
            "DayOfWeek",
            "Meal_Dinner",
            "Meal_Lunch",
            "Canteen_Section_B",
            "Canteen_Section_C",
            "Canteen_Section_D",
            "Food_Category_Rice",
            "Food_Category_Soup",
            "Food_Category_Vegetables",
        ]

    def _prepare_legacy_features(self, df_subset: pd.DataFrame) -> pd.DataFrame:
        """Construct legacy 13-feature schema with drop_first=True."""
        df_in = df_subset.copy()
        encoded = pd.get_dummies(
            df_in,
            columns=["Meal", "Canteen_Section", "Food_Category"],
            drop_first=True,
        )
        return encoded.reindex(columns=self.legacy_feature_columns, fill_value=0)

    def get_default_models(self) -> List[BenchmarkModelSpec]:
        """Return standard candidate model specifications for Phase 3 benchmark."""
        return [
            BenchmarkModelSpec(name="Dummy_Mean", model_type="dummy_mean"),
            BenchmarkModelSpec(name="Dummy_Median", model_type="dummy_median"),
            BenchmarkModelSpec(
                name="Retrained_Legacy_RF",
                model_type="legacy_rf",
                params={"n_estimators": 100, "random_state": self.random_state},
                use_temporal_features=False,
            ),
            BenchmarkModelSpec(
                name="Candidate_Temporal_RF",
                model_type="random_forest",
                params={
                    "n_estimators": 100,
                    "max_depth": 5,
                    "min_samples_leaf": 5,
                    "random_state": self.random_state,
                },
                use_temporal_features=True,
            ),
            BenchmarkModelSpec(
                name="XGBoost_Regularized",
                model_type="xgboost",
                params={
                    "max_depth": 2,
                    "learning_rate": 0.05,
                    "n_estimators": 100,
                    "subsample": 0.8,
                    "colsample_bytree": 0.8,
                    "reg_alpha": 0.1,
                    "reg_lambda": 1.0,
                    "random_state": self.random_state,
                },
                use_temporal_features=True,
            ),
            BenchmarkModelSpec(
                name="XGBoost_Depth3",
                model_type="xgboost",
                params={
                    "max_depth": 3,
                    "learning_rate": 0.03,
                    "n_estimators": 100,
                    "subsample": 0.8,
                    "colsample_bytree": 0.8,
                    "reg_alpha": 0.5,
                    "reg_lambda": 2.0,
                    "random_state": self.random_state,
                },
                use_temporal_features=True,
            ),
        ]

    def run_development_benchmark(
        self,
        df: pd.DataFrame,
        models: Optional[List[BenchmarkModelSpec]] = None,
    ) -> Dict[str, Any]:
        """Evaluate candidate models across the 4 chronological development folds."""
        specs = models or self.get_default_models()
        folds = self.splitter.split(df)
        if not folds:
            raise ValueError("Splitter generated 0 folds.")

        fold_records: List[BenchmarkFoldRecord] = []

        for fold in folds:
            train_df = df.iloc[fold.train_indices].copy()
            test_df = df.iloc[fold.test_indices].copy()

            y_train = train_df["Waste_Weight_kg"].values
            y_test = test_df["Waste_Weight_kg"].values

            # Pre-compute features
            # A. Phase 1 Temporal features
            pipe = TemporalFeaturePipeline()
            pipe.fit(train_df)
            X_train_temporal = pipe.transform(train_df, is_training=True)
            history_pool = pd.concat([train_df, test_df], ignore_index=True)
            X_test_temporal = pipe.transform(
                test_df,
                is_training=False,
                historical_records=history_pool,
            )

            # B. Legacy 13 features
            X_train_legacy = self._prepare_legacy_features(train_df)
            X_test_legacy = self._prepare_legacy_features(test_df)

            # 1. Compute baseline mean MAE for comparison delta
            mean_baseline_val = float(np.mean(y_train))
            baseline_mae = float(mean_absolute_error(y_test, np.full_like(y_test, mean_baseline_val)))

            fold_model_results: Dict[str, ModelFoldResult] = {}

            for spec in specs:
                t0 = time.time()
                if spec.model_type == "dummy_mean":
                    preds = np.full_like(y_test, mean_baseline_val)
                    fit_dur = time.time() - t0
                elif spec.model_type == "dummy_median":
                    med_val = float(np.median(y_train))
                    preds = np.full_like(y_test, med_val)
                    fit_dur = time.time() - t0
                elif spec.model_type == "legacy_rf":
                    model = RandomForestRegressor(**spec.params)
                    model.fit(X_train_legacy, y_train)
                    fit_dur = time.time() - t0
                    preds = model.predict(X_test_legacy)
                elif spec.model_type == "random_forest":
                    model = RandomForestRegressor(**spec.params)
                    model.fit(X_train_temporal, y_train)
                    fit_dur = time.time() - t0
                    preds = model.predict(X_test_temporal)
                elif spec.model_type == "xgboost":
                    model = xgb.XGBRegressor(**spec.params)
                    model.fit(X_train_temporal, y_train)
                    fit_dur = time.time() - t0
                    preds = model.predict(X_test_temporal)
                else:
                    raise ValueError(f"Unknown model type: {spec.model_type}")

                mae = float(mean_absolute_error(y_test, preds))
                rmse = float(root_mean_squared_error(y_test, preds))
                r2 = safe_r2_score(y_test, preds)

                abs_diff = mae - baseline_mae
                pct_diff = (abs_diff / baseline_mae) * 100.0 if baseline_mae > 0 else 0.0

                fold_model_results[spec.name] = ModelFoldResult(
                    mae=mae,
                    rmse=rmse,
                    r2=r2,
                    fit_time_sec=fit_dur,
                    abs_diff_vs_mean=abs_diff,
                    pct_diff_vs_mean=pct_diff,
                )

            fold_records.append(
                BenchmarkFoldRecord(
                    fold_idx=fold.fold_idx,
                    train_dates=f"{fold.train_start_date} to {fold.train_end_date}",
                    test_dates=f"{fold.test_start_date} to {fold.test_end_date}",
                    train_samples=fold.train_count,
                    test_samples=fold.test_count,
                    results=fold_model_results,
                )
            )

        # Compute aggregate performance across folds
        summary = self._compute_summary(fold_records, [s.name for s in specs])

        h_start, h_end, h_idx = self.splitter.get_holdout(df)
        holdout_info = {
            "dates": f"{h_start} to {h_end}",
            "sample_count": len(h_idx),
            "status": "Untouched (Evaluated only after candidate selection)",
        }

        return {
            "folds": [
                {
                    "fold_idx": f.fold_idx,
                    "train_dates": f.train_dates,
                    "test_dates": f.test_dates,
                    "train_samples": f.train_samples,
                    "test_samples": f.test_samples,
                    "models": {k: v.to_dict() for k, v in f.results.items()},
                }
                for f in fold_records
            ],
            "aggregate_summary": summary,
            "holdout_info": holdout_info,
        }

    def _compute_summary(
        self,
        folds: List[BenchmarkFoldRecord],
        model_names: List[str],
    ) -> Dict[str, Dict[str, float]]:
        """Calculate mean and std of metrics across folds."""
        summary: Dict[str, Dict[str, float]] = {}

        for name in model_names:
            maes = [f.results[name].mae for f in folds]
            rmses = [f.results[name].rmse for f in folds]
            r2s = [f.results[name].r2 for f in folds]
            times = [f.results[name].fit_time_sec for f in folds]
            diffs = [f.results[name].abs_diff_vs_mean for f in folds]
            pcts = [f.results[name].pct_diff_vs_mean for f in folds]

            summary[name] = {
                "mean_mae": float(np.mean(maes)),
                "std_mae": float(np.std(maes, ddof=1)) if len(maes) > 1 else 0.0,
                "mean_rmse": float(np.mean(rmses)),
                "std_rmse": float(np.std(rmses, ddof=1)) if len(rmses) > 1 else 0.0,
                "mean_r2": float(np.mean(r2s)),
                "std_r2": float(np.std(r2s, ddof=1)) if len(r2s) > 1 else 0.0,
                "mean_fit_time_sec": float(np.mean(times)),
                "mean_abs_diff_vs_mean": float(np.mean(diffs)),
                "mean_pct_diff_vs_mean": float(np.mean(pcts)),
            }

        return summary

    def evaluate_holdout(
        self,
        df: pd.DataFrame,
        selected_model: BenchmarkModelSpec,
    ) -> Dict[str, Any]:
        """Evaluate the selected candidate against the baseline on the untouched final holdout."""
        h_start, h_end, h_idx = self.splitter.get_holdout(df)

        clean_df = df.copy()
        clean_df["_parsed_date"] = clean_df[self.splitter.date_column].apply(parse_strict_date)

        # Train set is all data strictly before holdout start date
        h_start_ts = parse_strict_date(h_start)
        train_df = clean_df[clean_df["_parsed_date"] < h_start_ts].copy()
        holdout_df = clean_df.iloc[h_idx].copy()

        y_train = train_df["Waste_Weight_kg"].values
        y_holdout = holdout_df["Waste_Weight_kg"].values

        # 1. Baseline
        mean_base = float(np.mean(y_train))
        med_base = float(np.median(y_train))
        y_pred_mean = np.full_like(y_holdout, mean_base)
        y_pred_med = np.full_like(y_holdout, med_base)

        res_mean = evaluate_regression(y_holdout, y_pred_mean)
        res_med = evaluate_regression(y_holdout, y_pred_med)

        # 2. Selected model
        pipe = TemporalFeaturePipeline()
        pipe.fit(train_df)
        X_train = pipe.transform(train_df, is_training=True)

        full_pool = pd.concat([train_df, holdout_df], ignore_index=True)
        X_holdout = pipe.transform(holdout_df, is_training=False, historical_records=full_pool)

        t0 = time.time()
        if selected_model.model_type == "random_forest":
            model = RandomForestRegressor(**selected_model.params)
        elif selected_model.model_type == "xgboost":
            model = xgb.XGBRegressor(**selected_model.params)
        else:
            raise ValueError(f"Unsupported model type for holdout: {selected_model.model_type}")

        model.fit(X_train, y_train)
        fit_dur = time.time() - t0
        y_pred_cand = model.predict(X_holdout)

        res_cand = evaluate_regression(y_holdout, y_pred_cand)

        abs_diff = res_cand.mae - res_mean.mae
        pct_diff = (abs_diff / res_mean.mae) * 100.0 if res_mean.mae > 0 else 0.0

        return {
            "holdout_dates": f"{h_start} to {h_end}",
            "train_samples": len(train_df),
            "holdout_samples": len(holdout_df),
            "selected_model_name": selected_model.name,
            "dummy_mean": res_mean.to_dict(),
            "dummy_median": res_med.to_dict(),
            "selected_candidate": {
                **res_cand.to_dict(),
                "fit_time_sec": fit_dur,
                "abs_diff_vs_mean": abs_diff,
                "pct_diff_vs_mean": pct_diff,
            },
        }
