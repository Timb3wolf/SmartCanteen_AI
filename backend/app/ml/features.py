"""Leakage-Safe Temporal Feature Engineering Pipeline for SmartCanteen AI.

Provides modular, reproducible, and verifiable feature engineering with:
- Strict calendar date parsing and cyclic trigonometric encodings.
- Backward-looking historical lag and rolling-window aggregations with calendar semantics.
- Non-leaking out-of-time lookups (current and future dates are strictly excluded).
- Explicit missing-history indicators and safe fallbacks.
- Deterministic categorical encoding and unseen-category safety.
"""

from dataclasses import dataclass, field
import datetime
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd


@dataclass
class TemporalFeatureConfig:
    """Configuration for temporal feature construction."""

    date_column: str = "Date"
    target_column: str = "Waste_Weight_kg"
    price_column: str = "Unit_Price_per_kg"
    grouping_keys: List[str] = field(
        default_factory=lambda: ["Canteen_Section", "Meal", "Food_Category"]
    )
    lag_days: int = 7
    rolling_windows: List[int] = field(default_factory=lambda: [7, 14])
    include_cyclic_dow: bool = True
    include_is_weekend: bool = True
    fallback_waste_mean: float = 2.585

    learn_fallback_mean: bool = True

    # Fixed known categorical vocabulary for deterministic one-hot representation
    known_meals: List[str] = field(
        default_factory=lambda: ["Breakfast", "Dinner", "Lunch"]
    )
    known_sections: List[str] = field(
        default_factory=lambda: ["A", "B", "C", "D"]
    )
    known_categories: List[str] = field(
        default_factory=lambda: ["Meat", "Rice", "Soup", "Vegetables"]
    )


def parse_strict_date(val: Any) -> pd.Timestamp:
    """Parse a date value strictly, raising ValueError for invalid dates."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        raise ValueError("Observation date cannot be None, null, or NaN.")

    if isinstance(val, (datetime.datetime, pd.Timestamp)):
        return pd.Timestamp(val).floor("D")

    if isinstance(val, datetime.date):
        return pd.Timestamp(val)

    if isinstance(val, str):
        cleaned = val.strip()
        parts = cleaned.split("-")
        if len(parts) != 3 or len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
            raise ValueError(
                f"Date '{val}' must be a valid ISO string in YYYY-MM-DD format."
            )
        try:
            d = datetime.date.fromisoformat(cleaned)
            return pd.Timestamp(d)
        except ValueError as err:
            raise ValueError(f"Invalid calendar date string '{val}': {err}") from err

    raise ValueError(f"Unsupported date type: {type(val)} for value '{val}'")


class TemporalFeaturePipeline:
    """Leakage-safe temporal and categorical feature engineering pipeline.

    Guarantees:
    1. Historical features look strictly backward: [Date - window, Date - 1 day].
    2. An observation's own target or future observations never enter its features.
    3. Categorical encoding is deterministic and safe against unseen categories.
    4. Missing history has explicit boolean indicator flags and safe fallbacks.
    5. Raw Day (1-31) and constant Year (2025) are excluded to prevent calendar memorization.
    """

    def __init__(self, config: Optional[TemporalFeatureConfig] = None) -> None:
        self.config = config or TemporalFeatureConfig()
        self.is_fitted: bool = False
        self._learned_fallback_mean: float = self.config.fallback_waste_mean
        self._history_records: Optional[pd.DataFrame] = None
        self._feature_names: List[str] = self._build_feature_names()

    @property
    def fallback_mean(self) -> float:
        """Return the current fallback mean used for imputing missing history."""
        return self._learned_fallback_mean

    def _build_feature_names(self) -> List[str]:
        """Generate ordered, deterministic list of feature names."""
        names: List[str] = [
            "unit_price_per_kg",
            "day_of_week",
        ]

        if self.config.include_cyclic_dow:
            names.extend(["dow_sin", "dow_cos"])

        if self.config.include_is_weekend:
            names.append("is_weekend")

        # Categoricals (deterministic alphabetical order)
        for meal in sorted(self.config.known_meals):
            names.append(f"meal_{meal}")
        for sec in sorted(self.config.known_sections):
            names.append(f"section_{sec}")
        for cat in sorted(self.config.known_categories):
            names.append(f"category_{cat}")

        # Lag 7d
        names.extend(["waste_lag_7d", "is_missing_lag_7d"])

        # Rolling windows (7d and 14d)
        for w in self.config.rolling_windows:
            names.extend([
                f"waste_rolling_mean_{w}d",
                f"waste_rolling_std_{w}d",
                f"waste_rolling_count_{w}d",
                f"is_missing_rolling_{w}d",
            ])

        return names

    @property
    def feature_names(self) -> List[str]:
        """Return immutable copy of feature column names."""
        return list(self._feature_names)

    def fit(self, train_df: pd.DataFrame) -> "TemporalFeaturePipeline":
        """Fit pipeline on the training partition only.

        Learns fallback values and indexes historical records for out-of-time lookups.
        """
        if train_df.empty:
            self._history_records = pd.DataFrame(
                columns=["parsed_date"] + self.config.grouping_keys + [self.config.target_column]
            )
            self._learned_fallback_mean = self.config.fallback_waste_mean
            self.is_fitted = True
            return self

        # Ensure required columns exist
        required_cols = self.config.grouping_keys + [self.config.date_column]
        for col in required_cols:
            if col not in train_df.columns:
                raise ValueError(f"Required column '{col}' missing from training DataFrame.")

        clean_train = train_df.copy()
        clean_train["parsed_date"] = clean_train[self.config.date_column].apply(parse_strict_date)

        # Learn fallback mean from target if present in training set
        if self.config.learn_fallback_mean and self.config.target_column in clean_train.columns:
            targets = clean_train[self.config.target_column].dropna()
            if not targets.empty:
                self._learned_fallback_mean = float(targets.mean())
        else:
            self._learned_fallback_mean = self.config.fallback_waste_mean

        # Index historical records: deduplicate on [Date, keys] by taking the mean of target
        if self.config.target_column in clean_train.columns:
            dedup_cols = ["parsed_date"] + self.config.grouping_keys
            history = (
                clean_train.groupby(dedup_cols, as_index=False)[self.config.target_column]
                .mean()
                .sort_values("parsed_date")
                .reset_index(drop=True)
            )
            self._history_records = history
        else:
            self._history_records = pd.DataFrame(
                columns=["parsed_date"] + self.config.grouping_keys + [self.config.target_column]
            )

        self.is_fitted = True
        return self

    def update_history(self, new_records: pd.DataFrame) -> None:
        """Update known historical records with new audited ground truth."""
        if new_records.empty:
            return

        clean_new = new_records.copy()
        clean_new["parsed_date"] = clean_new[self.config.date_column].apply(parse_strict_date)

        if self.config.target_column not in clean_new.columns:
            raise ValueError(
                f"Ground-truth target column '{self.config.target_column}' required to update history."
            )

        dedup_cols = ["parsed_date"] + self.config.grouping_keys
        agg_new = (
            clean_new.groupby(dedup_cols, as_index=False)[self.config.target_column]
            .mean()
        )

        if self._history_records is None or self._history_records.empty:
            self._history_records = agg_new.sort_values("parsed_date").reset_index(drop=True)
        else:
            combined = pd.concat([self._history_records, agg_new], ignore_index=True)
            self._history_records = (
                combined.groupby(dedup_cols, as_index=False)[self.config.target_column]
                .mean()
                .sort_values("parsed_date")
                .reset_index(drop=True)
            )

    def _compute_calendar_features(self, dates: pd.Series) -> pd.DataFrame:
        """Derive strict calendar and cyclic features from timestamps."""
        dows = dates.dt.weekday
        cal_df = pd.DataFrame(index=dates.index)
        cal_df["day_of_week"] = dows.astype(float)

        if self.config.include_cyclic_dow:
            cal_df["dow_sin"] = np.sin(2.0 * np.pi * dows / 7.0)
            cal_df["dow_cos"] = np.cos(2.0 * np.pi * dows / 7.0)

        if self.config.include_is_weekend:
            cal_df["is_weekend"] = (dows >= 5).astype(float)

        return cal_df

    def _compute_categorical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate deterministic one-hot features with safe unseen handling."""
        cat_df = pd.DataFrame(index=df.index)

        # Meal
        for meal in sorted(self.config.known_meals):
            cat_df[f"meal_{meal}"] = (df["Meal"] == meal).astype(float)

        # Canteen Section
        for sec in sorted(self.config.known_sections):
            cat_df[f"section_{sec}"] = (df["Canteen_Section"] == sec).astype(float)

        # Food Category
        for cat in sorted(self.config.known_categories):
            cat_df[f"category_{cat}"] = (df["Food_Category"] == cat).astype(float)

        return cat_df

    def transform_training_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform historical records in batch mode with strict zero leakage.

        For each observation at date D, historical features are computed strictly
        from previous observations occurring in [D - window, D - 1 day].
        """
        if df.empty:
            return pd.DataFrame(columns=self._feature_names, dtype=float)

        work_df = df.copy()
        work_df["parsed_date"] = work_df[self.config.date_column].apply(parse_strict_date)
        work_df["_orig_order_idx"] = np.arange(len(work_df))

        # 1. Price feature
        price_series = work_df[self.config.price_column].astype(float)

        # 2. Calendar features
        cal_df = self._compute_calendar_features(work_df["parsed_date"])

        # 3. Categorical features
        cat_df = self._compute_categorical_features(work_df)

        # 4. Lag and rolling calculations grouped by keys
        # We process grouped data using explicit calendar intervals
        target_col = self.config.target_column
        has_target = target_col in work_df.columns

        if not has_target:
            raise ValueError(
                f"Target column '{target_col}' must be present in DataFrame for training batch transformation."
            )

        # To prevent duplicate dates from creating ambiguous joins, deduplicate lookup
        dedup_cols = ["parsed_date"] + self.config.grouping_keys
        hist_lookup = (
            work_df.groupby(dedup_cols, as_index=False)[target_col]
            .mean()
            .sort_values("parsed_date")
            .reset_index(drop=True)
        )

        # A. Exact Lag 7d: join with history where JoinDate = parsed_date - 7 days
        hist_lag7 = hist_lookup.copy()
        hist_lag7["_join_date"] = hist_lag7["parsed_date"] + pd.Timedelta(days=self.config.lag_days)

        merged_lag7 = work_df.merge(
            hist_lag7[["_join_date"] + self.config.grouping_keys + [target_col]],
            left_on=["parsed_date"] + self.config.grouping_keys,
            right_on=["_join_date"] + self.config.grouping_keys,
            how="left",
            suffixes=("", "_lag7_hist"),
        )

        lag7_raw = merged_lag7[f"{target_col}_lag7_hist"]
        is_missing_lag7 = lag7_raw.isna().astype(float)
        waste_lag7 = lag7_raw.fillna(self._learned_fallback_mean).astype(float)

        # B. Rolling windows via grouped rolling with closed='left'
        # closed='left' includes strictly [Date - window, Date), excluding the current Date
        def _calc_group_rolling(group: pd.DataFrame) -> pd.DataFrame:
            g_sorted = group.sort_values("parsed_date")
            g_idx = g_sorted.set_index("parsed_date")

            out_dict: Dict[str, Any] = {"_orig_order_idx": g_sorted["_orig_order_idx"].values}

            for w in self.config.rolling_windows:
                r_series = g_idx[target_col].rolling(f"{w}D", closed="left")
                r_mean = r_series.mean().values
                r_std = r_series.std().values
                r_count = r_series.count().values

                out_dict[f"waste_rolling_mean_{w}d"] = r_mean
                out_dict[f"waste_rolling_std_{w}d"] = r_std
                out_dict[f"waste_rolling_count_{w}d"] = r_count

            return pd.DataFrame(out_dict)

        rolling_res = (
            work_df.groupby(self.config.grouping_keys, group_keys=False)
            .apply(_calc_group_rolling, include_groups=False)
        )

        # Align rolling results back to original row order
        aligned_df = work_df[["_orig_order_idx"]].merge(rolling_res, on="_orig_order_idx", how="left")

        # Assemble full candidate feature DataFrame
        features_df = pd.DataFrame(index=work_df.index)
        features_df["unit_price_per_kg"] = price_series.values
        features_df["day_of_week"] = cal_df["day_of_week"].values

        if self.config.include_cyclic_dow:
            features_df["dow_sin"] = cal_df["dow_sin"].values
            features_df["dow_cos"] = cal_df["dow_cos"].values

        if self.config.include_is_weekend:
            features_df["is_weekend"] = cal_df["is_weekend"].values

        for col in cat_df.columns:
            features_df[col] = cat_df[col].values

        features_df["waste_lag_7d"] = waste_lag7.values
        features_df["is_missing_lag_7d"] = is_missing_lag7.values

        for w in self.config.rolling_windows:
            m_col = f"waste_rolling_mean_{w}d"
            s_col = f"waste_rolling_std_{w}d"
            c_col = f"waste_rolling_count_{w}d"
            miss_col = f"is_missing_rolling_{w}d"

            raw_mean = aligned_df[m_col].values
            raw_std = aligned_df[s_col].values
            raw_count = aligned_df[c_col].values

            # Flag missing when count == 0 or mean is NaN
            is_miss = (np.isnan(raw_mean) | (raw_count == 0)).astype(float)
            filled_mean = np.where(is_miss == 1.0, self._learned_fallback_mean, raw_mean)
            # Std is 0.0 when missing or single observation
            filled_std = np.where(np.isnan(raw_std), 0.0, raw_std)
            filled_count = np.where(np.isnan(raw_count), 0.0, raw_count)

            features_df[m_col] = filled_mean.astype(float)
            features_df[s_col] = filled_std.astype(float)
            features_df[c_col] = filled_count.astype(float)
            features_df[miss_col] = is_miss.astype(float)

        # Enforce exact column ordering and finite float representation
        features_df = features_df[self._feature_names].astype(float)
        return features_df

    def transform_inference(
        self,
        df: pd.DataFrame,
        historical_records: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Transform candidate inference records using prior history strictly.

        For each prediction date D, lookups only access records where Date < D.
        """
        if df.empty:
            return pd.DataFrame(columns=self._feature_names, dtype=float)

        hist = historical_records if historical_records is not None else self._history_records
        if hist is None:
            # Fallback to empty historical DataFrame if un-fitted
            hist = pd.DataFrame(
                columns=["parsed_date"] + self.config.grouping_keys + [self.config.target_column]
            )
        else:
            if "parsed_date" not in hist.columns:
                hist = hist.copy()
                hist["parsed_date"] = hist[self.config.date_column].apply(parse_strict_date)

        # Pre-index history by grouping keys for fast O(1) group lookup
        hist_by_key: Dict[Tuple[str, str, str], pd.DataFrame] = {}
        if not hist.empty and all(k in hist.columns for k in self.config.grouping_keys):
            for k_val, grp in hist.groupby(self.config.grouping_keys):
                hist_by_key[k_val] = grp.sort_values("parsed_date")

        rows: List[Dict[str, float]] = []

        for _, row in df.iterrows():
            pred_date = parse_strict_date(row[self.config.date_column])
            sec = str(row["Canteen_Section"])
            meal = str(row["Meal"])
            cat = str(row["Food_Category"])
            price = float(row[self.config.price_column])

            # Filter historical records strictly before prediction date
            key = (sec, meal, cat)
            grp = hist_by_key.get(key)
            if grp is not None and not grp.empty:
                prior_records = grp[grp["parsed_date"] < pred_date]
            else:
                prior_records = pd.DataFrame(columns=hist.columns)

            dow = float(pred_date.weekday())
            row_feats: Dict[str, float] = {
                "unit_price_per_kg": price,
                "day_of_week": dow,
            }

            if self.config.include_cyclic_dow:
                row_feats["dow_sin"] = float(np.sin(2.0 * np.pi * dow / 7.0))
                row_feats["dow_cos"] = float(np.cos(2.0 * np.pi * dow / 7.0))

            if self.config.include_is_weekend:
                row_feats["is_weekend"] = 1.0 if dow >= 5 else 0.0

            # One-hot categoricals
            for m in sorted(self.config.known_meals):
                row_feats[f"meal_{m}"] = 1.0 if meal == m else 0.0
            for s in sorted(self.config.known_sections):
                row_feats[f"section_{s}"] = 1.0 if sec == s else 0.0
            for c in sorted(self.config.known_categories):
                row_feats[f"category_{c}"] = 1.0 if cat == c else 0.0

            # Lag 7d: exactly Date - 7 days
            lag7_date = pred_date - pd.Timedelta(days=self.config.lag_days)
            lag7_match = prior_records[prior_records["parsed_date"] == lag7_date]

            if not lag7_match.empty and not pd.isna(lag7_match[self.config.target_column].iloc[0]):
                row_feats["waste_lag_7d"] = float(lag7_match[self.config.target_column].iloc[0])
                row_feats["is_missing_lag_7d"] = 0.0
            else:
                row_feats["waste_lag_7d"] = float(self._learned_fallback_mean)
                row_feats["is_missing_lag_7d"] = 1.0

            # Rolling windows: [Date - window, Date - 1 day]
            for w in self.config.rolling_windows:
                w_start = pred_date - pd.Timedelta(days=w)
                w_records = prior_records[prior_records["parsed_date"] >= w_start]
                vals = w_records[self.config.target_column].dropna().values

                if len(vals) > 0:
                    row_feats[f"waste_rolling_mean_{w}d"] = float(np.mean(vals))
                    row_feats[f"waste_rolling_std_{w}d"] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
                    row_feats[f"waste_rolling_count_{w}d"] = float(len(vals))
                    row_feats[f"is_missing_rolling_{w}d"] = 0.0
                else:
                    row_feats[f"waste_rolling_mean_{w}d"] = float(self._learned_fallback_mean)
                    row_feats[f"waste_rolling_std_{w}d"] = 0.0
                    row_feats[f"waste_rolling_count_{w}d"] = 0.0
                    row_feats[f"is_missing_rolling_{w}d"] = 1.0

            rows.append(row_feats)

        result_df = pd.DataFrame(rows)[self._feature_names].astype(float)
        return result_df

    def transform(
        self,
        df: pd.DataFrame,
        is_training: bool = False,
        historical_records: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Unified transformation dispatcher for training and inference."""
        if is_training:
            return self.transform_training_batch(df)
        return self.transform_inference(df, historical_records=historical_records)

    def transform_single(
        self,
        date_str: str,
        meal: str,
        canteen_section: str,
        food_category: str,
        unit_price_per_kg: float,
        historical_records: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """Convenience method for transforming a single inference request."""
        single_df = pd.DataFrame(
            [
                {
                    self.config.date_column: date_str,
                    "Meal": meal,
                    "Canteen_Section": canteen_section,
                    "Food_Category": food_category,
                    self.config.price_column: unit_price_per_kg,
                }
            ]
        )
        return self.transform_inference(single_df, historical_records=historical_records)


def create_candidate_feature_pipeline(
    train_df: Optional[pd.DataFrame] = None,
) -> TemporalFeaturePipeline:
    """Factory helper to instantiate and optionally fit a candidate feature pipeline."""
    pipeline = TemporalFeaturePipeline()
    if train_df is not None:
        pipeline.fit(train_df)
    return pipeline
