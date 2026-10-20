"""Health check endpoint."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from backend.app.schemas.common import HealthResponse
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.prediction_service import PredictionService

router = APIRouter(tags=["Health"])


def get_analytics_service() -> AnalyticsService:
    from backend.app.main import analytics_service
    return analytics_service


def get_prediction_service() -> PredictionService:
    from backend.app.main import prediction_service
    return prediction_service


@router.get("/health", response_model=HealthResponse)
def health_check(
    analytics: AnalyticsService = Depends(get_analytics_service),
    predictions: PredictionService = Depends(get_prediction_service),
) -> HealthResponse:
    """Return application health, dataset status, and model loading state."""
    dataset_ok = False
    record_count = 0
    try:
        record_count = len(analytics.df)
        dataset_ok = record_count > 0
    except Exception:
        pass

    models_loaded = predictions.is_loaded

    return HealthResponse(
        status="healthy" if (dataset_ok and models_loaded) else "degraded",
        dataset_available=dataset_ok,
        record_count=record_count,
        models_loaded=models_loaded,
        models={
            "regression_model": predictions.reg_model is not None,
            "classifier_model": predictions.clf_model is not None,
            "feature_schema": len(predictions.regression_features) > 0,
        },
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
