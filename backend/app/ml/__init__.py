"""Machine Learning modules, feature pipelines, evaluation, and benchmarking for SmartCanteen AI."""

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
from backend.app.ml.benchmark import (
    BenchmarkFoldRecord,
    BenchmarkModelSpec,
    ModelBenchmarkRunner,
    ModelFoldResult,
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
    "BenchmarkFoldRecord",
    "BenchmarkModelSpec",
    "ModelBenchmarkRunner",
    "ModelFoldResult",
]
