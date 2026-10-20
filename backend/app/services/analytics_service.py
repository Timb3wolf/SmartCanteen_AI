"""Analytics service for querying, aggregating, and analyzing canteen data."""

from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from backend.app.core.config import DATASET_PATH
from backend.app.schemas.analytics import (
    AnalyticsSummaryResponse,
    CategoryLossItem,
    CategoryWasteItem,
    DailyTrendItem,
    DistributionResponse,
    MealWasteItem,
    RecordItem,
    RiskDistributionItem,
    SectionWasteItem,
)
from backend.app.schemas.common import PaginatedResponse
from backend.app.schemas.metadata import DateRange, MetadataResponse, PriceRange


class AnalyticsService:
    def __init__(self, dataset_path: Path = DATASET_PATH) -> None:
        self.dataset_path = dataset_path
        self._df: Optional[pd.DataFrame] = None
        self.load_dataset()

    def load_dataset(self) -> pd.DataFrame:
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found at {self.dataset_path}")
        self._df = pd.read_csv(self.dataset_path)
        # Ensure Date is string in YYYY-MM-DD
        self._df["Date"] = pd.to_datetime(self._df["Date"]).dt.strftime("%Y-%m-%d")
        return self._df

    @property
    def df(self) -> pd.DataFrame:
        if self._df is None:
            return self.load_dataset()
        return self._df

    def get_metadata(self, feature_columns: List[str]) -> MetadataResponse:
        df = self.df
        min_date = str(df["Date"].min())
        max_date = str(df["Date"].max())
        min_price = float(df["Unit_Price_per_kg"].min())
        max_price = float(df["Unit_Price_per_kg"].max())
        mean_price = round(float(df["Unit_Price_per_kg"].mean()), 2)

        return MetadataResponse(
            meals=sorted(df["Meal"].unique().tolist()),
            canteen_sections=sorted(df["Canteen_Section"].unique().tolist()),
            food_categories=sorted(df["Food_Category"].unique().tolist()),
            risk_categories=["Low", "Medium", "High"],
            date_range=DateRange(min_date=min_date, max_date=max_date),
            unit_price_range=PriceRange(min=min_price, max=max_price, mean=mean_price),
            feature_columns=feature_columns,
            total_dataset_records=len(df),
        )

    def filter_dataframe(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        meals: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        filtered = self.df.copy()

        if start_date:
            filtered = filtered[filtered["Date"] >= start_date]
        if end_date:
            filtered = filtered[filtered["Date"] <= end_date]
        if meals:
            filtered = filtered[filtered["Meal"].isin(meals)]
        if sections:
            filtered = filtered[filtered["Canteen_Section"].isin(sections)]
        if categories:
            filtered = filtered[filtered["Food_Category"].isin(categories)]

        return filtered

    def get_summary(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        meals: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> AnalyticsSummaryResponse:
        filtered = self.filter_dataframe(start_date, end_date, meals, sections, categories)

        record_count = len(filtered)
        if record_count == 0:
            return AnalyticsSummaryResponse(
                total_waste_kg=0.0,
                avg_waste_per_record_kg=0.0,
                total_financial_loss=0.0,
                record_count=0,
                avg_waste_per_service_kg=0.0,
                avg_daily_waste_kg=0.0,
                start_date=start_date,
                end_date=end_date,
            )

        total_waste = round(float(filtered["Waste_Weight_kg"].sum()), 2)
        avg_waste = round(float(filtered["Waste_Weight_kg"].mean()), 2)
        total_loss = round(float(filtered["Cost_Loss"].sum()), 2)

        # Average waste per meal service (Date + Meal group)
        service_groups = filtered.groupby(["Date", "Meal"])["Waste_Weight_kg"].sum()
        avg_service_waste = round(float(service_groups.mean()), 2) if not service_groups.empty else 0.0

        # Average daily food waste
        daily_groups = filtered.groupby("Date")["Waste_Weight_kg"].sum()
        avg_daily_waste = round(float(daily_groups.mean()), 2) if not daily_groups.empty else 0.0

        return AnalyticsSummaryResponse(
            total_waste_kg=total_waste,
            avg_waste_per_record_kg=avg_waste,
            total_financial_loss=total_loss,
            record_count=record_count,
            avg_waste_per_service_kg=avg_service_waste,
            avg_daily_waste_kg=avg_daily_waste,
            start_date=start_date or (str(filtered["Date"].min()) if not filtered.empty else None),
            end_date=end_date or (str(filtered["Date"].max()) if not filtered.empty else None),
        )

    def get_distribution(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        meals: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
    ) -> DistributionResponse:
        filtered = self.filter_dataframe(start_date, end_date, meals, sections, categories)
        total_waste = filtered["Waste_Weight_kg"].sum() if not filtered.empty else 0.0
        total_loss = filtered["Cost_Loss"].sum() if not filtered.empty else 0.0
        total_records = len(filtered)

        # Waste by category
        cat_series = filtered.groupby("Food_Category")["Waste_Weight_kg"].sum().sort_values(ascending=False)
        waste_by_cat = [
            CategoryWasteItem(
                category=str(cat),
                waste_kg=round(float(val), 2),
                percentage=round(float(val / total_waste * 100), 1) if total_waste > 0 else 0.0,
            )
            for cat, val in cat_series.items()
        ]

        # Waste by meal
        meal_series = filtered.groupby("Meal")["Waste_Weight_kg"].sum().sort_values(ascending=False)
        waste_by_meal = [
            MealWasteItem(
                meal=str(m),
                waste_kg=round(float(val), 2),
                percentage=round(float(val / total_waste * 100), 1) if total_waste > 0 else 0.0,
            )
            for m, val in meal_series.items()
        ]

        # Waste by section
        sec_series = filtered.groupby("Canteen_Section")["Waste_Weight_kg"].sum().sort_values(ascending=False)
        waste_by_sec = [
            SectionWasteItem(
                section=str(s),
                waste_kg=round(float(val), 2),
                percentage=round(float(val / total_waste * 100), 1) if total_waste > 0 else 0.0,
            )
            for s, val in sec_series.items()
        ]

        # Financial loss by category
        loss_series = filtered.groupby("Food_Category")["Cost_Loss"].sum().sort_values(ascending=False)
        loss_by_cat = [
            CategoryLossItem(
                category=str(cat),
                cost_loss=round(float(val), 2),
                percentage=round(float(val / total_loss * 100), 1) if total_loss > 0 else 0.0,
            )
            for cat, val in loss_series.items()
        ]

        # Risk distribution
        risk_counts = filtered["Waste_Risk"].value_counts().reindex(["Low", "Medium", "High"], fill_value=0)
        risk_dist = [
            RiskDistributionItem(
                risk=str(r),
                count=int(cnt),
                percentage=round(float(cnt / total_records * 100), 1) if total_records > 0 else 0.0,
            )
            for r, cnt in risk_counts.items()
        ]

        # Daily waste trend
        daily_df = (
            filtered.groupby("Date")
            .agg(
                waste_kg=("Waste_Weight_kg", "sum"),
                cost_loss=("Cost_Loss", "sum"),
                record_count=("Waste_Weight_kg", "count"),
            )
            .reset_index()
            .sort_values("Date")
        )

        daily_trend = [
            DailyTrendItem(
                date=str(row["Date"]),
                waste_kg=round(float(row["waste_kg"]), 2),
                cost_loss=round(float(row["cost_loss"]), 2),
                record_count=int(row["record_count"]),
            )
            for _, row in daily_df.iterrows()
        ]

        return DistributionResponse(
            waste_by_category=waste_by_cat,
            waste_by_meal=waste_by_meal,
            waste_by_section=waste_by_sec,
            financial_loss_by_category=loss_by_cat,
            risk_distribution=risk_dist,
            daily_waste_trend=daily_trend,
        )

    def get_paginated_records(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        meals: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        search: Optional[str] = None,
        sort_by: str = "Date",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[RecordItem]:
        filtered = self.filter_dataframe(start_date, end_date, meals, sections, categories)

        if search:
            search_term = search.lower().strip()
            mask = (
                filtered["Meal"].str.lower().str.contains(search_term)
                | filtered["Canteen_Section"].str.lower().str.contains(search_term)
                | filtered["Food_Category"].str.lower().str.contains(search_term)
                | filtered["Waste_Risk"].str.lower().str.contains(search_term)
                | filtered["Date"].str.contains(search_term)
            )
            filtered = filtered[mask]

        # Validate sort column
        allowed_cols = [
            "Date",
            "Meal",
            "Canteen_Section",
            "Food_Category",
            "Waste_Weight_kg",
            "Unit_Price_per_kg",
            "Cost_Loss",
            "Waste_Risk",
        ]
        col = sort_by if sort_by in allowed_cols else "Date"
        ascending = sort_order.lower() == "asc"
        filtered = filtered.sort_values(by=col, ascending=ascending)

        total_records = len(filtered)
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        total_pages = max(1, (total_records + page_size - 1) // page_size)

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_df = filtered.iloc[start_idx:end_idx]

        items = [
            RecordItem(
                Date=str(row["Date"]),
                Meal=str(row["Meal"]),
                Canteen_Section=str(row["Canteen_Section"]),
                Food_Category=str(row["Food_Category"]),
                Waste_Weight_kg=round(float(row["Waste_Weight_kg"]), 2),
                Unit_Price_per_kg=round(float(row["Unit_Price_per_kg"]), 2),
                Cost_Loss=round(float(row["Cost_Loss"]), 2),
                Waste_Risk=str(row["Waste_Risk"]),
            )
            for _, row in page_df.iterrows()
        ]

        return PaginatedResponse[RecordItem](
            items=items,
            total=total_records,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def export_csv(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        meals: Optional[List[str]] = None,
        sections: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        search: Optional[str] = None,
    ) -> str:
        filtered = self.filter_dataframe(start_date, end_date, meals, sections, categories)
        if search:
            search_term = search.lower().strip()
            mask = (
                filtered["Meal"].str.lower().str.contains(search_term)
                | filtered["Canteen_Section"].str.lower().str.contains(search_term)
                | filtered["Food_Category"].str.lower().str.contains(search_term)
                | filtered["Waste_Risk"].str.lower().str.contains(search_term)
                | filtered["Date"].str.contains(search_term)
            )
            filtered = filtered[mask]

        # Export clean columns
        export_cols = [
            "Date",
            "Meal",
            "Canteen_Section",
            "Food_Category",
            "Waste_Weight_kg",
            "Unit_Price_per_kg",
            "Cost_Loss",
            "Waste_Risk",
        ]
        return filtered[export_cols].to_csv(index=False)
