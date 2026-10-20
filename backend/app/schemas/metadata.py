"""Metadata schemas for canteen configuration and options."""

from typing import List, Optional
from pydantic import BaseModel


class DateRange(BaseModel):
    min_date: str
    max_date: str


class PriceRange(BaseModel):
    min: float
    max: float
    mean: float


class MetadataResponse(BaseModel):
    meals: List[str]
    canteen_sections: List[str]
    food_categories: List[str]
    risk_categories: List[str]
    date_range: DateRange
    unit_price_range: PriceRange
    feature_columns: List[str]
    total_dataset_records: int
