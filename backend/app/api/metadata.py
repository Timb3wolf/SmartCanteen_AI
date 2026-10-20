"""Metadata endpoint for canteen options and categorical values."""

from fastapi import APIRouter, Depends
from backend.app.schemas.metadata import MetadataResponse
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.prediction_service import PredictionService

router = APIRouter(tags=["Metadata"])


def get_analytics_service() -> AnalyticsService:
    from backend.app.main import analytics_service
    return analytics_service


def get_prediction_service() -> PredictionService:
    from backend.app.main import prediction_service
    return prediction_service


@router.get("/metadata", response_model=MetadataResponse)
def get_metadata(
    analytics: AnalyticsService = Depends(get_analytics_service),
    predictions: PredictionService = Depends(get_prediction_service),
) -> MetadataResponse:
    """Return available meals, sections, food categories, risk classes, and supported date/price ranges."""
    return analytics.get_metadata(feature_columns=predictions.regression_features)
