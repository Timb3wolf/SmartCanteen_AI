"""Model metrics and evaluation transparency endpoint."""

from fastapi import APIRouter, Depends
from backend.app.schemas.prediction import ModelMetricsResponse
from backend.app.services.prediction_service import PredictionService

router = APIRouter(prefix="/models", tags=["Model Governance"])


def get_prediction_service() -> PredictionService:
    from backend.app.main import prediction_service
    return prediction_service


@router.get("/metrics", response_model=ModelMetricsResponse)
def get_model_metrics(
    service: PredictionService = Depends(get_prediction_service),
) -> ModelMetricsResponse:
    """Return verified historical evaluation metrics for Random Forest Regressor and Classifier."""
    return service.get_metrics()
