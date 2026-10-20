"""ML pipeline integrity and baseline verification tests.

Validates data schema, model artifact consistency, feature column ordering,
inference bounds, and reproducibility of baseline test metrics.
"""

from datetime import date
import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from backend.app.core.config import (
    CLASSIFICATION_FEATURES_PATH,
    CLASSIFIER_MODEL_PATH,
    DATASET_PATH,
    REGRESSION_FEATURES_PATH,
    REGRESSION_MODEL_PATH,
)
from backend.app.schemas.prediction import PredictionRequest
from backend.app.services.prediction_service import PredictionService


@pytest.fixture(scope="module")
def dataset_df() -> pd.DataFrame:
    assert DATASET_PATH.exists(), f"Dataset missing at {DATASET_PATH}"
    return pd.read_csv(DATASET_PATH)


@pytest.fixture(scope="module")
def prediction_service() -> PredictionService:
    service = PredictionService()
    assert service.is_loaded
    return service


# ==========================================
# 1. Dataset Integrity Tests
# ==========================================

def test_dataset_shape_and_non_null(dataset_df: pd.DataFrame):
    """Ensure dataset has expected volume, columns, and zero missing values."""
    assert dataset_df.shape == (2600, 13)
    assert dataset_df.isnull().sum().sum() == 0, "Dataset contains unexpected null values"

    expected_cols = {
        "Date",
        "Meal",
        "Canteen_Section",
        "Food_Category",
        "Waste_Weight_kg",
        "Unit_Price_per_kg",
        "Cost_Loss",
        "Year",
        "Month",
        "Day",
        "DayOfWeek",
        "Waste_Risk",
        "Cluster",
    }
    assert expected_cols.issubset(set(dataset_df.columns))


def test_dataset_no_duplicate_events(dataset_df: pd.DataFrame):
    """Confirm no duplicate observation records exist for the same meal service station."""
    duplicate_count = dataset_df.duplicated(
        subset=["Date", "Meal", "Canteen_Section", "Food_Category"]
    ).sum()
    assert duplicate_count == 0, "Duplicate operational events found in dataset"


def test_dataset_cost_loss_calculation(dataset_df: pd.DataFrame):
    """Verify Cost_Loss mathematically matches Waste_Weight_kg * Unit_Price_per_kg."""
    expected_loss = dataset_df["Waste_Weight_kg"] * dataset_df["Unit_Price_per_kg"]
    diff = (expected_loss - dataset_df["Cost_Loss"]).abs()
    assert diff.max() < 0.01, f"Cost_Loss calculation mismatch: max diff={diff.max()}"


def test_waste_risk_labels_and_discretization(dataset_df: pd.DataFrame):
    """Verify Waste_Risk categories are valid and correspond to discrete non-overlapping waste weight bins."""
    unique_risks = set(dataset_df["Waste_Risk"].unique())
    assert unique_risks == {"Low", "Medium", "High"}

    # Validate non-overlapping bin boundaries discovered during Phase 0 audit
    low_max = dataset_df[dataset_df["Waste_Risk"] == "Low"]["Waste_Weight_kg"].max()
    med_min = dataset_df[dataset_df["Waste_Risk"] == "Medium"]["Waste_Weight_kg"].min()
    med_max = dataset_df[dataset_df["Waste_Risk"] == "Medium"]["Waste_Weight_kg"].max()
    high_min = dataset_df[dataset_df["Waste_Risk"] == "High"]["Waste_Weight_kg"].min()

    assert low_max < med_min, f"Overlap between Low and Medium bins: low_max={low_max}, med_min={med_min}"
    assert med_max < high_min, f"Overlap between Medium and High bins: med_max={med_max}, high_min={high_min}"


# ==========================================
# 2. Model Artifact & Feature Schema Tests
# ==========================================

def test_model_artifact_files_exist():
    """Verify all 4 required serialization artifacts exist on disk."""
    assert REGRESSION_MODEL_PATH.exists()
    assert CLASSIFIER_MODEL_PATH.exists()
    assert REGRESSION_FEATURES_PATH.exists()
    assert CLASSIFICATION_FEATURES_PATH.exists()


def test_feature_column_schema_consistency():
    """Confirm feature ordering and identity match across regression and classification schemas."""
    reg_features = joblib.load(REGRESSION_FEATURES_PATH)
    clf_features = joblib.load(CLASSIFICATION_FEATURES_PATH)

    assert len(reg_features) == 13
    assert reg_features == clf_features

    expected_features = [
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
    assert reg_features == expected_features


def test_model_estimator_types_and_feature_counts(prediction_service: PredictionService):
    """Check that loaded models have expected estimator types and consume 13 features."""
    assert hasattr(prediction_service.reg_model, "predict")
    assert hasattr(prediction_service.clf_model, "predict")
    assert prediction_service.reg_model.n_features_in_ == 13
    assert prediction_service.clf_model.n_features_in_ == 13


# ==========================================
# 3. Inference Robustness & Boundary Tests
# ==========================================

@pytest.mark.parametrize("meal", ["Breakfast", "Lunch", "Dinner"])
@pytest.mark.parametrize("section", ["A", "B", "C", "D"])
@pytest.mark.parametrize("category", ["Meat", "Rice", "Soup", "Vegetables"])
def test_inference_boundary_matrix(
    prediction_service: PredictionService,
    meal: str,
    section: str,
    category: str,
):
    """Test that all permutations of categorical inputs produce finite, non-negative predictions."""
    req = PredictionRequest(
        date="2025-07-15",
        meal=meal,
        canteen_section=section,
        food_category=category,
        unit_price_per_kg=3.5,
    )
    result = prediction_service.predict(req)

    assert isinstance(result.predicted_waste_kg, float)
    assert np.isfinite(result.predicted_waste_kg)
    assert result.predicted_waste_kg >= 0.0

    assert result.predicted_risk in ["Low", "Medium", "High"]

    expected_loss = round(result.predicted_waste_kg * 3.5, 2)
    assert result.estimated_financial_loss == expected_loss


def test_inference_handles_baseline_categories_gracefully(prediction_service: PredictionService):
    """Verify inference works when all one-hot features are 0 (Breakfast, Section A, Meat)."""
    req = PredictionRequest(
        date="2025-06-15",
        meal="Breakfast",
        canteen_section="A",
        food_category="Meat",
        unit_price_per_kg=5.0,
    )
    result = prediction_service.predict(req)
    assert result.predicted_waste_kg >= 0.0
    assert result.predicted_risk in ["Low", "Medium", "High"]


# ==========================================
# 4. Baseline Reproduction Tests
# ==========================================

def test_reproduce_exact_historical_metrics(dataset_df: pd.DataFrame):
    """Verify that the reported baseline metrics are reproduced exactly on the 80/20 seed 42 split."""
    features = joblib.load(REGRESSION_FEATURES_PATH)
    encoded = pd.get_dummies(
        dataset_df,
        columns=["Meal", "Canteen_Section", "Food_Category"],
        drop_first=True,
    )
    X = encoded[features]
    y_reg = dataset_df["Waste_Weight_kg"]
    y_clf = dataset_df["Waste_Risk"]

    # 1. Regression Reproduction: unstratified 80/20, seed 42
    X_tr_r, X_te_r, y_tr_r, y_te_r = train_test_split(X, y_reg, test_size=0.2, random_state=42)
    reg = joblib.load(REGRESSION_MODEL_PATH)
    y_reg_pred = reg.predict(X_te_r)

    mae = mean_absolute_error(y_te_r, y_reg_pred)
    r2 = r2_score(y_te_r, y_reg_pred)

    assert round(mae, 2) == 1.32, f"Regression MAE mismatch: {mae}"
    assert round(r2, 3) == -0.128, f"Regression R2 mismatch: {r2}"

    # 2. Classification Reproduction: stratified 80/20, seed 42
    X_tr_c, X_te_c, y_tr_c, y_te_c = train_test_split(
        X, y_clf, test_size=0.2, random_state=42, stratify=y_clf
    )
    clf = joblib.load(CLASSIFIER_MODEL_PATH)
    y_clf_pred = clf.predict(X_te_c)

    acc = accuracy_score(y_te_c, y_clf_pred)
    assert round(acc * 100, 2) == 35.38, f"Classification accuracy mismatch: {acc}"
