"""Configuration for the isolated SmartCanteen AI Pilot Data Store.

Enforces strict isolation from the production database and defines
operational parameters for the Canteen Section A Lunch pilot.
"""

import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Pilot data directory & database path
PILOT_DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
PILOT_DATABASE_PATH = Path(
    os.getenv("PILOT_DATABASE_PATH", str(PILOT_DATA_DIR / "pilot_operational.db"))
)

# Pilot Operational Constants
PILOT_TIMEZONE = "Asia/Colombo"
PILOT_TARGET_SECTION = "A"
PILOT_TARGET_MEAL = "Lunch"
PILOT_TARGET_SERVICE_COUNT = 40
PILOT_TARGET_COMPLIANCE_RATE = 0.90  # 90%
PILOT_HOLDOUT_RESERVE_DAYS = 10
PILOT_CUTOFF_HOURS_BEFORE_SERVICE = 4  # T - 4h prediction cutoff

# Security & Upload Limits
MAX_POS_CSV_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB limit for CSV payloads
MAX_POS_CSV_ROWS = 5000                   # Maximum allowed rows per import


def validate_pilot_db_path(path: Path) -> Path:
    """Validate that the pilot database path does NOT collide with production database.
    
    Raises:
        RuntimeError: If the target path resolves to the production database or
                      uses the reserved production filename 'predictions.db'.
    """
    resolved_path = path.resolve()
    
    # Check against production database path
    from backend.app.core.config import DATABASE_PATH as PROD_DATABASE_PATH
    resolved_prod = PROD_DATABASE_PATH.resolve()

    if resolved_path == resolved_prod or resolved_path.name.lower() == "predictions.db":
        raise RuntimeError(
            f"FATAL SECURITY VIOLATION: Pilot database path '{resolved_path}' conflicts with "
            f"production database path '{resolved_prod}'. The pilot data store MUST be "
            f"physically separate and never share filenames with production storage."
        )

    return path
