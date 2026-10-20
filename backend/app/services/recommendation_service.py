"""Recommendation service for generating dynamic, data-driven operational insights."""

from datetime import datetime, timezone
from typing import List
import pandas as pd

from backend.app.schemas.analytics import RecommendationItem, RecommendationsResponse


class RecommendationService:
    @staticmethod
    def generate_recommendations(filtered_df: pd.DataFrame) -> RecommendationsResponse:
        """Derive actionable insights directly from calculated values in the filtered dataset."""
        if filtered_df.empty:
            return RecommendationsResponse(
                recommendations=[
                    RecommendationItem(
                        id="rec-empty",
                        category="Data Notice",
                        type="info",
                        title="No Records in Selected Filter",
                        description="Adjust your filter selections to see data-driven recommendations.",
                        metric_value=None,
                        action_item="Clear or broaden current filters to analyze historical trends.",
                    )
                ],
                generated_at=datetime.now(timezone.utc).isoformat(),
            )

        total_waste = float(filtered_df["Waste_Weight_kg"].sum())
        total_loss = float(filtered_df["Cost_Loss"].sum())
        total_records = len(filtered_df)
        recs: List[RecommendationItem] = []

        # 1. Highest waste category
        cat_waste = filtered_df.groupby("Food_Category")["Waste_Weight_kg"].sum()
        if not cat_waste.empty:
            top_cat = cat_waste.idxmax()
            top_cat_waste = float(cat_waste.max())
            cat_pct = round((top_cat_waste / total_waste * 100), 1) if total_waste > 0 else 0.0

            recs.append(
                RecommendationItem(
                    id="rec-cat-waste",
                    category="Category Priority",
                    type="warning",
                    title=f"High Waste in {top_cat}",
                    description=(
                        f"{top_cat} generated the highest cumulative waste in the active dataset, "
                        f"totaling {top_cat_waste:.2f} kg ({cat_pct}% of total waste)."
                    ),
                    metric_value=f"{top_cat_waste:.1f} kg ({cat_pct}%)",
                    action_item=f"Calibrate preparation batches and serving portion guidelines specifically for {top_cat}.",
                )
            )

        # 2. Meal period analysis
        meal_waste = filtered_df.groupby("Meal")["Waste_Weight_kg"].sum()
        if not meal_waste.empty:
            top_meal = meal_waste.idxmax()
            top_meal_waste = float(meal_waste.max())
            meal_pct = round((top_meal_waste / total_waste * 100), 1) if total_waste > 0 else 0.0

            recs.append(
                RecommendationItem(
                    id="rec-meal-priority",
                    category="Meal Scheduling",
                    type="info",
                    title=f"Peak Waste Service: {top_meal}",
                    description=(
                        f"{top_meal} service accounts for {top_meal_waste:.2f} kg of discarded food "
                        f"({meal_pct}% of all recorded service waste)."
                    ),
                    metric_value=f"{top_meal_waste:.1f} kg ({meal_pct}%)",
                    action_item=f"Review student attendance curves during {top_meal} and transition to staggered cooking.",
                )
            )

        # 3. Canteen section analysis
        section_waste = filtered_df.groupby("Canteen_Section")["Waste_Weight_kg"].sum()
        if not section_waste.empty:
            top_sec = section_waste.idxmax()
            top_sec_waste = float(section_waste.max())
            sec_pct = round((top_sec_waste / total_waste * 100), 1) if total_waste > 0 else 0.0

            recs.append(
                RecommendationItem(
                    id="rec-section-focus",
                    category="Station Audit",
                    type="warning",
                    title=f"Section {top_sec} Surplus Alert",
                    description=(
                        f"Canteen Section {top_sec} recorded {top_sec_waste:.2f} kg of food waste, "
                        f"leading all serving stations."
                    ),
                    metric_value=f"Section {top_sec}: {top_sec_waste:.1f} kg",
                    action_item=f"Inspect plate return trays and self-serve counters in Section {top_sec} to identify excessive serving sizes.",
                )
            )

        # 4. Highest financial loss category
        cat_loss = filtered_df.groupby("Food_Category")["Cost_Loss"].sum()
        if not cat_loss.empty:
            top_loss_cat = cat_loss.idxmax()
            top_loss_amount = float(cat_loss.max())
            loss_pct = round((top_loss_amount / total_loss * 100), 1) if total_loss > 0 else 0.0

            recs.append(
                RecommendationItem(
                    id="rec-financial-loss",
                    category="Budget Impact",
                    type="danger" if loss_pct > 35 else "warning",
                    title=f"Financial Loss Driver: {top_loss_cat}",
                    description=(
                        f"{top_loss_cat} accounted for ${top_loss_amount:.2f} in financial losses "
                        f"({loss_pct}% of total monetary waste)."
                    ),
                    metric_value=f"${top_loss_amount:.2f} ({loss_pct}%)",
                    action_item=f"Prioritize inventory purchase controls and supplier order quantities for {top_loss_cat}.",
                )
            )

        # 5. Waste risk distribution insight
        risk_counts = filtered_df["Waste_Risk"].value_counts()
        high_risk_count = int(risk_counts.get("High", 0))
        high_risk_pct = round((high_risk_count / total_records * 100), 1) if total_records > 0 else 0.0

        if high_risk_pct >= 33.0:
            recs.append(
                RecommendationItem(
                    id="rec-high-risk-alert",
                    category="Risk Mitigation",
                    type="danger",
                    title="Elevated High-Risk Ratio",
                    description=(
                        f"{high_risk_count} records ({high_risk_pct}%) in the active selection are classified as High Waste Risk."
                    ),
                    metric_value=f"{high_risk_pct}% High Risk",
                    action_item="Mandate end-of-day kitchen log reconciliation and implement daily leftover flash sales or food bank transfers.",
                )
            )
        else:
            recs.append(
                RecommendationItem(
                    id="rec-controlled-risk",
                    category="Risk Mitigation",
                    type="success",
                    title="Stable Risk Profile",
                    description=(
                        f"High-risk incidents represent {high_risk_pct}% of observed records, maintaining normal operational thresholds."
                    ),
                    metric_value=f"{high_risk_pct}% High Risk",
                    action_item="Maintain current portion standards while monitoring seasonal variations.",
                )
            )

        # 6. Trend over time comparison (first half vs second half of days)
        unique_dates = sorted(filtered_df["Date"].unique())
        if len(unique_dates) >= 4:
            mid = len(unique_dates) // 2
            first_half_dates = unique_dates[:mid]
            second_half_dates = unique_dates[mid:]

            first_half_avg = float(
                filtered_df[filtered_df["Date"].isin(first_half_dates)]
                .groupby("Date")["Waste_Weight_kg"]
                .sum()
                .mean()
            )
            second_half_avg = float(
                filtered_df[filtered_df["Date"].isin(second_half_dates)]
                .groupby("Date")["Waste_Weight_kg"]
                .sum()
                .mean()
            )

            diff = round(second_half_avg - first_half_avg, 2)
            pct_change = round((diff / first_half_avg * 100), 1) if first_half_avg > 0 else 0.0

            if diff < 0:
                recs.append(
                    RecommendationItem(
                        id="rec-trend-improvement",
                        category="Progress Tracking",
                        type="success",
                        title="Favorable Daily Waste Trend",
                        description=(
                            f"Average daily food waste decreased by {abs(diff):.2f} kg ({abs(pct_change)}%) "
                            f"between the initial and later periods in this dataset."
                        ),
                        metric_value=f"{diff:+.2f} kg/day",
                        action_item="Document the kitchen procedures used in recent weeks as standard operating practices.",
                    )
                )
            else:
                recs.append(
                    RecommendationItem(
                        id="rec-trend-warning",
                        category="Progress Tracking",
                        type="warning",
                        title="Upward Trend in Daily Waste",
                        description=(
                            f"Average daily waste increased by {diff:.2f} kg (+{pct_change}%) in the second half "
                            f"of the selected period."
                        ),
                        metric_value=f"+{diff:.2f} kg/day",
                        action_item="Investigate whether recent university events or changes in supplier pack sizes caused increased kitchen trimmings.",
                    )
                )

        return RecommendationsResponse(
            recommendations=recs,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
