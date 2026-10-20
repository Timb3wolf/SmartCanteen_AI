"""Comprehensive tests for Phase 4 Ensemble Feasibility.

Verifies:
- Weight normalization, boundary constraints, and validation
- Mathematical exactness of weighted averaging and shrinkage
- Chronological out-of-fold accumulation and leakage prevention
- Meta-learner behavior, non-negativity, and input validations
- Determinism and future mutation invariance
"""

import math
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.ensemble import (
    ChronologicalStackingMetaLearner,
    EnsembleExperimentRunner,
    EnsembleSpec,
    WeightedAverageEnsemble,
)
from backend.app.ml.evaluation import RollingOriginSplitter


# =========================================================================
# 1. Weight Validation and Invariant Tests
# =========================================================================

def test_ensemble_weights_validation_success():
    """Valid weights and shrinkage values initialize without error."""
    ens = WeightedAverageEnsemble(
        weights={"model_a": 0.5, "model_b": 0.5},
        shrinkage_to_mean=0.2,
    )
    assert ens.weights == {"model_a": 0.5, "model_b": 0.5}
    assert ens.shrinkage_to_mean == 0.2


def test_ensemble_weights_empty_error():
    """Empty weights dictionary must raise ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        WeightedAverageEnsemble(weights={})


def test_ensemble_weights_negative_error():
    """Negative weights must raise ValueError."""
    with pytest.raises(ValueError, match="cannot be negative"):
        WeightedAverageEnsemble(weights={"model_a": -0.2, "model_b": 1.2})


def test_ensemble_weights_non_sum_to_one_error():
    """Weights that do not sum to 1.0 must raise ValueError."""
    with pytest.raises(ValueError, match="must sum to 1.0"):
        WeightedAverageEnsemble(weights={"model_a": 0.4, "model_b": 0.4})


def test_ensemble_shrinkage_out_of_bounds_error():
    """shrinkage_to_mean must be strictly within [0.0, 1.0]."""
    with pytest.raises(ValueError, match="shrinkage_to_mean must be in"):
        WeightedAverageEnsemble(weights={"model_a": 1.0}, shrinkage_to_mean=1.5)

    with pytest.raises(ValueError, match="shrinkage_to_mean must be in"):
        WeightedAverageEnsemble(weights={"model_a": 1.0}, shrinkage_to_mean=-0.1)


# =========================================================================
# 2. Mathematical Exactness and Shrinkage Tests
# =========================================================================

def test_weighted_averaging_exact_math():
    """Base weighted predictions compute exact linear combinations."""
    ens = WeightedAverageEnsemble(weights={"rf": 0.25, "xgb": 0.75})
    preds = {
        "rf": np.array([10.0, 20.0, 30.0]),
        "xgb": np.array([20.0, 40.0, 60.0]),
    }
    result = ens.predict(preds)
    expected = 0.25 * preds["rf"] + 0.75 * preds["xgb"]
    np.testing.assert_allclose(result, expected, rtol=1e-7)
    np.testing.assert_allclose(result, [17.5, 35.0, 52.5], rtol=1e-7)


def test_baseline_shrinkage_exact_math():
    """Shrinkage toward training mean interpolates linearly between blend and mean."""
    ens = WeightedAverageEnsemble(
        weights={"rf": 0.5, "xgb": 0.5},
        shrinkage_to_mean=0.4,
    )
    preds = {
        "rf": np.array([10.0, 20.0]),
        "xgb": np.array([20.0, 40.0]),
    }
    training_mean = 5.0
    # Base blend = [15.0, 30.0]
    # Shrunk = (1 - 0.4) * [15.0, 30.0] + 0.4 * 5.0 = [9.0 + 2.0, 18.0 + 2.0] = [11.0, 20.0]
    result = ens.predict(preds, training_mean=training_mean)
    np.testing.assert_allclose(result, [11.0, 20.0], rtol=1e-7)


def test_shrinkage_requires_valid_mean():
    """Non-zero shrinkage requires a valid finite training mean."""
    ens = WeightedAverageEnsemble(weights={"m": 1.0}, shrinkage_to_mean=0.5)
    preds = {"m": np.array([1.0, 2.0])}

    with pytest.raises(ValueError, match="training_mean is required"):
        ens.predict(preds, training_mean=None)

    with pytest.raises(ValueError, match="training_mean is required"):
        ens.predict(preds, training_mean=float("nan"))


def test_predict_mismatched_lengths_error():
    """Inconsistent array lengths between models raise ValueError."""
    ens = WeightedAverageEnsemble(weights={"rf": 0.5, "xgb": 0.5})
    preds = {
        "rf": np.array([1.0, 2.0]),
        "xgb": np.array([1.0, 2.0, 3.0]),
    }
    with pytest.raises(ValueError, match="Inconsistent prediction array lengths"):
        ens.predict(preds)


def test_predict_missing_model_error():
    """Missing model key in predictions raises ValueError."""
    ens = WeightedAverageEnsemble(weights={"rf": 0.5, "xgb": 0.5})
    preds = {"rf": np.array([1.0, 2.0])}
    with pytest.raises(ValueError, match="missing required models"):
        ens.predict(preds)


# =========================================================================
# 3. Chronological Stacking Meta-Learner Tests
# =========================================================================

def test_stacking_meta_learner_fit_and_predict():
    """Meta-learner fits on OOF arrays and predicts on new base predictions."""
    np.random.seed(42)
    n_samples = 50
    y_true = np.random.uniform(1.0, 4.0, size=n_samples)
    p_rf = y_true + np.random.normal(0, 0.2, size=n_samples)
    p_xgb = y_true + np.random.normal(0, 0.2, size=n_samples)

    meta = ChronologicalStackingMetaLearner(
        model_names=["rf", "xgb"],
        alpha=1.0,
        positive=True,
    )
    meta.fit({"rf": p_rf, "xgb": p_xgb}, y_true)

    assert meta.fitted_
    assert len(meta.coef_) == 2
    assert all(c >= 0.0 for c in meta.coef_)

    test_preds = {"rf": np.array([2.5, 3.0]), "xgb": np.array([2.6, 2.9])}
    out = meta.predict(test_preds)
    assert len(out) == 2
    assert all(np.isfinite(out))


def test_stacking_unfitted_predict_raises():
    """Predicting on unfitted meta-learner raises RuntimeError."""
    meta = ChronologicalStackingMetaLearner(model_names=["rf"])
    with pytest.raises(RuntimeError, match="not been fitted"):
        meta.predict({"rf": np.array([1.0])})


def test_stacking_empty_targets_raises():
    """Fitting meta-learner on empty targets raises ValueError."""
    meta = ChronologicalStackingMetaLearner(model_names=["rf"])
    with pytest.raises(ValueError, match="Cannot fit meta-learner on empty targets"):
        meta.fit({"rf": np.array([])}, np.array([]))


# =========================================================================
# 4. Leakage Prevention and Temporal Order Invariance
# =========================================================================

def test_future_targets_mutation_invariance(monkeypatch):
    """Mutating future test targets or features cannot alter prior fold predictions."""
    # Create minimal 35-day synthetic canteen dataset (min_train_days=26, test_days=7 -> 1 fold)
    dates = pd.date_range("2025-06-01", periods=36, freq="D")
    records = []
    np.random.seed(42)
    for d in dates:
        for meal in ["Lunch", "Dinner"]:
            records.append({
                "Date": d.strftime("%Y-%m-%d"),
                "Meal": meal,
                "Canteen_Section": "Section_A",
                "Food_Category": "Rice",
                "Unit_Price_per_kg": 5.0,
                "Waste_Weight_kg": float(np.random.uniform(1.0, 5.0)),
            })
    df_clean = pd.DataFrame(records)

    splitter = RollingOriginSplitter(min_train_days=26, test_days=7, num_folds=1, holdout_days=0)
    runner = EnsembleExperimentRunner(splitter=splitter, random_state=42)

    res_clean = runner.run_development_ensembles(df_clean, include_stacking=False)
    pred_fold1_clean = res_clean["folds"][0]["models"]["Blend_50RF_50XGB"]["mae"]

    # Now mutate future holdout data (dates beyond fold 1 test set)
    df_mutated = df_clean.copy()
    max_fold1_test_date = res_clean["folds"][0]["test_dates"].split(" to ")[1]
    future_mask = df_mutated["Date"] > max_fold1_test_date
    df_mutated.loc[future_mask, "Waste_Weight_kg"] = 999.0
    df_mutated.loc[future_mask, "Unit_Price_per_kg"] = 999.0

    res_mutated = runner.run_development_ensembles(df_mutated, include_stacking=False)
    pred_fold1_mutated = res_mutated["folds"][0]["models"]["Blend_50RF_50XGB"]["mae"]

    # Fold 1 metrics must remain strictly identical
    assert math.isclose(pred_fold1_clean, pred_fold1_mutated, rel_tol=1e-9)


def test_chronological_stacking_strict_fold_progression():
    """Verify that Fold 1 has no stacking result, and Folds 2+ accumulate strictly past OOF."""
    dates = pd.date_range("2025-06-01", periods=54, freq="D")
    records = []
    np.random.seed(42)
    for d in dates:
        records.append({
            "Date": d.strftime("%Y-%m-%d"),
            "Meal": "Lunch",
            "Canteen_Section": "Section_A",
            "Food_Category": "Rice",
            "Unit_Price_per_kg": 5.0,
            "Waste_Weight_kg": float(np.random.uniform(1.0, 5.0)),
        })
    df_synth = pd.DataFrame(records)

    # 26 min train + 3 folds of 7 days = 26 + 21 = 47 days, leaving holdout
    splitter = RollingOriginSplitter(min_train_days=26, test_days=7, num_folds=3, holdout_days=7)
    runner = EnsembleExperimentRunner(splitter=splitter, random_state=42)

    res = runner.run_development_ensembles(df_synth, include_stacking=True)
    folds = res["folds"]
    assert len(folds) == 3

    # Fold 1 has no prior OOF -> Ridge_Stacking must NOT be present
    assert "Ridge_Stacking" not in folds[0]["models"]
    assert folds[0]["stacking_coefs"] is None

    # Fold 2 has prior OOF from Fold 1 -> Ridge_Stacking must be present
    assert "Ridge_Stacking" in folds[1]["models"]
    assert folds[1]["stacking_coefs"] is not None
    assert len(folds[1]["stacking_coefs"]) == 2

    # Fold 3 has prior OOF from Folds 1 & 2 -> Ridge_Stacking must be present
    assert "Ridge_Stacking" in folds[2]["models"]


# =========================================================================
# 5. Determinism Across Runs
# =========================================================================

def test_ensemble_runner_deterministic_repeatability():
    """Running development benchmark twice with same seed produces bitwise identical results."""
    dates = pd.date_range("2025-06-01", periods=40, freq="D")
    records = []
    np.random.seed(42)
    for d in dates:
        records.append({
            "Date": d.strftime("%Y-%m-%d"),
            "Meal": "Lunch",
            "Canteen_Section": "Section_A",
            "Food_Category": "Rice",
            "Unit_Price_per_kg": 5.0,
            "Waste_Weight_kg": float(np.random.uniform(1.0, 5.0)),
        })
    df_synth = pd.DataFrame(records)

    splitter = RollingOriginSplitter(min_train_days=26, test_days=7, num_folds=2, holdout_days=0)
    runner1 = EnsembleExperimentRunner(splitter=splitter, random_state=42)
    runner2 = EnsembleExperimentRunner(splitter=splitter, random_state=42)

    res1 = runner1.run_development_ensembles(df_synth, include_stacking=True)
    res2 = runner2.run_development_ensembles(df_synth, include_stacking=True)

    for f1, f2 in zip(res1["folds"], res2["folds"]):
        for model_name in f1["models"]:
            assert math.isclose(f1["models"][model_name]["mae"], f2["models"][model_name]["mae"], rel_tol=1e-9)
            assert math.isclose(f1["models"][model_name]["rmse"], f2["models"][model_name]["rmse"], rel_tol=1e-9)
