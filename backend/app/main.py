"""FastAPI application main module for SmartCanteen AI."""

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.analytics import router as analytics_router
from backend.app.api.health import router as health_router
from backend.app.api.metadata import router as metadata_router
from backend.app.api.models_info import router as models_router
from backend.app.api.predictions import router as predictions_router
from backend.app.core.config import API_V1_PREFIX, PROJECT_NAME, PROJECT_VERSION, get_cors_origins
from backend.app.core.database import init_db
from backend.app.services.analytics_service import AnalyticsService
from backend.app.services.prediction_service import PredictionService

# Configure logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("smartcanteen.api")

# Global singleton service instances
analytics_service: AnalyticsService = None  # type: ignore
prediction_service: PredictionService = None  # type: ignore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager: initialize database, cache dataset, and load ML models."""
    global analytics_service, prediction_service
    logger.info("Initializing SmartCanteen AI backend services...")

    # Initialize SQLite database
    init_db()
    logger.info("Database initialized successfully.")

    # Initialize analytics service
    analytics_service = AnalyticsService()
    logger.info("Analytics service loaded with %d historical records.", len(analytics_service.df))

    # Initialize prediction service (loads .pkl models)
    prediction_service = PredictionService()
    logger.info("ML prediction models loaded successfully.")

    yield

    logger.info("Shutting down SmartCanteen AI backend.")


app = FastAPI(
    title=PROJECT_NAME,
    version=PROJECT_VERSION,
    description="Production-grade API for university canteen food waste prediction, risk classification, and analytics.",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Configure CORS
origins = get_cors_origins()
logger.info("Enabling CORS for origins: %s", origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(health_router, prefix=API_V1_PREFIX)
app.include_router(metadata_router, prefix=API_V1_PREFIX)
app.include_router(analytics_router, prefix=API_V1_PREFIX)
app.include_router(predictions_router, prefix=API_V1_PREFIX)
app.include_router(models_router, prefix=API_V1_PREFIX)


@app.get("/")
def root_status() -> JSONResponse:
    """Root redirect / basic welcome message."""
    return JSONResponse(
        content={
            "app": PROJECT_NAME,
            "version": PROJECT_VERSION,
            "status": "online",
            "docs": "/api/docs",
        }
    )
