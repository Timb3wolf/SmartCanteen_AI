"""Prediction and history endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.schemas.prediction import (
    ClearHistoryResponse,
    PredictionHistoryResponse,
    PredictionRequest,
    PredictionResponse,
)
from backend.app.services.prediction_service import PredictionService

router = APIRouter(tags=["Predictions"])


def get_prediction_service() -> PredictionService:
    from backend.app.main import prediction_service
    return prediction_service


@router.post("/predict", response_model=PredictionResponse, status_code=status.HTTP_201_CREATED)
def predict_food_waste(
    request: PredictionRequest,
    service: PredictionService = Depends(get_prediction_service),
) -> PredictionResponse:
    """Execute dual-model inference (Regression + Classification) and persist to prediction history."""
    try:
        return service.predict(request)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference error: {str(e)}",
        )


@router.get("/predictions/history", response_model=PredictionHistoryResponse)
def get_prediction_history(
    limit: int = Query(100, ge=1, le=500, description="Max history records to return"),
    meal: Optional[str] = Query(None, description="Optional meal filter"),
    risk: Optional[str] = Query(None, description="Optional risk category filter"),
    service: PredictionService = Depends(get_prediction_service),
) -> PredictionHistoryResponse:
    """Retrieve logged prediction history from SQLite."""
    records = service.get_history(limit=limit, meal=meal, risk=risk)
    return PredictionHistoryResponse(predictions=records, total=len(records))


@router.delete("/predictions/history", response_model=ClearHistoryResponse)
def clear_prediction_history(
    service: PredictionService = Depends(get_prediction_service),
) -> ClearHistoryResponse:
    """Clear all records from prediction history."""
    deleted = service.clear_history()
    return ClearHistoryResponse(
        message="Prediction history cleared successfully",
        deleted_count=deleted,
    )
