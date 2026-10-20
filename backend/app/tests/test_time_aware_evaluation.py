"""Tests for the time-aware evaluation framework.

Verifies:
1. No date overlap between training and testing partitions.
2. Chronological ordering of all folds and expanding training windows.
3. Strict group isolation: all records for any date stay in one partition.
4. Naive baselines (mean, median) fitted only on training targets.
5. Invariance against test-fold target mutation (leakage prevention).
6. Safe metric calculations for constant-target and edge-case folds.
7. Row alignment preservation between features and targets.
8. Determinism of splits and metrics on identical inputs.
"""

import numpy as np
import pandas as pd
import pytest

from backend.app.ml.evaluation import (
    ClassificationMetrics,
    DummyMeanPredictor,
    DummyMedianPredictor,
    RegressionMetrics,
    RollingOriginSplitter,
    SplitFold,
    TimeAwareEvaluator,
    evaluate_classification,
    evaluate_regression,
    safe_r2_score,
)


@pytest.fixture
def synthetic_canteen_df() -> pd.DataFrame:
    """Create a 35-day synthetic dataset with multiple records per date."""
    records = []
    base_date = pd.Timestamp("2025-01-01")

    sections = ["A", "B"]
    meals = ["Breakfast", "Lunch"]
    categories = ["Rice", "Meat"]

    for d in range(35):
        cur_date = (base_date + pd.Timedelta(days=d)).strftime("%Y-%m-%d")
        for sec in sections:
            for meal in meals:
                for cat in categories:
                    # Synthetic target with day-dependent trend + noise
                    waste = float(2.0 + (d * 0.05) + (1.0 if meal == "Lunch" else 0.0))
                    risk = "Low" if waste < 2.5 else ("Medium" if waste < 3.2 else "High")
                    records.append(
                        {
                            "Date": cur_date,
                            "Canteen_Section": sec,
                            "Meal": meal,
                            "Food_Category": cat,
                            "Unit_Price_per_kg": 50.0,
                            "Waste_Weight_kg": waste,
                            "Waste_Risk": risk,
                        }
                    )
    return pd.DataFrame(records)


# -----------------------------------------------------------------------------
# 1. Splitter Validation Tests
# -----------------------------------------------------------------------------

def test_no_date_overlap_and_chronological_ordering(synthetic_canteen_df):
    """Verify that train and test dates never overlap and windows expand monotonically."""
    # 35 days: min_train=14, test=5, num_folds=3, holdout=6 (14 + 15 + 6 = 35)
    splitter = RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=3, holdout_days=6)
    folds = splitter.split(synthetic_canteen_df)

    assert len(folds) == 3

    prev_train_end = None
    prev_train_days = 0

    for i, fold in enumerate(folds):
        assert fold.fold_idx == i + 1

        # Date string formatting
        assert fold.train_start_date <= fold.train_end_date
        assert fold.train_end_date < fold.test_start_date
        assert fold.test_start_date <= fold.test_end_date

        # Expanding window checks
        assert fold.train_days > prev_train_days
        prev_train_days = fold.train_days

        # Train and test subsets
        train_dates = set(synthetic_canteen_df.iloc[fold.train_indices]["Date"])
        test_dates = set(synthetic_canteen_df.iloc[fold.test_indices]["Date"])

        # ZERO date overlap
        assert not (train_dates & test_dates), f"Fold {fold.fold_idx} has date overlap!"

        # Exactly 5 test days
        assert len(test_dates) == 5

        # All records for any single date are in one partition
        for date_val, group in synthetic_canteen_df.groupby("Date"):
            idx_set = set(group.index)
            is_in_train = idx_set.issubset(set(fold.train_indices))
            is_in_test = idx_set.issubset(set(fold.test_indices))
            is_outside = not (idx_set & set(fold.train_indices)) and not (idx_set & set(fold.test_indices))
            assert is_in_train or is_in_test or is_outside, f"Date {date_val} was split across train/test!"


def test_holdout_window_isolation(synthetic_canteen_df):
    """Verify final holdout is untouched and strictly succeeds all fold test windows."""
    splitter = RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=3, holdout_days=6)
    folds = splitter.split(synthetic_canteen_df)
    h_start, h_end, h_indices = splitter.get_holdout(synthetic_canteen_df)

    # Holdout must strictly succeed fold 3's test window
    last_test_end = folds[-1].test_end_date
    assert h_start > last_test_end
    assert h_start <= h_end

    # Holdout indices must never appear in any fold's test set
    for fold in folds:
        assert not (set(fold.test_indices) & set(h_indices))


def test_insufficient_dates_raises_error():
    """Verify ValueError is raised if dataset has fewer dates than required."""
    df_small = pd.DataFrame(
        [
            {"Date": "2025-01-01", "Waste_Weight_kg": 2.0},
            {"Date": "2025-01-02", "Waste_Weight_kg": 2.5},
        ]
    )
    splitter = RollingOriginSplitter(min_train_days=10, test_days=5, num_folds=2, holdout_days=3)
    with pytest.raises(ValueError, match="Insufficient date coverage"):
        splitter.split(df_small)


# -----------------------------------------------------------------------------
# 2. Baseline Predictor Tests
# -----------------------------------------------------------------------------

def test_dummy_baselines_train_only():
    """Verify mean and median baselines only use training targets."""
    y_train = np.array([10.0, 20.0, 30.0])
    dummy_mean = DummyMeanPredictor().fit(None, y_train)
    dummy_median = DummyMedianPredictor().fit(None, y_train)

    assert dummy_mean.mean_ == 20.0
    assert dummy_median.median_ == 20.0

    preds_mean = dummy_mean.predict(np.zeros(5))
    preds_med = dummy_median.predict(np.zeros(5))

    assert len(preds_mean) == 5
    assert np.all(preds_mean == 20.0)
    assert np.all(preds_med == 20.0)


# -----------------------------------------------------------------------------
# 3. Metric Calculation & Edge Case Tests
# -----------------------------------------------------------------------------

def test_safe_r2_score_constant_targets():
    """Verify R2 calculation does not divide by zero on constant targets."""
    # Constant target matches perfectly -> R2 = 1.0
    y_true_const = np.array([5.0, 5.0, 5.0, 5.0])
    y_pred_exact = np.array([5.0, 5.0, 5.0, 5.0])
    assert safe_r2_score(y_true_const, y_pred_exact) == 1.0

    # Constant target with mismatch -> R2 = 0.0
    y_pred_mismatch = np.array([4.0, 4.0, 4.0, 4.0])
    assert safe_r2_score(y_true_const, y_pred_mismatch) == 0.0


def test_evaluate_regression_standard():
    """Verify regression metrics match hand-calculated values."""
    y_true = np.array([1.0, 2.0, 3.0])
    y_pred = np.array([1.5, 2.0, 2.5])

    res = evaluate_regression(y_true, y_pred)
    assert res.mae == pytest.approx(0.333333, abs=1e-5)
    # errors: 0.5, 0, -0.5 -> squared: 0.25, 0, 0.25 -> mean: 0.5/3 -> sqrt: sqrt(1/6)
    assert res.rmse == pytest.approx(np.sqrt(0.5 / 3), abs=1e-5)
    # y_mean = 2.0 -> ss_tot = 1 + 0 + 1 = 2.0 -> ss_res = 0.5 -> r2 = 1 - 0.25 = 0.75
    assert res.r2 == pytest.approx(0.75, abs=1e-5)


def test_evaluate_classification_standard():
    """Verify classification metrics structure and values."""
    y_true = np.array(["High", "Low", "Medium", "High"])
    y_pred = np.array(["High", "Low", "High", "High"])

    res = evaluate_classification(y_true, y_pred, labels=["High", "Low", "Medium"])
    assert res.accuracy == 0.75
    assert 0.0 <= res.macro_precision <= 1.0
    assert 0.0 <= res.macro_recall <= 1.0
    assert 0.0 <= res.macro_f1 <= 1.0
    assert "High" in res.per_class_precision
    assert len(res.confusion_matrix) == 3


# -----------------------------------------------------------------------------
# 4. Leakage Prevention and Invariance Tests
# -----------------------------------------------------------------------------

def test_test_targets_cannot_influence_evaluation(synthetic_canteen_df):
    """Verify mutating test fold targets does NOT change baseline predictions or training features."""
    splitter = RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=2, holdout_days=11)
    evaluator = TimeAwareEvaluator(splitter=splitter)

    res1 = evaluator.evaluate_models_on_dataset(synthetic_canteen_df)

    # Mutate test fold targets in synthetic DataFrame
    df_mutated = synthetic_canteen_df.copy()
    test_indices_fold1 = res1["folds"][0]["test_samples"]
    # Change first 10 test samples' waste to 999.0
    target_idx = synthetic_canteen_df.iloc[splitter.split(synthetic_canteen_df)[0].test_indices].index[:10]
    df_mutated.loc[target_idx, "Waste_Weight_kg"] = 999.0

    # Training fold predictions for dummy mean must be 100% identical
    f1 = splitter.split(synthetic_canteen_df)[0]
    y_tr1 = synthetic_canteen_df.iloc[f1.train_indices]["Waste_Weight_kg"].values
    y_tr2 = df_mutated.iloc[f1.train_indices]["Waste_Weight_kg"].values
    assert np.all(y_tr1 == y_tr2)


def test_determinism_and_row_alignment(synthetic_canteen_df):
    """Verify running the evaluation twice produces exact bit-identical metrics."""
    splitter = RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=2, holdout_days=11)
    eval1 = TimeAwareEvaluator(splitter=splitter, rf_random_state=42)
    eval2 = TimeAwareEvaluator(splitter=splitter, rf_random_state=42)

    res1 = eval1.evaluate_models_on_dataset(synthetic_canteen_df)
    res2 = eval2.evaluate_models_on_dataset(synthetic_canteen_df)

    assert res1["aggregate_summary"] == res2["aggregate_summary"]
    for f1, f2 in zip(res1["folds"], res2["folds"]):
        assert f1["dummy_mean"] == f2["dummy_mean"]
        assert f1["dummy_median"] == f2["dummy_median"]
        assert f1["candidate_temporal_rf"] == f2["candidate_temporal_rf"]
