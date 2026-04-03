"""Shared test fixtures and configuration.

Provides reusable fixtures for:
- FastAPI test client
- Authentication headers
- Sample data factories
- Cleanup utilities
"""

import io
import os
import sys
from typing import Generator

import pytest
from fastapi.testclient import TestClient

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.core.config import Settings, get_settings
from backend.app.main import create_app
from backend.app.services.job_store import job_store


# Test API key
TEST_API_KEY = "test-api-key-for-testing"


def get_test_settings() -> Settings:
    """Override settings for testing."""
    return Settings(
        api_key=TEST_API_KEY,
        environment="testing",
        debug=True,
        log_level="DEBUG",
    )


@pytest.fixture()
def app():
    """Create a fresh FastAPI app for each test."""
    from backend.app.core.config import get_settings
    test_app = create_app()
    test_app.dependency_overrides[get_settings] = get_test_settings
    return test_app


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    """Create a test client for the app."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Return valid authentication headers."""
    return {"X-API-Key": TEST_API_KEY}


@pytest.fixture()
def invalid_auth_headers() -> dict[str, str]:
    """Return invalid authentication headers."""
    return {"X-API-Key": "invalid-key"}


@pytest.fixture()
def sample_png_file() -> io.BytesIO:
    """Create a minimal valid PNG file for testing."""
    from PIL import Image
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


@pytest.fixture()
def sample_jpeg_file() -> io.BytesIO:
    """Create a minimal valid JPEG file for testing."""
    from PIL import Image
    img = Image.new("RGB", (100, 100), (0, 255, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    buffer.seek(0)
    return buffer


@pytest.fixture(autouse=True)
def cleanup_job_store():
    """Clear the job store before each test."""
    job_store._jobs.clear()
    yield
    job_store._jobs.clear()


@pytest.fixture()
def valid_element_id() -> str:
    """Return a valid element ID from the catalog."""
    return "elem-minifig-torso-001"


@pytest.fixture()
def invalid_element_id() -> str:
    """Return an element ID that does not exist."""
    return "elem-nonexistent-999"
