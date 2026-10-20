"""Utility functions for SmartCanteen AI.

Provides helper routines for loading datasets, models, feature column lists,
and performing inference.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple
import pandas as pd
import joblib

try:
    import streamlit as st
    cache_data = st.cache_data
    cache_resource = st.cache_resource
except ImportError:
    # No-op decorators if streamlit is not installed
    def cache_data(func):
        return func
    def cache_resource(func):
        return func

from src.config import (
    DATASET_PATH,
    REGRESSION_MODEL_PATH,
    CLASSIFIER_MODEL_PATH,
    REGRESSION_FEATURES_PATH,
    CLASSIFICATION_FEATURES_PATH,
)


@cache_data
def load_dataset(path: Path = DATASET_PATH) -> pd.DataFrame:
    """Load the canteen raw dataset from CSV."""
    resolved_path = Path(path).resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Dataset not found at: {resolved_path}")
    return pd.read_csv(resolved_path)


@cache_resource
def load_models(
    reg_path: Path = REGRESSION_MODEL_PATH,
    clf_path: Path = CLASSIFIER_MODEL_PATH,
) -> Tuple[Any, Any]:
    """Load the trained regression and classification models."""
    resolved_reg = Path(reg_path).resolve()
    resolved_clf = Path(clf_path).resolve()

    if not resolved_reg.exists():
        raise FileNotFoundError(f"Regression model not found at: {resolved_reg}")
    if not resolved_clf.exists():
        raise FileNotFoundError(f"Classifier model not found at: {resolved_clf}")

    rf_model = joblib.load(resolved_reg)
    rf_classifier = joblib.load(resolved_clf)
    return rf_model, rf_classifier


@cache_resource
def load_features(
    reg_features_path: Path = REGRESSION_FEATURES_PATH,
    clf_features_path: Path = CLASSIFICATION_FEATURES_PATH,
) -> Tuple[List[str], List[str]]:
    """Load the expected feature columns for regression and classification."""
    resolved_reg_feat = Path(reg_features_path).resolve()
    resolved_clf_feat = Path(clf_features_path).resolve()

    if not resolved_reg_feat.exists():
        raise FileNotFoundError(f"Regression features not found at: {resolved_reg_feat}")
    if not resolved_clf_feat.exists():
        raise FileNotFoundError(f"Classification features not found at: {resolved_clf_feat}")

    regression_features = joblib.load(resolved_reg_feat)
    classification_features = joblib.load(resolved_clf_feat)
    return regression_features, classification_features


def predict_food_waste_and_risk(
    prediction_date,
    prediction_meal: str,
    prediction_section: str,
    prediction_category: str,
    prediction_price: float,
    rf_model: Any,
    rf_classifier: Any,
    regression_features: List[str],
    classification_features: List[str],
) -> Dict[str, Any]:
    """Preprocess user inputs and run regression and classification inference."""
    # Create input data DataFrame
    input_data = pd.DataFrame({
        "Unit_Price_per_kg": [prediction_price],
        "Year": [prediction_date.year],
        "Month": [prediction_date.month],
        "Day": [prediction_date.day],
        "DayOfWeek": [prediction_date.weekday()],
    })

    # Add categorical values
    input_data["Meal"] = prediction_meal
    input_data["Canteen_Section"] = prediction_section
    input_data["Food_Category"] = prediction_category

    # Convert categorical values into dummy variables
    input_data = pd.get_dummies(
        input_data,
        columns=["Meal", "Canteen_Section", "Food_Category"],
        drop_first=True,
    )

    # Prepare input for regression
    regression_input = input_data.reindex(
        columns=regression_features,
        fill_value=0,
    )

    # Predict food waste (kg)
    predicted_waste = float(rf_model.predict(regression_input)[0])

    # Estimate financial loss
    estimated_loss = float(predicted_waste * prediction_price)

    # Prepare input for classification
    classification_input = input_data.reindex(
        columns=classification_features,
        fill_value=0,
    )

    # Predict waste risk (e.g. Low, Medium, High)
    predicted_risk = str(rf_classifier.predict(classification_input)[0])

    return {
        "predicted_waste": predicted_waste,
        "predicted_risk": predicted_risk,
        "estimated_loss": estimated_loss,
    }
