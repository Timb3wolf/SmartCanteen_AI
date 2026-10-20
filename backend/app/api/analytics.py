"""Analytics endpoints for KPI summaries, distribution charts, recommendations, and records."""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response

from backend.app.schemas.analytics import (
    AnalyticsSummaryResponse,
    DistributionResponse,
    RecommendationsResponse,
    RecordItem,
)
from backend.app.schemas.common import PaginatedResponse
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def get_analytics_service() -> AnalyticsService:
    from backend.app.main import analytics_service
    return analytics_service


def parse_multi_param(param: Optional[List[str]]) -> Optional[List[str]]:
    """Support both repeated params (meal=A&meal=B) and comma-separated params (meal=A,B)."""
    if not param:
        return None
    items = []
    for val in param:
        for sub in val.split(","):
            cleaned = sub.strip()
            if cleaned:
                items.append(cleaned)
    return items if items else None


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    meal: Optional[List[str]] = Query(None, description="Meal filters (Breakfast, Lunch, Dinner)"),
    canteen_section: Optional[List[str]] = Query(None, description="Canteen section filters (A, B, C, D)"),
    food_category: Optional[List[str]] = Query(None, description="Food category filters"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummaryResponse:
    """Calculate real-time KPI metrics on filtered historical canteen records."""
    return analytics.get_summary(
        start_date=start_date,
        end_date=end_date,
        meals=parse_multi_param(meal),
        sections=parse_multi_param(canteen_section),
        categories=parse_multi_param(food_category),
    )


@router.get("/distribution", response_model=DistributionResponse)
def get_analytics_distribution(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    meal: Optional[List[str]] = Query(None, description="Meal filters"),
    canteen_section: Optional[List[str]] = Query(None, description="Canteen section filters"),
    food_category: Optional[List[str]] = Query(None, description="Food category filters"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> DistributionResponse:
    """Return aggregations for category, meal, section, loss, risk class, and daily trend charts."""
    return analytics.get_distribution(
        start_date=start_date,
        end_date=end_date,
        meals=parse_multi_param(meal),
        sections=parse_multi_param(canteen_section),
        categories=parse_multi_param(food_category),
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_analytics_recommendations(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    meal: Optional[List[str]] = Query(None, description="Meal filters"),
    canteen_section: Optional[List[str]] = Query(None, description="Canteen section filters"),
    food_category: Optional[List[str]] = Query(None, description="Food category filters"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> RecommendationsResponse:
    """Generate dynamic, data-driven operational suggestions from the filtered dataset."""
    filtered_df = analytics.filter_dataframe(
        start_date=start_date,
        end_date=end_date,
        meals=parse_multi_param(meal),
        sections=parse_multi_param(canteen_section),
        categories=parse_multi_param(food_category),
    )
    return RecommendationService.generate_recommendations(filtered_df)


@router.get("/records", response_model=PaginatedResponse[RecordItem])
def get_canteen_records(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    meal: Optional[List[str]] = Query(None, description="Meal filters"),
    canteen_section: Optional[List[str]] = Query(None, description="Canteen section filters"),
    food_category: Optional[List[str]] = Query(None, description="Food category filters"),
    search: Optional[str] = Query(None, description="Text search query"),
    sort_by: str = Query("Date", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size limit"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> PaginatedResponse[RecordItem]:
    """Retrieve paginated, filterable historical canteen records for the Data Explorer."""
    return analytics.get_paginated_records(
        start_date=start_date,
        end_date=end_date,
        meals=parse_multi_param(meal),
        sections=parse_multi_param(canteen_section),
        categories=parse_multi_param(food_category),
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
def export_filtered_csv(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    meal: Optional[List[str]] = Query(None, description="Meal filters"),
    canteen_section: Optional[List[str]] = Query(None, description="Canteen section filters"),
    food_category: Optional[List[str]] = Query(None, description="Food category filters"),
    search: Optional[str] = Query(None, description="Text search query"),
    analytics: AnalyticsService = Depends(get_analytics_service),
) -> Response:
    """Export filtered dataset records as a downloadable CSV file."""
    csv_data = analytics.export_csv(
        start_date=start_date,
        end_date=end_date,
        meals=parse_multi_param(meal),
        sections=parse_multi_param(canteen_section),
        categories=parse_multi_param(food_category),
        search=search,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=SmartCanteen_Filtered_Data.csv"},
    )
