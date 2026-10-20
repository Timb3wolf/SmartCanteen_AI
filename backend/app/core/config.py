"""Configuration module for SmartCanteen AI Backend."""

import os
from pathlib import Path
from typing import List

# Resolve repository root
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Data and model directories
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
MODELS_DIR = Path(os.getenv("MODELS_DIR", str(BASE_DIR / "models")))

DATASET_PATH = DATA_DIR / "raw" / "SmartCanteen_Final_Dataset.csv"
REGRESSION_MODEL_PATH = MODELS_DIR / "waste_regression_model.pkl"
CLASSIFIER_MODEL_PATH = MODELS_DIR / "waste_risk_classifier.pkl"
REGRESSION_FEATURES_PATH = MODELS_DIR / "regression_features.pkl"
CLASSIFICATION_FEATURES_PATH = MODELS_DIR / "classification_features.pkl"

# SQLite database for prediction history
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "predictions.db")))

# CORS origins
DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
]

def get_cors_origins() -> List[str]:
    env_origins = os.getenv("CORS_ORIGINS")
    if env_origins:
        return [origin.strip() for origin in env_origins.split(",") if origin.strip()]
    return DEFAULT_CORS_ORIGINS

API_V1_PREFIX = "/api"
PROJECT_NAME = "SmartCanteen AI"
PROJECT_VERSION = "2.0.0"
