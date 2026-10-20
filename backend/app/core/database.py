"""SQLite database manager for persistent prediction history."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.app.core.config import DATABASE_PATH


def get_db_connection() -> sqlite3.Connection:
    """Create and return a SQLite database connection with row factory enabled."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DATABASE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize SQLite tables for prediction history."""
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_date TEXT NOT NULL,
                meal TEXT NOT NULL,
                canteen_section TEXT NOT NULL,
                food_category TEXT NOT NULL,
                unit_price_per_kg REAL NOT NULL,
                predicted_waste_kg REAL NOT NULL,
                predicted_risk TEXT NOT NULL,
                estimated_financial_loss REAL NOT NULL,
                model_version TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()


def save_prediction(
    prediction_date: str,
    meal: str,
    canteen_section: str,
    food_category: str,
    unit_price_per_kg: float,
    predicted_waste_kg: float,
    predicted_risk: str,
    estimated_financial_loss: float,
    model_version: str,
) -> Dict[str, Any]:
    """Save a prediction result into SQLite and return the inserted record."""
    created_at = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO predictions (
                prediction_date,
                meal,
                canteen_section,
                food_category,
                unit_price_per_kg,
                predicted_waste_kg,
                predicted_risk,
                estimated_financial_loss,
                model_version,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prediction_date,
                meal,
                canteen_section,
                food_category,
                unit_price_per_kg,
                predicted_waste_kg,
                predicted_risk,
                estimated_financial_loss,
                model_version,
                created_at,
            ),
        )
        conn.commit()
        inserted_id = cursor.lastrowid

    return {
        "id": inserted_id,
        "prediction_date": prediction_date,
        "meal": meal,
        "canteen_section": canteen_section,
        "food_category": food_category,
        "unit_price_per_kg": unit_price_per_kg,
        "predicted_waste_kg": predicted_waste_kg,
        "predicted_risk": predicted_risk,
        "estimated_financial_loss": estimated_financial_loss,
        "model_version": model_version,
        "created_at": created_at,
    }


def get_predictions(
    limit: int = 100,
    meal: Optional[str] = None,
    risk: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve predictions from SQLite with optional filtering."""
    query = "SELECT * FROM predictions WHERE 1=1"
    params: List[Any] = []

    if meal:
        query += " AND meal = ?"
        params.append(meal)
    if risk:
        query += " AND predicted_risk = ?"
        params.append(risk)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()

    return [dict(row) for row in rows]


def clear_predictions() -> int:
    """Clear all records from prediction history and return count of deleted records."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM predictions")
        count = cursor.fetchone()[0]
        cursor.execute("DELETE FROM predictions")
        conn.commit()
    return count
