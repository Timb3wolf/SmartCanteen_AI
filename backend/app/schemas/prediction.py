"""Schemas for ML prediction requests, responses, and history."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import date


class PredictionRequest(BaseModel):
    date: str = Field(..., json_schema_extra={"example": "2025-07-15"}, description="Observation date in YYYY-MM-DD format")
    meal: str = Field(..., json_schema_extra={"example": "Lunch"}, description="Meal period (Breakfast, Lunch, Dinner)")
    canteen_section: str = Field(..., json_schema_extra={"example": "B"}, description="Canteen section (A, B, C, D)")
    food_category: str = Field(..., json_schema_extra={"example": "Rice"}, description="Food category (Meat, Rice, Soup, Vegetables)")
    unit_price_per_kg: float = Field(..., gt=0.0, le=50.0, json_schema_extra={"example": 4.5}, description="Unit price per kg in dollars/currency")

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Date must be in ISO format (YYYY-MM-DD)")


class PredictionResponse(BaseModel):
    id: Optional[int] = None
    prediction_date: str
    meal: str
    canteen_section: str
    food_category: str
    unit_price_per_kg: float
    predicted_waste_kg: float
    predicted_risk: str
    estimated_financial_loss: float
    model_version: str
    created_at: str
    warnings: List[str] = Field(default_factory=list)


class PredictionHistoryResponse(BaseModel):
    predictions: List[PredictionResponse]
    total: int


class ClearHistoryResponse(BaseModel):
    message: str
    deleted_count: int


class RegressionMetrics(BaseModel):
    mae: float = 1.322705
    rmse: float = 1.550671
    r2_score: float = -0.128365
    target: str = "Waste_Weight_kg"


class ClassificationMetrics(BaseModel):
    accuracy: float = 0.353846
    macro_precision: float = 0.354729
    macro_recall: float = 0.353846
    macro_f1: float = 0.354169
    target: str = "Waste_Risk (Low, Medium, High)"


class ModelMetricsResponse(BaseModel):
    regression: RegressionMetrics
    classification: ClassificationMetrics
    features_count: int
    features: List[str]
    model_types: Dict[str, str]
    disclaimer: str
    limitations: List[str]
