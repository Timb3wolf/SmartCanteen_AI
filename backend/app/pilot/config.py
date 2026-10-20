"""Configuration for the isolated SmartCanteen AI Pilot Data Store."""

import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Pilot database path - physically distinct from production database
# Configurable via environment variable; defaults to data/pilot_operational.db (ignored by git)
PILOT_DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
PILOT_DATABASE_PATH = Path(
    os.getenv("PILOT_DATABASE_PATH", str(PILOT_DATA_DIR / "pilot_operational.db"))
)

# Pilot Operational Constants
PILOT_TARGET_SECTION = "A"
PILOT_TARGET_MEAL = "Lunch"
PILOT_TARGET_SERVICE_COUNT = 40
PILOT_TARGET_COMPLIANCE_RATE = 0.90  # 90%
PILOT_HOLDOUT_RESERVE_DAYS = 10
