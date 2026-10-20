"""Tests for Phase 5: Target Validity and Data Readiness Audit.

Verifies:
- Target naming consistency and absence of 'Waste_Quantity_kg' alias confusion
- Mathematical relationship between Cost_Loss, Waste_Weight_kg, and Unit_Price_per_kg
- Verification that Waste_Risk is an exact tertile binning of Waste_Weight_kg
- Verification that target-derived columns (Cost_Loss, Waste_Risk, Cluster) are excluded from feature pipelines
- Temporal feature lookup information boundaries (strictly Date < pred_date)
- Unit of observation uniqueness across (Date, Meal, Canteen_Section, Food_Category)
"""

import math
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.features import (
    TemporalFeatureConfig,
    TemporalFeaturePipeline,
    parse_strict_date,
)
from backend.app.ml.evaluation import RollingOriginSplitter


@pytest.fixture(scope="module")
def raw_dataset() -> pd.DataFrame:
    """Load the raw 2,600-row SmartCanteen dataset."""
    return pd.read_csv("data/raw/SmartCanteen_Final_Dataset.csv")


# =========================================================================
# 1. Target Naming & Column Integrity Tests
# =========================================================================

def test_target_column_naming_consistency(raw_dataset: pd.DataFrame):
    """Verify raw target column is strictly 'Waste_Weight_kg' and not 'Waste_Quantity_kg'."""
    assert "Waste_Weight_kg" in raw_dataset.columns
    assert "Waste_Quantity_kg" not in raw_dataset.columns


def test_cost_loss_algebraic_consistency(raw_dataset: pd.DataFrame):
    """Verify Cost_Loss matches Waste_Weight_kg * Unit_Price_per_kg within 2-decimal rounding."""
    calculated = raw_dataset["Waste_Weight_kg"] * raw_dataset["Unit_Price_per_kg"]
    diff = (raw_dataset["Cost_Loss"] - calculated).abs()

    # Maximum allowed difference is 0.005 (due to floating point and standard half-up rounding)
    assert diff.max() <= 0.0051
    assert diff.mean() < 0.001


def test_waste_risk_is_exact_tertile_discretization(raw_dataset: pd.DataFrame):
    """Verify Waste_Risk is strictly an empirical tertile discretization of Waste_Weight_kg."""
    low_records = raw_dataset[raw_dataset["Waste_Risk"] == "Low"]["Waste_Weight_kg"]
    med_records = raw_dataset[raw_dataset["Waste_Risk"] == "Medium"]["Waste_Weight_kg"]
    high_records = raw_dataset[raw_dataset["Waste_Risk"] == "High"]["Waste_Weight_kg"]

    # Threshold boundaries
    assert low_records.max() <= 1.78
    assert med_records.min() >= 1.79
    assert med_records.max() <= 3.42
    assert high_records.min() >= 3.43

    # Tertile quantiles match boundaries
    q_33 = raw_dataset["Waste_Weight_kg"].quantile(1.0 / 3.0)
    q_66 = raw_dataset["Waste_Weight_kg"].quantile(2.0 / 3.0)
    assert math.isclose(q_33, 1.78, abs_tol=0.01)
    assert math.isclose(q_66, 3.42, abs_tol=0.01)


def test_target_derived_columns_excluded_from_features(raw_dataset: pd.DataFrame):
    """Verify Cost_Loss, Waste_Risk, and Cluster never enter the feature matrix."""
    pipeline = TemporalFeaturePipeline()
    pipeline.fit(raw_dataset.iloc[:500])
    X = pipeline.transform(raw_dataset.iloc[:100], is_training=False)

    forbidden_cols = ["Cost_Loss", "Waste_Risk", "Cluster", "Waste_Weight_kg", "Waste_Quantity_kg"]
    for col in forbidden_cols:
        assert col not in X.columns
        assert col.lower() not in [c.lower() for c in X.columns]


# =========================================================================
# 2. Unit of Observation & Dataset Structure Tests
# =========================================================================

def test_unit_of_observation_is_unique_meal_section_category(raw_dataset: pd.DataFrame):
    """Verify each row is a unique (Date, Meal, Canteen_Section, Food_Category) slice."""
    keys = ["Date", "Meal", "Canteen_Section", "Food_Category"]
    duplicates = raw_dataset.duplicated(subset=keys, keep=False)
    assert duplicates.sum() == 0, "Duplicate records found for same meal/section/category/date"
    assert len(raw_dataset) == 2600


def test_date_continuity_and_row_counts_per_day(raw_dataset: pd.DataFrame):
    """Verify 61 consecutive calendar days without missing dates."""
    dates = pd.to_datetime(raw_dataset["Date"]).drop_duplicates().sort_values()
    assert len(dates) == 61
    expected_range = pd.date_range("2025-06-11", "2025-08-10", freq="D")
    assert (dates.values == expected_range.values).all()

    # Daily counts range between 37 and 46 observations
    daily_counts = raw_dataset.groupby("Date").size()
    assert daily_counts.min() >= 35
    assert daily_counts.max() <= 48


# =========================================================================
# 3. Information Boundaries & Temporal Safeguards
# =========================================================================

def test_inference_transform_strictly_excludes_same_day_and_future_targets():
    """Verify transform_inference never accesses same-day or future target values."""
    records = []
    for d in ["2025-07-01", "2025-07-02", "2025-07-03"]:
        records.append({
            "Date": d,
            "Meal": "Lunch",
            "Canteen_Section": "A",
            "Food_Category": "Rice",
            "Unit_Price_per_kg": 5.0,
            "Waste_Weight_kg": 10.0 if d == "2025-07-02" else 2.0,
        })
    df_mini = pd.DataFrame(records)

    pipe = TemporalFeaturePipeline()
    pipe.fit(df_mini)

    # Predicting for 2025-07-02: target on 2025-07-02 is 10.0.
    # The history should strictly exclude 2025-07-02 and 2025-07-03.
    target_row = df_mini[df_mini["Date"] == "2025-07-02"].copy()
    X = pipe.transform(target_row, is_training=False, historical_records=df_mini)

    # Rolling mean for 7d should only reflect 2025-07-01 (value = 2.0)
    assert math.isclose(X["waste_rolling_mean_7d"].iloc[0], 2.0, abs_tol=1e-5)
    assert X["waste_rolling_count_7d"].iloc[0] == 1.0


def test_first_test_day_invariance_to_test_window_history():
    """Day 1 of a test window produces identical features whether test_df is in history_pool or not."""
    df_raw = pd.read_csv("data/raw/SmartCanteen_Final_Dataset.csv")
    splitter = RollingOriginSplitter(min_train_days=26, test_days=7, num_folds=1, holdout_days=7)
    fold = splitter.split(df_raw)[0]

    train_df = df_raw.iloc[fold.train_indices].copy()
    test_df = df_raw.iloc[fold.test_indices].copy()

    pipe = TemporalFeaturePipeline()
    pipe.fit(train_df)

    # Isolate Day 1 of test window
    day1_date = fold.test_start_date
    day1_records = test_df[test_df["Date"] == day1_date].copy()

    # Case A: history_pool includes test_df
    pool = pd.concat([train_df, test_df], ignore_index=True)
    X_pool = pipe.transform(day1_records, is_training=False, historical_records=pool)

    # Case B: history is strictly train_df
    X_trainonly = pipe.transform(day1_records, is_training=False, historical_records=train_df)

    # On Day 1, records < day1_date are identical in both pools
    pd.testing.assert_frame_equal(X_pool, X_trainonly)
