"""Tests for the leakage-safe temporal feature engineering pipeline.

Verifies:
1. Strict ISO date parsing and validation.
2. Cyclical trigonometric day-of-week encoding and weekend indicator.
3. Hand-checkable lag and rolling-window calculations.
4. Non-leakage guarantees (own target and future targets never leak).
5. Unseen category safety and fixed column schema invariance.
6. Missing history indicators and safe fallbacks.
7. Duplicate key handling and deterministic outputs.
8. Compatibility with existing prediction service and production schemas.
"""

import datetime
import math
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.features import (
    TemporalFeatureConfig,
    TemporalFeaturePipeline,
    create_candidate_feature_pipeline,
    parse_strict_date,
)
from backend.app.services.prediction_service import PredictionService
from backend.app.schemas.prediction import PredictionRequest


# -----------------------------------------------------------------------------
# 1. Date Parsing Tests
# -----------------------------------------------------------------------------

def test_parse_strict_date_valid():
    """Verify valid date types and string formats are parsed correctly."""
    ts1 = parse_strict_date("2025-07-15")
    assert ts1 == pd.Timestamp("2025-07-15")

    ts2 = parse_strict_date(datetime.date(2025, 6, 11))
    assert ts2 == pd.Timestamp("2025-06-11")

    ts3 = parse_strict_date(pd.Timestamp("2025-08-10 14:30:00"))
    assert ts3 == pd.Timestamp("2025-08-10")


@pytest.mark.parametrize(
    "invalid_input",
    [
        "2025-02-30",       # Invalid calendar date
        "2025/07/15",       # Non-ISO format
        "15-07-2025",       # Day-first format
        "invalid-date",     # Plain string
        "2025-13-01",       # Non-existent month
        None,               # None
        float("nan"),       # NaN
        12345,              # Unsupported type
    ],
)
def test_parse_strict_date_invalid(invalid_input):
    """Verify invalid dates explicitly raise ValueError."""
    with pytest.raises(ValueError):
        parse_strict_date(invalid_input)


# -----------------------------------------------------------------------------
# 2. Calendar and Cyclic Encoding Tests
# -----------------------------------------------------------------------------

def test_cyclical_dow_and_weekend_encoding():
    """Verify trigonometric encoding of day of week and weekend flags."""
    pipeline = TemporalFeaturePipeline()

    # Monday (weekday 0)
    mon_feats = pipeline.transform_single(
        date_str="2025-06-16",  # 2025-06-16 is Monday
        meal="Lunch",
        canteen_section="A",
        food_category="Rice",
        unit_price_per_kg=10.0,
    )
    assert mon_feats["day_of_week"].iloc[0] == 0.0
    assert pytest.approx(mon_feats["dow_sin"].iloc[0], abs=1e-5) == 0.0
    assert pytest.approx(mon_feats["dow_cos"].iloc[0], abs=1e-5) == 1.0
    assert mon_feats["is_weekend"].iloc[0] == 0.0

    # Friday (weekday 4)
    fri_feats = pipeline.transform_single(
        date_str="2025-06-20",  # 2025-06-20 is Friday
        meal="Lunch",
        canteen_section="A",
        food_category="Rice",
        unit_price_per_kg=10.0,
    )
    assert fri_feats["day_of_week"].iloc[0] == 4.0
    assert fri_feats["is_weekend"].iloc[0] == 0.0

    # Saturday (weekday 5)
    sat_feats = pipeline.transform_single(
        date_str="2025-06-21",  # 2025-06-21 is Saturday
        meal="Lunch",
        canteen_section="A",
        food_category="Rice",
        unit_price_per_kg=10.0,
    )
    assert sat_feats["day_of_week"].iloc[0] == 5.0
    assert sat_feats["is_weekend"].iloc[0] == 1.0

    # Sunday (weekday 6)
    sun_feats = pipeline.transform_single(
        date_str="2025-06-22",  # 2025-06-22 is Sunday
        meal="Lunch",
        canteen_section="A",
        food_category="Rice",
        unit_price_per_kg=10.0,
    )
    assert sun_feats["day_of_week"].iloc[0] == 6.0
    assert sun_feats["is_weekend"].iloc[0] == 1.0

    # Pythagorean identity: sin^2 + cos^2 == 1.0 for all days
    for feats in [mon_feats, fri_feats, sat_feats, sun_feats]:
        s = feats["dow_sin"].iloc[0]
        c = feats["dow_cos"].iloc[0]
        assert pytest.approx(s**2 + c**2, abs=1e-5) == 1.0


# -----------------------------------------------------------------------------
# 3. Hand-Checkable Toy Fixture Tests (Lag & Rolling Windows)
# -----------------------------------------------------------------------------

def test_hand_checkable_toy_fixture_rolling_and_lag():
    """Verify exact rolling windows and lag 7d using a deterministic toy sequence.

    Constructs 8 consecutive daily records for ('A', 'Lunch', 'Rice'):
      Day 1 (2025-01-01): 10.0 kg
      Day 2 (2025-01-02): 20.0 kg
      Day 3 (2025-01-03): 30.0 kg
      Day 4 (2025-01-04): 40.0 kg
      Day 5 (2025-01-05): 50.0 kg
      Day 6 (2025-01-06): 60.0 kg
      Day 7 (2025-01-07): 70.0 kg
      Day 8 (2025-01-08): 80.0 kg
    """
    toy_data = []
    base_date = pd.Timestamp("2025-01-01")
    for i in range(8):
        cur_date = base_date + pd.Timedelta(days=i)
        toy_data.append(
            {
                "Date": cur_date.strftime("%Y-%m-%d"),
                "Meal": "Lunch",
                "Canteen_Section": "A",
                "Food_Category": "Rice",
                "Unit_Price_per_kg": 50.0,
                "Waste_Weight_kg": float((i + 1) * 10),
            }
        )

    toy_df = pd.DataFrame(toy_data)
    pipeline = TemporalFeaturePipeline(
        TemporalFeatureConfig(fallback_waste_mean=99.0, learn_fallback_mean=False)
    )
    pipeline.fit(toy_df)
    transformed = pipeline.transform(toy_df, is_training=True)

    # Day 1: Zero prior history exists
    day1 = transformed.iloc[0]
    assert day1["is_missing_lag_7d"] == 1.0
    assert day1["waste_lag_7d"] == 99.0  # Safe fallback
    assert day1["is_missing_rolling_7d"] == 1.0
    assert day1["waste_rolling_mean_7d"] == 99.0
    assert day1["waste_rolling_count_7d"] == 0.0

    # Day 2: Prior history contains Day 1 (10.0 kg) ONLY
    day2 = transformed.iloc[1]
    assert day2["waste_rolling_count_7d"] == 1.0
    assert day2["is_missing_rolling_7d"] == 0.0
    assert day2["waste_rolling_mean_7d"] == 10.0
    assert day2["waste_rolling_std_7d"] == 0.0  # 1 sample -> std is 0.0
    assert day2["is_missing_lag_7d"] == 1.0  # Lag 7d not yet available

    # Day 3: Prior history contains Day 1 (10.0) and Day 2 (20.0). Mean = 15.0
    day3 = transformed.iloc[2]
    assert day3["waste_rolling_count_7d"] == 2.0
    assert day3["waste_rolling_mean_7d"] == 15.0
    expected_std_day3 = float(np.std([10.0, 20.0], ddof=1))
    assert pytest.approx(day3["waste_rolling_std_7d"], abs=1e-5) == expected_std_day3

    # Day 8: Exactly 7 days after Day 1
    # Lag 7d must be Day 1's waste: 10.0 kg
    day8 = transformed.iloc[7]
    assert day8["is_missing_lag_7d"] == 0.0
    assert day8["waste_lag_7d"] == 10.0

    # Rolling 7d window for Day 8 covers [Day 1, Day 7].
    # Expected mean = (10 + 20 + 30 + 40 + 50 + 60 + 70) / 7 = 40.0
    assert day8["waste_rolling_count_7d"] == 7.0
    assert day8["waste_rolling_mean_7d"] == 40.0
    expected_std_day8 = float(np.std([10, 20, 30, 40, 50, 60, 70], ddof=1))
    assert pytest.approx(day8["waste_rolling_std_7d"], abs=1e-5) == expected_std_day8

    # CRITICAL: Day 8's OWN waste (80.0) MUST NOT be in its rolling mean
    assert day8["waste_rolling_mean_7d"] != 45.0  # 45.0 would mean Day 8 leaked!


# -----------------------------------------------------------------------------
# 4. Leakage Prevention Tests
# -----------------------------------------------------------------------------

def test_no_own_target_leakage():
    """Verify changing a record's own target value does not alter its features."""
    df = pd.DataFrame(
        [
            {"Date": "2025-06-11", "Meal": "Dinner", "Canteen_Section": "B", "Food_Category": "Meat", "Unit_Price_per_kg": 100.0, "Waste_Weight_kg": 2.0},
            {"Date": "2025-06-18", "Meal": "Dinner", "Canteen_Section": "B", "Food_Category": "Meat", "Unit_Price_per_kg": 100.0, "Waste_Weight_kg": 3.0},
        ]
    )

    pipeline = TemporalFeaturePipeline()
    pipeline.fit(df)

    feats1 = pipeline.transform(df, is_training=True)

    # Mutate second row's own target from 3.0 to 999.0
    df_mutated = df.copy()
    df_mutated.loc[1, "Waste_Weight_kg"] = 999.0

    feats2 = pipeline.transform(df_mutated, is_training=True)

    # Row 1's features must be identical
    pd.testing.assert_frame_equal(feats1.iloc[[0]], feats2.iloc[[0]])

    # Row 2's historical features must be identical (it sees row 1, not itself)
    cols_to_check = ["waste_lag_7d", "waste_rolling_mean_7d", "waste_rolling_count_7d"]
    pd.testing.assert_frame_equal(feats1.iloc[[1]][cols_to_check], feats2.iloc[[1]][cols_to_check])


def test_no_future_target_leakage():
    """Verify changing a future observation's target never affects an earlier record."""
    df = pd.DataFrame(
        [
            {"Date": "2025-06-11", "Meal": "Breakfast", "Canteen_Section": "A", "Food_Category": "Soup", "Unit_Price_per_kg": 40.0, "Waste_Weight_kg": 1.5},
            {"Date": "2025-06-12", "Meal": "Breakfast", "Canteen_Section": "A", "Food_Category": "Soup", "Unit_Price_per_kg": 40.0, "Waste_Weight_kg": 2.5},
            {"Date": "2025-06-25", "Meal": "Breakfast", "Canteen_Section": "A", "Food_Category": "Soup", "Unit_Price_per_kg": 40.0, "Waste_Weight_kg": 4.0},
        ]
    )

    pipeline = TemporalFeaturePipeline()
    pipeline.fit(df)

    feats1 = pipeline.transform(df, is_training=True)

    # Mutate row 2 (future date: 2025-06-25) to an extreme value
    df_mutated = df.copy()
    df_mutated.loc[2, "Waste_Weight_kg"] = 5000.0

    feats2 = pipeline.transform(df_mutated, is_training=True)

    # Rows 0 and 1 must be 100% byte-for-byte identical
    pd.testing.assert_frame_equal(feats1.iloc[:2], feats2.iloc[:2])


# -----------------------------------------------------------------------------
# 5. Missing History and Unseen Category Tests
# -----------------------------------------------------------------------------

def test_missing_history_indicators_and_fallbacks():
    """Verify records with zero history return explicit indicators and safe fallback mean."""
    pipeline = TemporalFeaturePipeline(TemporalFeatureConfig(fallback_waste_mean=2.585))
    empty_df = pd.DataFrame(
        columns=["Date", "Meal", "Canteen_Section", "Food_Category", "Unit_Price_per_kg", "Waste_Weight_kg"]
    )
    pipeline.fit(empty_df)

    # Query for a date with no history
    feats = pipeline.transform_single(
        date_str="2025-09-01",
        meal="Breakfast",
        canteen_section="C",
        food_category="Vegetables",
        unit_price_per_kg=60.0,
    )

    assert feats["is_missing_lag_7d"].iloc[0] == 1.0
    assert feats["waste_lag_7d"].iloc[0] == 2.585
    assert feats["is_missing_rolling_7d"].iloc[0] == 1.0
    assert feats["waste_rolling_mean_7d"].iloc[0] == 2.585
    assert feats["waste_rolling_std_7d"].iloc[0] == 0.0
    assert feats["waste_rolling_count_7d"].iloc[0] == 0.0

    # Ensure no NaN or infinite values
    assert np.isfinite(feats.values).all()


def test_unseen_categories_safe_handling():
    """Verify novel unseen categories do not crash or alter column count."""
    pipeline = TemporalFeaturePipeline()

    feats = pipeline.transform_single(
        date_str="2025-07-20",
        meal="MidnightBuffet",        # Unseen meal
        canteen_section="Wing_Z",       # Unseen section
        food_category="ExoticSeafood",  # Unseen category
        unit_price_per_kg=150.0,
    )

    assert feats.shape == (1, len(pipeline.feature_names))

    # All standard one-hot indicators must be 0.0
    for meal in pipeline.config.known_meals:
        assert feats[f"meal_{meal}"].iloc[0] == 0.0
    for sec in pipeline.config.known_sections:
        assert feats[f"section_{sec}"].iloc[0] == 0.0
    for cat in pipeline.config.known_categories:
        assert feats[f"category_{cat}"].iloc[0] == 0.0

    assert np.isfinite(feats.values).all()


# -----------------------------------------------------------------------------
# 6. Schema Consistency and Determinism Tests
# -----------------------------------------------------------------------------

def test_training_and_inference_schema_identical():
    """Verify training and inference transformations produce identical columns."""
    df = pd.DataFrame(
        [
            {"Date": "2025-06-11", "Meal": "Lunch", "Canteen_Section": "A", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 2.0},
            {"Date": "2025-06-18", "Meal": "Lunch", "Canteen_Section": "A", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 2.5},
        ]
    )

    pipeline = TemporalFeaturePipeline()
    pipeline.fit(df)

    train_out = pipeline.transform(df, is_training=True)
    infer_out = pipeline.transform(df, is_training=False)

    assert list(train_out.columns) == pipeline.feature_names
    assert list(infer_out.columns) == pipeline.feature_names
    assert train_out.dtypes.to_dict() == infer_out.dtypes.to_dict()


def test_determinism_on_identical_inputs():
    """Verify running the pipeline multiple times produces identical bit-for-bit output."""
    df = pd.DataFrame(
        [
            {"Date": "2025-06-11", "Meal": "Dinner", "Canteen_Section": "B", "Food_Category": "Meat", "Unit_Price_per_kg": 100.0, "Waste_Weight_kg": 3.0},
            {"Date": "2025-06-18", "Meal": "Dinner", "Canteen_Section": "B", "Food_Category": "Meat", "Unit_Price_per_kg": 100.0, "Waste_Weight_kg": 3.5},
        ]
    )

    p1 = TemporalFeaturePipeline().fit(df)
    p2 = TemporalFeaturePipeline().fit(df)

    out1 = p1.transform(df, is_training=True)
    out2 = p2.transform(df, is_training=True)

    pd.testing.assert_frame_equal(out1, out2)


def test_duplicate_key_handling():
    """Verify duplicate records on the same date/group do not duplicate rows or explode joins."""
    df_dup = pd.DataFrame(
        [
            {"Date": "2025-06-11", "Meal": "Lunch", "Canteen_Section": "A", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 2.0},
            {"Date": "2025-06-11", "Meal": "Lunch", "Canteen_Section": "A", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 4.0},  # Duplicate same day
            {"Date": "2025-06-18", "Meal": "Lunch", "Canteen_Section": "A", "Food_Category": "Rice", "Unit_Price_per_kg": 50.0, "Waste_Weight_kg": 3.0},
        ]
    )

    pipeline = TemporalFeaturePipeline().fit(df_dup)
    out = pipeline.transform(df_dup, is_training=True)

    # Exactly 3 rows must be returned
    assert len(out) == 3
    assert np.isfinite(out.values).all()


# -----------------------------------------------------------------------------
# 7. Production Compatibility Test
# -----------------------------------------------------------------------------

def test_production_prediction_service_unbroken():
    """Verify existing production PredictionService continues to run cleanly."""
    service = PredictionService()
    assert service.is_loaded

    req = PredictionRequest(
        date="2025-07-20",
        meal="Lunch",
        canteen_section="B",
        food_category="Rice",
        unit_price_per_kg=4.5,
    )

    res = service.predict(req)
    assert res.predicted_waste_kg >= 0.0
    assert res.predicted_risk in ["Low", "Medium", "High"]
    assert res.estimated_financial_loss == round(res.predicted_waste_kg * 4.5, 2)
