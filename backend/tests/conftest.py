"""
tests/conftest.py — Pytest Fixtures
Cung cấp fixtures chung cho toàn bộ test suite.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Settings cho môi trường test — override API keys bằng mock."""
    return Settings(
        DEBUG=True,
        GOOGLE_API_KEY="test_key",
        TAVILY_API_KEY="test_tavily_key",
    )


@pytest.fixture(scope="session")
def test_client(test_settings: Settings) -> TestClient:
    """FastAPI TestClient đã cấu hình."""
    app = create_app()
    return TestClient(app)
