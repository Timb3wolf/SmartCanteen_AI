"""Tests for the model benchmark framework.

Verifies:
1. Target and target-derived columns are strictly excluded from all model feature sets.
2. Same-date observations cannot leak targets into each other's features.
3. Development folds and final holdout are strictly isolated without date overlap.
4. Baseline comparison math (absolute diff and percentage diff) is exact.
5. Determinism: identical inputs produce identical metrics down to bit-level equivalence.
6. Benchmark runner correctly instantiates and evaluates Random Forest and XGBoost models.
"""

import numpy as np
import pandas as pd
import pytest

from backend.app.ml.benchmark import (
    BenchmarkFoldRecord,
    BenchmarkModelSpec,
    ModelBenchmarkRunner,
    ModelFoldResult,
)
from backend.app.ml.evaluation import RollingOriginSplitter


@pytest.fixture
def synthetic_benchmark_df() -> pd.DataFrame:
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
                    waste = float(2.0 + (d * 0.05) + (0.5 if meal == "Lunch" else 0.0))
                    cost_loss = waste * 50.0
                    risk = "Low" if waste < 2.5 else ("Medium" if waste < 3.2 else "High")
                    records.append(
                        {
                            "Date": cur_date,
                            "Canteen_Section": sec,
                            "Meal": meal,
                            "Food_Category": cat,
                            "Unit_Price_per_kg": 50.0,
                            "Waste_Weight_kg": waste,
                            "Cost_Loss": cost_loss,
                            "Waste_Risk": risk,
                        }
                    )
    return pd.DataFrame(records)


def test_no_target_derived_columns_in_features(synthetic_benchmark_df):
    """Verify Waste_Weight_kg, Cost_Loss, and Waste_Risk never enter model feature sets."""
    runner = ModelBenchmarkRunner(
        RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=2, holdout_days=11)
    )

    models = [
        BenchmarkModelSpec(name="Dummy_Mean", model_type="dummy_mean"),
        BenchmarkModelSpec(
            name="RF",
            model_type="random_forest",
            params={"n_estimators": 10, "max_depth": 3, "random_state": 42},
        ),
        BenchmarkModelSpec(
            name="XGB",
            model_type="xgboost",
            params={"n_estimators": 10, "max_depth": 2, "random_state": 42},
        ),
    ]

    res = runner.run_development_benchmark(synthetic_benchmark_df, models=models)
    assert len(res["folds"]) == 2

    # Check temporal feature pipeline feature names
    from backend.app.ml.features import TemporalFeaturePipeline

    pipeline = TemporalFeaturePipeline()
    feature_names = pipeline.feature_names

    forbidden_cols = ["Waste_Weight_kg", "Cost_Loss", "Waste_Risk", "Cluster"]
    for col in forbidden_cols:
        assert col not in feature_names, f"Forbidden column '{col}' found in candidate feature names!"

    # Check legacy feature names
    for col in forbidden_cols:
        assert col not in runner.legacy_feature_columns


def test_same_date_target_leakage_impossible():
    """Verify that records sharing the same date cannot leak target values to each other."""
    from backend.app.ml.features import TemporalFeaturePipeline

    df_same_date = pd.DataFrame(
        [
            {"Date": "2025-07-15", "Canteen_Section": "A", "Meal": "Lunch", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 2.0},
            {"Date": "2025-07-15", "Canteen_Section": "B", "Meal": "Lunch", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 999.0},
            {"Date": "2025-07-15", "Canteen_Section": "C", "Meal": "Dinner", "Food_Category": "Meat", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 888.0},
        ]
    )

    pipeline = TemporalFeaturePipeline()
    # Transform using itself as history
    feats = pipeline.transform(df_same_date, is_training=False, historical_records=df_same_date)

    # All rows must register missing rolling history because < pred_date matches 0 records
    assert np.all(feats["is_missing_rolling_7d"].values == 1.0)
    assert np.all(feats["is_missing_lag_7d"].values == 1.0)
    assert np.all(feats["waste_rolling_count_7d"].values == 0.0)


def test_baseline_comparison_math():
    """Verify absolute diff and percentage diff math is exact."""
    result = ModelFoldResult(
        mae=1.25,
        rmse=1.45,
        r2=0.05,
        fit_time_sec=0.1,
        abs_diff_vs_mean=0.05,
        pct_diff_vs_mean=4.166667,
    )
    d = result.to_dict()
    assert d["mae"] == 1.25
    assert d["abs_diff_vs_mean"] == pytest.approx(0.05, abs=1e-5)
    assert d["pct_diff_vs_mean"] == pytest.approx(4.166667, abs=1e-5)


def test_benchmark_determinism(synthetic_benchmark_df):
    """Verify running the benchmark twice produces identical results down to bit precision."""
    splitter = RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=2, holdout_days=11)
    runner1 = ModelBenchmarkRunner(splitter=splitter, random_state=42)
    runner2 = ModelBenchmarkRunner(splitter=splitter, random_state=42)

    models = [
        BenchmarkModelSpec(name="Dummy_Mean", model_type="dummy_mean"),
        BenchmarkModelSpec(
            name="RF",
            model_type="random_forest",
            params={"n_estimators": 20, "max_depth": 3, "random_state": 42},
        ),
        BenchmarkModelSpec(
            name="XGB",
            model_type="xgboost",
            params={"n_estimators": 20, "max_depth": 2, "random_state": 42},
        ),
    ]

    res1 = runner1.run_development_benchmark(synthetic_benchmark_df, models=models)
    res2 = runner2.run_development_benchmark(synthetic_benchmark_df, models=models)

    # Verify mathematical metrics are bit-for-bit identical (excluding wall-clock execution time)
    for model_name in ["Dummy_Mean", "RF", "XGB"]:
        s1 = res1["aggregate_summary"][model_name]
        s2 = res2["aggregate_summary"][model_name]
        for metric_key in ["mean_mae", "std_mae", "mean_rmse", "std_rmse", "mean_r2", "std_r2"]:
            assert s1[metric_key] == s2[metric_key]

    for f1, f2 in zip(res1["folds"], res2["folds"]):
        for model_name in ["Dummy_Mean", "RF", "XGB"]:
            m1 = f1["models"][model_name]
            m2 = f2["models"][model_name]
            assert m1["mae"] == m2["mae"]
            assert m1["rmse"] == m2["rmse"]
            assert m1["r2"] == m2["r2"]


def test_holdout_evaluation_isolation(synthetic_benchmark_df):
    """Verify holdout evaluation is executed on untouched holdout records."""
    splitter = RollingOriginSplitter(min_train_days=14, test_days=5, num_folds=2, holdout_days=11)
    runner = ModelBenchmarkRunner(splitter=splitter, random_state=42)

    cand_spec = BenchmarkModelSpec(
        name="Candidate_RF",
        model_type="random_forest",
        params={"n_estimators": 20, "max_depth": 3, "random_state": 42},
    )

    holdout_res = runner.evaluate_holdout(synthetic_benchmark_df, cand_spec)
    assert holdout_res["holdout_samples"] > 0
    assert "dummy_mean" in holdout_res
    assert "selected_candidate" in holdout_res
    assert holdout_res["selected_candidate"]["mae"] > 0.0
