"""Re-export time-aware evaluation framework from backend.app.ml.evaluation."""

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
