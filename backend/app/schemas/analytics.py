"""Schemas for analytics summaries, distributions, and recommendations."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    total_waste_kg: float = Field(..., description="Total cumulative food waste in kilograms")
    avg_waste_per_record_kg: float = Field(..., description="Average waste per recorded event in kg")
    total_financial_loss: float = Field(..., description="Total financial loss (waste_kg * unit_price)")
    record_count: int = Field(..., description="Total matching historical records")
    avg_waste_per_service_kg: float = Field(..., description="Average waste per meal service (Date + Meal group)")
    avg_daily_waste_kg: float = Field(..., description="Average daily food waste in kilograms")
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class CategoryWasteItem(BaseModel):
    category: str
    waste_kg: float
    percentage: float


class MealWasteItem(BaseModel):
    meal: str
    waste_kg: float
    percentage: float


class SectionWasteItem(BaseModel):
    section: str
    waste_kg: float
    percentage: float


class CategoryLossItem(BaseModel):
    category: str
    cost_loss: float
    percentage: float


class RiskDistributionItem(BaseModel):
    risk: str
    count: int
    percentage: float


class DailyTrendItem(BaseModel):
    date: str
    waste_kg: float
    cost_loss: float
    record_count: int


class DistributionResponse(BaseModel):
    waste_by_category: List[CategoryWasteItem]
    waste_by_meal: List[MealWasteItem]
    waste_by_section: List[SectionWasteItem]
    financial_loss_by_category: List[CategoryLossItem]
    risk_distribution: List[RiskDistributionItem]
    daily_waste_trend: List[DailyTrendItem]


class RecommendationItem(BaseModel):
    id: str
    category: str
    type: str  # 'warning', 'info', 'success', 'danger'
    title: str
    description: str
    metric_value: Optional[str] = None
    action_item: str


class RecommendationsResponse(BaseModel):
    recommendations: List[RecommendationItem]
    generated_at: str


class RecordItem(BaseModel):
    Date: str
    Meal: str
    Canteen_Section: str
    Food_Category: str
    Waste_Weight_kg: float
    Unit_Price_per_kg: float
    Cost_Loss: float
    Waste_Risk: str
