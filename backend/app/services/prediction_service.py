"""Prediction service for executing Random Forest ML models and managing prediction history."""

from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import joblib
import pandas as pd

from backend.app.core.config import (
    CLASSIFICATION_FEATURES_PATH,
    CLASSIFIER_MODEL_PATH,
    REGRESSION_FEATURES_PATH,
    REGRESSION_MODEL_PATH,
)
from backend.app.core.database import clear_predictions, get_predictions, save_prediction
from backend.app.schemas.prediction import (
    ClassificationMetrics,
    ModelMetricsResponse,
    PredictionRequest,
    PredictionResponse,
    RegressionMetrics,
)


class PredictionService:
    def __init__(
        self,
        reg_model_path: Path = REGRESSION_MODEL_PATH,
        clf_model_path: Path = CLASSIFIER_MODEL_PATH,
        reg_features_path: Path = REGRESSION_FEATURES_PATH,
        clf_features_path: Path = CLASSIFICATION_FEATURES_PATH,
    ) -> None:
        self.reg_model_path = reg_model_path
        self.clf_model_path = clf_model_path
        self.reg_features_path = reg_features_path
        self.clf_features_path = clf_features_path

        self.reg_model: Any = None
        self.clf_model: Any = None
        self.regression_features: List[str] = []
        self.classification_features: List[str] = []

        self.load_models()

    def load_models(self) -> None:
        """Load and cache Random Forest models and feature column schemas."""
        if not self.reg_model_path.exists():
            raise FileNotFoundError(f"Regression model missing at {self.reg_model_path}")
        if not self.clf_model_path.exists():
            raise FileNotFoundError(f"Classifier model missing at {self.clf_model_path}")
        if not self.reg_features_path.exists():
            raise FileNotFoundError(f"Regression features missing at {self.reg_features_path}")
        if not self.clf_features_path.exists():
            raise FileNotFoundError(f"Classification features missing at {self.clf_features_path}")

        self.reg_model = joblib.load(self.reg_model_path)
        self.clf_model = joblib.load(self.clf_model_path)
        self.regression_features = joblib.load(self.reg_features_path)
        self.classification_features = joblib.load(self.clf_features_path)

    @property
    def is_loaded(self) -> bool:
        return (
            self.reg_model is not None
            and self.clf_model is not None
            and bool(self.regression_features)
            and bool(self.classification_features)
        )

    def predict(self, req: PredictionRequest) -> PredictionResponse:
        """Perform feature preprocessing, inference, and log prediction to database."""
        if not self.is_loaded:
            self.load_models()

        parsed_date = date.fromisoformat(req.date)

        # Build feature DataFrame matching training pipeline
        input_data = pd.DataFrame(
            {
                "Unit_Price_per_kg": [req.unit_price_per_kg],
                "Year": [parsed_date.year],
                "Month": [parsed_date.month],
                "Day": [parsed_date.day],
                "DayOfWeek": [parsed_date.weekday()],
            }
        )

        input_data["Meal"] = req.meal
        input_data["Canteen_Section"] = req.canteen_section
        input_data["Food_Category"] = req.food_category

        # One-hot encode categorical features (drop_first matches training)
        input_encoded = pd.get_dummies(
            input_data,
            columns=["Meal", "Canteen_Section", "Food_Category"],
            drop_first=True,
        )

        # Reindex features to strictly match model expectations
        reg_input = input_encoded.reindex(columns=self.regression_features, fill_value=0)
        clf_input = input_encoded.reindex(columns=self.classification_features, fill_value=0)

        # Execute Random Forest Regressor
        raw_waste = float(self.reg_model.predict(reg_input)[0])
        # Model constraint: food waste cannot be negative in physical operations
        predicted_waste_kg = max(0.0, round(raw_waste, 2))

        # Calculate estimated financial loss: waste_kg * unit_price
        estimated_loss = round(predicted_waste_kg * req.unit_price_per_kg, 2)

        # Execute Random Forest Classifier
        predicted_risk = str(self.clf_model.predict(clf_input)[0])

        model_version = "RandomForestRegressor_v1.0 & RandomForestClassifier_v1.0"

        # Persist to SQLite
        saved_record = save_prediction(
            prediction_date=req.date,
            meal=req.meal,
            canteen_section=req.canteen_section,
            food_category=req.food_category,
            unit_price_per_kg=req.unit_price_per_kg,
            predicted_waste_kg=predicted_waste_kg,
            predicted_risk=predicted_risk,
            estimated_financial_loss=estimated_loss,
            model_version=model_version,
        )

        warnings = [
            "Estimates are based on historical canteen patterns (Test R²: -0.128, Accuracy: 35.38%). "
            "Use as operational guidance alongside actual kitchen audits."
        ]

        return PredictionResponse(
            id=saved_record["id"],
            prediction_date=saved_record["prediction_date"],
            meal=saved_record["meal"],
            canteen_section=saved_record["canteen_section"],
            food_category=saved_record["food_category"],
            unit_price_per_kg=saved_record["unit_price_per_kg"],
            predicted_waste_kg=saved_record["predicted_waste_kg"],
            predicted_risk=saved_record["predicted_risk"],
            estimated_financial_loss=saved_record["estimated_financial_loss"],
            model_version=saved_record["model_version"],
            created_at=saved_record["created_at"],
            warnings=warnings,
        )

    def get_history(
        self,
        limit: int = 100,
        meal: Optional[str] = None,
        risk: Optional[str] = None,
    ) -> List[PredictionResponse]:
        """Fetch logged prediction history from SQLite."""
        records = get_predictions(limit=limit, meal=meal, risk=risk)
        return [
            PredictionResponse(
                id=r["id"],
                prediction_date=r["prediction_date"],
                meal=r["meal"],
                canteen_section=r["canteen_section"],
                food_category=r["food_category"],
                unit_price_per_kg=r["unit_price_per_kg"],
                predicted_waste_kg=r["predicted_waste_kg"],
                predicted_risk=r["predicted_risk"],
                estimated_financial_loss=r["estimated_financial_loss"],
                model_version=r["model_version"],
                created_at=r["created_at"],
            )
            for r in records
        ]

    def clear_history(self) -> int:
        """Clear all logged predictions from SQLite."""
        return clear_predictions()

    def get_metrics(self) -> ModelMetricsResponse:
        """Return the exact, verified test metrics and feature breakdown."""
        return ModelMetricsResponse(
            regression=RegressionMetrics(),
            classification=ClassificationMetrics(),
            features_count=len(self.regression_features),
            features=self.regression_features,
            model_types={
                "regression": "RandomForestRegressor (scikit-learn)",
                "classification": "RandomForestClassifier (scikit-learn)",
            },
            disclaimer=(
                "These metrics reflect test set evaluation on the historical 2,600-record dataset. "
                "The negative regression R² (-0.128) and moderate classification accuracy (35.38%) "
                "demonstrate that additional temporal feature engineering, student attendance logs, "
                "and menu scheduling features are recommended for higher precision."
            ),
            limitations=[
                "Static calendar features do not capture real-time university campus holidays or exam periods.",
                "Weather conditions and campus foot traffic sensors are not present in the current dataset.",
                "Models use dummy encoding with drop_first=True; baseline categories (Breakfast, Section A, Meat) are represented by zeroed dummy columns.",
            ],
        )
