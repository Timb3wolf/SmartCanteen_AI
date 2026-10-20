"""Machine Learning modules, feature pipelines, and evaluation frameworks for SmartCanteen AI."""

from backend.app.ml.features import (
    TemporalFeatureConfig,
    TemporalFeaturePipeline,
    create_candidate_feature_pipeline,
    parse_strict_date,
)
from backend.app.ml.evaluation import (
    ClassificationMetrics,
    DummyMeanPredictor,
    DummyMedianPredictor,
    RegressionMetrics,
    RollingOriginSplitter,
    SplitFold,
    TimeAwareEvaluator,
    evaluate_classification,
    evaluate_regression,
    safe_r2_score,
)

__all__ = [
    "TemporalFeatureConfig",
    "TemporalFeaturePipeline",
    "create_candidate_feature_pipeline",
    "parse_strict_date",
    "ClassificationMetrics",
    "DummyMeanPredictor",
    "DummyMedianPredictor",
    "RegressionMetrics",
    "RollingOriginSplitter",
    "SplitFold",
    "TimeAwareEvaluator",
    "evaluate_classification",
    "evaluate_regression",
    "safe_r2_score",
]
