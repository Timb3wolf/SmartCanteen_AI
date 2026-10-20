"""Test configuration and fixtures."""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure repo root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
