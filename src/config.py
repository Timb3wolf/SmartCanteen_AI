"""Configuration module for SmartCanteen AI.

Centralizes all project paths using pathlib.Path.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"

REGRESSION_MODEL_PATH = MODELS_DIR / "waste_regression_model.pkl"
CLASSIFIER_MODEL_PATH = MODELS_DIR / "waste_risk_classifier.pkl"
REGRESSION_FEATURES_PATH = MODELS_DIR / "regression_features.pkl"
CLASSIFICATION_FEATURES_PATH = MODELS_DIR / "classification_features.pkl"
DATASET_PATH = DATA_DIR / "raw" / "SmartCanteen_Final_Dataset.csv"
