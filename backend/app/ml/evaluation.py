"""Time-Aware Evaluation Framework for SmartCanteen AI.

Provides:
- Date-grouped, rolling-origin chronological splitting with expanding training windows.
- Strict prevention of train/test leakage and date cross-contamination.
- Zero-leakage daily rolling forecast protocol and frozen-origin multi-day protocol.
- Naive empirical baselines (Training Mean, Training Median).
- Retrained and candidate Random Forest models with fold-isolated preprocessing.
- Performance aggregation, variability tracking, and classification evaluation.
"""

from dataclasses import dataclass, field
import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    precision_score,
    recall_score,
    root_mean_squared_error,
)

from backend.app.ml.features import (
    TemporalFeatureConfig,
    TemporalFeaturePipeline,
    parse_strict_date,
)


@dataclass
class SplitFold:
    """Represents a single chronological train/test split fold."""

    fold_idx: int
    train_start_date: str
    train_end_date: str
    test_start_date: str
    test_end_date: str
    train_days: int
    test_days: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_count: int
    test_count: int


@dataclass
class RegressionMetrics:
    """Container for regression evaluation metrics."""

    mae: float
    rmse: float
    r2: float

    def to_dict(self) -> Dict[str, float]:
        return {"mae": self.mae, "rmse": self.rmse, "r2": self.r2}


@dataclass
class ClassificationMetrics:
    """Container for classification evaluation metrics."""

    accuracy: float
    macro_precision: float
    macro_recall: float
    macro_f1: float
    per_class_precision: Dict[str, float]
    per_class_recall: Dict[str, float]
    per_class_f1: Dict[str, float]
    confusion_matrix: List[List[int]]
    class_distribution: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy": self.accuracy,
            "macro_precision": self.macro_precision,
            "macro_recall": self.macro_recall,
            "macro_f1": self.macro_f1,
            "per_class_precision": self.per_class_precision,
            "per_class_recall": self.per_class_recall,
            "per_class_f1": self.per_class_f1,
            "confusion_matrix": self.confusion_matrix,
            "class_distribution": self.class_distribution,
        }


def safe_r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Compute R2 score safely, handling zero-variance or constant target edge cases."""
    if len(y_true) == 0:
        return 0.0

    ss_res = float(np.sum((y_true - y_pred) ** 2))
    y_mean = float(np.mean(y_true))
    ss_tot = float(np.sum((y_true - y_mean) ** 2))

    if ss_tot == 0.0:
        # If all true targets are constant:
        # Perfect match -> 1.0, otherwise 0.0
        return 1.0 if ss_res == 0.0 else 0.0

    return float(1.0 - (ss_res / ss_tot))


def evaluate_regression(y_true: np.ndarray, y_pred: np.ndarray) -> RegressionMetrics:
    """Calculate MAE, RMSE, and safe R2."""
    mae = float(mean_absolute_error(y_true, y_pred))
    rmse = float(root_mean_squared_error(y_true, y_pred))
    r2 = safe_r2_score(y_true, y_pred)
    return RegressionMetrics(mae=mae, rmse=rmse, r2=r2)


def evaluate_classification(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    labels: Optional[List[str]] = None,
) -> ClassificationMetrics:
    """Calculate multiclass accuracy, macro/per-class precision, recall, F1, and confusion matrix."""
    if labels is None:
        labels = ["High", "Low", "Medium"]

    acc = float(accuracy_score(y_true, y_pred))
    prec = float(precision_score(y_true, y_pred, average="macro", zero_division=0))
    rec = float(recall_score(y_true, y_pred, average="macro", zero_division=0))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))

    per_prec = precision_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    per_rec = recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    per_f1 = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)

    per_class_p = {lbl: float(p) for lbl, p in zip(labels, per_prec)}
    per_class_r = {lbl: float(r) for lbl, r in zip(labels, per_rec)}
    per_class_f = {lbl: float(f) for lbl, f in zip(labels, per_f1)}

    cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()

    # True class distribution
    unique_vals, counts = np.unique(y_true, return_counts=True)
    class_dist = {str(k): int(v) for k, v in zip(unique_vals, counts)}

    return ClassificationMetrics(
        accuracy=acc,
        macro_precision=prec,
        macro_recall=rec,
        macro_f1=f1,
        per_class_precision=per_class_p,
        per_class_recall=per_class_r,
        per_class_f1=per_class_f,
        confusion_matrix=cm,
        class_distribution=class_dist,
    )


class DummyMeanPredictor:
    """Naive baseline predicting the training-fold mean target."""

    def __init__(self) -> None:
        self.mean_: float = 0.0

    def fit(self, X: Any, y: np.ndarray) -> "DummyMeanPredictor":
        self.mean_ = float(np.mean(y))
        return self

    def predict(self, X: Any) -> np.ndarray:
        n_samples = len(X) if hasattr(X, "__len__") else 1
        return np.full(n_samples, self.mean_, dtype=float)


class DummyMedianPredictor:
    """Naive baseline predicting the training-fold median target."""

    def __init__(self) -> None:
        self.median_: float = 0.0

    def fit(self, X: Any, y: np.ndarray) -> "DummyMedianPredictor":
        self.median_ = float(np.median(y))
        return self

    def predict(self, X: Any) -> np.ndarray:
        n_samples = len(X) if hasattr(X, "__len__") else 1
        return np.full(n_samples, self.median_, dtype=float)


class RollingOriginSplitter:
    """Constructs date-grouped, non-overlapping chronological rolling-origin folds.

    Guarantees:
    - Every record for a single calendar date belongs 100% to either training or testing.
    - Zero date overlap between training and testing partitions.
    - Chronologically monotonic expanding training windows.
    - Consecutive test windows following training cutoffs.
    - Final holdout window remains untouched for downstream validation.
    """

    def __init__(
        self,
        min_train_days: int = 26,
        test_days: int = 7,
        num_folds: int = 4,
        holdout_days: int = 7,
        date_column: str = "Date",
    ) -> None:
        self.min_train_days = min_train_days
        self.test_days = test_days
        self.num_folds = num_folds
        self.holdout_days = holdout_days
        self.date_column = date_column

    def split(self, df: pd.DataFrame) -> List[SplitFold]:
        """Generate rolling-origin folds from a DataFrame."""
        if df.empty:
            return []

        # Parse and sort unique calendar dates
        clean_df = df.copy()
        clean_df["_parsed_date"] = clean_df[self.date_column].apply(parse_strict_date)
        sorted_dates = sorted(clean_df["_parsed_date"].unique())
        total_dates = len(sorted_dates)

        required_days = self.min_train_days + (self.num_folds * self.test_days) + self.holdout_days
        if total_dates < required_days:
            raise ValueError(
                f"Insufficient date coverage: dataset has {total_dates} dates, but "
                f"{required_days} dates required ({self.min_train_days} min train + "
                f"{self.num_folds}x{self.test_days} test + {self.holdout_days} holdout)."
            )

        folds: List[SplitFold] = []

        for fold_i in range(self.num_folds):
            train_day_count = self.min_train_days + (fold_i * self.test_days)
            test_start_idx = train_day_count
            test_end_idx = test_start_idx + self.test_days

            train_dates = set(sorted_dates[:train_day_count])
            test_dates = set(sorted_dates[test_start_idx:test_end_idx])

            # Zero overlap check
            assert not (train_dates & test_dates), f"Fold {fold_i + 1} has train/test date overlap!"

            train_mask = clean_df["_parsed_date"].isin(train_dates)
            test_mask = clean_df["_parsed_date"].isin(test_dates)

            train_indices = clean_df.index[train_mask].to_numpy()
            test_indices = clean_df.index[test_mask].to_numpy()

            t_start = sorted_dates[0].strftime("%Y-%m-%d")
            t_end = sorted_dates[train_day_count - 1].strftime("%Y-%m-%d")
            v_start = sorted_dates[test_start_idx].strftime("%Y-%m-%d")
            v_end = sorted_dates[test_end_idx - 1].strftime("%Y-%m-%d")

            folds.append(
                SplitFold(
                    fold_idx=fold_i + 1,
                    train_start_date=t_start,
                    train_end_date=t_end,
                    test_start_date=v_start,
                    test_end_date=v_end,
                    train_days=train_day_count,
                    test_days=self.test_days,
                    train_indices=train_indices,
                    test_indices=test_indices,
                    train_count=len(train_indices),
                    test_count=len(test_indices),
                )
            )

        return folds

    def get_holdout(self, df: pd.DataFrame) -> Tuple[str, str, np.ndarray]:
        """Extract the untouched final holdout dates and indices."""
        clean_df = df.copy()
        clean_df["_parsed_date"] = clean_df[self.date_column].apply(parse_strict_date)
        sorted_dates = sorted(clean_df["_parsed_date"].unique())

        holdout_start_idx = self.min_train_days + (self.num_folds * self.test_days)
        holdout_dates = set(sorted_dates[holdout_start_idx:])

        mask = clean_df["_parsed_date"].isin(holdout_dates)
        indices = clean_df.index[mask].to_numpy()

        h_start = sorted_dates[holdout_start_idx].strftime("%Y-%m-%d")
        h_end = sorted_dates[-1].strftime("%Y-%m-%d")
        return h_start, h_end, indices


class TimeAwareEvaluator:
    """Executes time-aware rolling-origin evaluation of regression and classification models."""

    def __init__(
        self,
        splitter: Optional[RollingOriginSplitter] = None,
        forecast_protocol: str = "daily_rolling",
        rf_random_state: int = 42,
    ) -> None:
        self.splitter = splitter or RollingOriginSplitter()
        self.forecast_protocol = forecast_protocol  # "daily_rolling" or "frozen_origin"
        self.rf_random_state = rf_random_state

    def _prepare_legacy_features(
        self,
        df_subset: pd.DataFrame,
        feature_columns: List[str],
    ) -> pd.DataFrame:
        """Construct legacy 13-feature DataFrame matching production models."""
        df_in = df_subset.copy()
        encoded = pd.get_dummies(
            df_in,
            columns=["Meal", "Canteen_Section", "Food_Category"],
            drop_first=True,
        )
        return encoded.reindex(columns=feature_columns, fill_value=0)

    def evaluate_models_on_dataset(
        self,
        df: pd.DataFrame,
        prod_reg_model: Optional[Any] = None,
        prod_clf_model: Optional[Any] = None,
        legacy_reg_features: Optional[List[str]] = None,
        legacy_clf_features: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute complete cross-model evaluation across all rolling-origin folds."""
        folds = self.splitter.split(df)
        if not folds:
            raise ValueError("Splitter generated 0 folds.")

        results_by_fold: List[Dict[str, Any]] = []

        for fold in folds:
            train_df = df.iloc[fold.train_indices].copy()
            test_df = df.iloc[fold.test_indices].copy()

            y_train = train_df["Waste_Weight_kg"].values
            y_test = test_df["Waste_Weight_kg"].values
            y_train_risk = train_df["Waste_Risk"].values
            y_test_risk = test_df["Waste_Risk"].values

            fold_record: Dict[str, Any] = {
                "fold": fold.fold_idx,
                "train_dates": f"{fold.train_start_date} to {fold.train_end_date}",
                "test_dates": f"{fold.test_start_date} to {fold.test_end_date}",
                "train_samples": fold.train_count,
                "test_samples": fold.test_count,
            }

            # -------------------------------------------------------------
            # 1. Naive Baselines
            # -------------------------------------------------------------
            mean_pred = DummyMeanPredictor().fit(None, y_train).predict(test_df)
            med_pred = DummyMedianPredictor().fit(None, y_train).predict(test_df)

            fold_record["dummy_mean"] = evaluate_regression(y_test, mean_pred).to_dict()
            fold_record["dummy_median"] = evaluate_regression(y_test, med_pred).to_dict()

            # -------------------------------------------------------------
            # 2. Retrained Legacy RF (Fitted strictly on train fold)
            # -------------------------------------------------------------
            if legacy_reg_features:
                X_train_leg = self._prepare_legacy_features(train_df, legacy_reg_features)
                X_test_leg = self._prepare_legacy_features(test_df, legacy_reg_features)

                rf_leg = RandomForestRegressor(
                    n_estimators=100,
                    random_state=self.rf_random_state,
                )
                rf_leg.fit(X_train_leg, y_train)
                y_pred_leg = rf_leg.predict(X_test_leg)
                fold_record["retrained_legacy_rf"] = evaluate_regression(y_test, y_pred_leg).to_dict()

                if legacy_clf_features:
                    clf_leg = RandomForestClassifier(
                        n_estimators=100,
                        random_state=self.rf_random_state,
                    )
                    clf_leg.fit(X_train_leg, y_train_risk)
                    y_pred_clf_leg = clf_leg.predict(X_test_leg)
                    fold_record["retrained_legacy_classifier"] = evaluate_classification(
                        y_test_risk, y_pred_clf_leg
                    ).to_dict()

            # -------------------------------------------------------------
            # 3. Candidate RF with Phase 1 Temporal Features
            # -------------------------------------------------------------
            pipe = TemporalFeaturePipeline()
            pipe.fit(train_df)

            X_train_cand = pipe.transform(train_df, is_training=True)

            if self.forecast_protocol == "daily_rolling":
                # Historical updates permitted as test dates progress: Date < current_pred_date
                history_pool = pd.concat([train_df, test_df], ignore_index=True)
                X_test_cand = pipe.transform(
                    test_df,
                    is_training=False,
                    historical_records=history_pool,
                )
            else:
                # Frozen origin: only pre-test history available
                X_test_cand = pipe.transform(
                    test_df,
                    is_training=False,
                    historical_records=train_df,
                )

            # Fit candidate regularized Random Forest
            cand_rf = RandomForestRegressor(
                n_estimators=100,
                max_depth=5,
                min_samples_leaf=5,
                random_state=self.rf_random_state,
            )
            cand_rf.fit(X_train_cand, y_train)
            y_pred_cand = cand_rf.predict(X_test_cand)
            fold_record["candidate_temporal_rf"] = evaluate_regression(y_test, y_pred_cand).to_dict()

            # -------------------------------------------------------------
            # 4. Production Models (Fixed pre-trained checkpoints)
            # -------------------------------------------------------------
            if prod_reg_model is not None and legacy_reg_features:
                X_test_prod_reg = self._prepare_legacy_features(test_df, legacy_reg_features)
                y_pred_prod_reg = prod_reg_model.predict(X_test_prod_reg)
                fold_record["production_rf_fixed"] = evaluate_regression(y_test, y_pred_prod_reg).to_dict()

            if prod_clf_model is not None and legacy_clf_features:
                X_test_prod_clf = self._prepare_legacy_features(test_df, legacy_clf_features)
                y_pred_prod_clf = prod_clf_model.predict(X_test_prod_clf)
                fold_record["production_classifier_fixed"] = evaluate_classification(
                    y_test_risk, y_pred_prod_clf
                ).to_dict()

            results_by_fold.append(fold_record)

        # -----------------------------------------------------------------
        # Compute Aggregate Summary across folds (Mean & Std)
        # -----------------------------------------------------------------
        summary = self._compute_aggregate_summary(results_by_fold)

        h_start, h_end, h_indices = self.splitter.get_holdout(df)
        holdout_info = {
            "dates": f"{h_start} to {h_end}",
            "sample_count": len(h_indices),
            "status": "Untouched (Reserved for Phase 3)",
        }

        return {
            "folds": results_by_fold,
            "aggregate_summary": summary,
            "final_holdout": holdout_info,
            "forecast_protocol": self.forecast_protocol,
        }

    def _compute_aggregate_summary(
        self,
        folds: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """Calculate mean and standard deviation of metrics across folds."""
        models = [
            "dummy_mean",
            "dummy_median",
            "candidate_temporal_rf",
            "retrained_legacy_rf",
            "production_rf_fixed",
        ]

        summary: Dict[str, Dict[str, float]] = {}

        for m in models:
            if m not in folds[0]:
                continue
            maes = [f[m]["mae"] for f in folds]
            rmses = [f[m]["rmse"] for f in folds]
            r2s = [f[m]["r2"] for f in folds]

            summary[m] = {
                "mean_mae": float(np.mean(maes)),
                "std_mae": float(np.std(maes, ddof=1)) if len(maes) > 1 else 0.0,
                "mean_rmse": float(np.mean(rmses)),
                "std_rmse": float(np.std(rmses, ddof=1)) if len(rmses) > 1 else 0.0,
                "mean_r2": float(np.mean(r2s)),
                "std_r2": float(np.std(r2s, ddof=1)) if len(r2s) > 1 else 0.0,
            }

        # Classifier summaries if present
        clf_models = ["retrained_legacy_classifier", "production_classifier_fixed"]
        for cm in clf_models:
            if cm not in folds[0]:
                continue
            accs = [f[cm]["accuracy"] for f in folds]
            f1s = [f[cm]["macro_f1"] for f in folds]

            summary[cm] = {
                "mean_accuracy": float(np.mean(accs)),
                "std_accuracy": float(np.std(accs, ddof=1)) if len(accs) > 1 else 0.0,
                "mean_macro_f1": float(np.mean(f1s)),
                "std_macro_f1": float(np.std(f1s, ddof=1)) if len(f1s) > 1 else 0.0,
            }

        return summary
